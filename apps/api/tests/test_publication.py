"""Real PG/API lifecycle; session fixture only replaces OIDC login."""
from uuid import uuid4
from sqlalchemy import text
from test_identity import identities
from test_crm import client
from test_quotes import fixture,config,command
from test_catalog import ok,product,publish,price

P='/api/v1/publication'
def call(c,path,body=None,key=None):
    return c.post(P+path,json=body or {},headers={'Idempotency-Key':key or str(uuid4())})

def test_missing_policy_blocks_submission(engine,database,identities):
    with client(engine,database,identities.user,identities.a) as c:
        customer,host,psu,bom=fixture(c)
        draft=ok(command(c,'',config(customer,bom)))
        response=call(c,'/drafts/'+draft['id']+'/submit',{'expected_version':1,'valid_until':'2026-12-01T00:00:00Z'})
        assert response.status_code==422,response.text
        assert response.json()['code']=='PUBLICATION_POLICY_REQUIRED'

def prepare(c,i):
    from test_crm import payload
    from test_catalog import package,line,send
    customer=ok(c.post('/api/v1/crm/customers',json=payload('PUB'),headers={'Idempotency-Key':str(uuid4())}))
    host=product(c,'PUB-H');parts=[product(c,'PUB-'+kind,kind) for kind in ['cpu','memory','psu','system_disk','gpu']]
    bom=publish(c,'boms',package(c,host,[line(p,2 if p['category']=='psu' else 1) for p in parts]))
    publish(c,'price-books',price(c,host,'100.00',valid_from='2020-01-01T00:00:00Z',valid_to='2099-01-01T00:00:00Z'))
    with i.owner.begin() as db:
        db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:a,true)"),{'t':str(i.a),'a':str(i.user)})
        db.execute(text("INSERT INTO publication_policies VALUES (:t,:id,1,true,'development',true,'虚构测试责任范围','unlimited')"),{'t':i.a,'id':uuid4()})
        db.execute(text("INSERT INTO memberships VALUES (:t,:u,'admin',true) ON CONFLICT DO NOTHING"),{'t':i.a,'u':i.other})
    draft=ok(command(c,'',config(customer,bom)))
    return draft,parts,customer

def submit(c,draft):return ok(call(c,'/drafts/'+draft['id']+'/submit',{'expected_version':draft['version'],'valid_until':'2098-01-01T00:00:00Z'}))
def approve(c,can,key=None):
    return call(c,'/candidates/'+can['id']+'/decide',{'expected_version':can['draft_version'],'approved':True,'note':'虚构审批说明',
      'confirmations':[{'code':x['code'],'explanation':'虚构确认，保留原风险','evidence':'虚构人工核对记录'} for x in can['content']['calculation']['checks'] if x['status'] in ['WARN','UNKNOWN']]},key)
def issue(c,can,key=None):return call(c,'/candidates/'+can['id']+'/issue',{'expected_version':can['draft_version'],'confirmed':True},key)
def convert(c,v,key=None):return call(c,'/contracts/from-quote',{'quote_version_id':v['id'],'expected_version':v['version']},key)

def test_two_people_lifecycle_replay_snapshots_and_withdrawal(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,parts,customer=prepare(one,i);can=submit(one,draft)
        assert can['state']=='pending' and can['content']['development']
        assert approve(one,can).json()['code']=='SELF_APPROVAL_FORBIDDEN'
        with client(engine,database,i.other,i.a) as two:
            assert ok(approve(two,can),200)['state']=='approved'
            v=ok(issue(two,can));again=ok(issue(two,can));assert again['id']==v['id']
            assert v['content_hash']==can['content_hash'] and v['content']==can['content']
            ct=ok(convert(two,v));assert ok(convert(two,v))['id']==ct['id']
            assert ct['content']==v['content'] and ct['source_hash']==v['content_hash']
            assert ct['content']['calculation']['total']=='300.00'
            from test_catalog import send,update_body
            ok(send(two,'/skus/'+parts[0]['id'],update_body(parts[0],'skus',name='后来名称'),'put'),200)
            assert two.get(P+'/versions/'+v['id']).json()['content']==v['content']
            assert len(two.get(P+'/versions').json())==1 and len(two.get(P+'/contracts').json())==1
            result=ok(call(two,'/versions/'+v['id']+'/withdraw',{'expected_version':1,'reason':'虚构撤回'}),200)
            assert result['state']=='withdrawn'
            assert convert(two,v).json()['code']=='SOURCE_NOT_ACTIVE'
            assert two.get(P+'/contracts/'+ct['id']).json()['source_state']=='withdrawn'


def test_edit_invalidates_and_reapproval_uses_new_version(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,_,_=prepare(one,i);can=submit(one,draft)
        with client(engine,database,i.other,i.a) as two:
            ok(approve(two,can),200)
            changed=ok(command(one,'/'+draft['id'],{**draft['config'],'quantity':4,'expected_version':1},'put'),200)
            assert two.get(P+'/candidates/'+can['id']).json()['state']=='invalidated'
            assert issue(two,can).json()['code']=='APPROVAL_INVALIDATED'
            new=submit(one,changed);ok(approve(two,new),200);v=ok(issue(two,new))
            assert v['content']['calculation']['total']=='400.00'
            revised=ok(call(two,'/versions/'+v['id']+'/revise',{'expected_version':1}))
            assert revised['id']!=draft['id'] and revised['version']==1
            assert two.get(P+'/versions/'+v['id']).json()['content']==v['content']

import pytest
from sqlalchemy.exc import DBAPIError
from silicon.identity.access import tenant_transaction

@pytest.mark.parametrize('change',['policy','discount','expiry','sku','customer','price_time'])
def test_dependency_change_requires_reapproval(engine,database,identities,monkeypatch,change):
    from silicon.publication import service as s
    from silicon.quotes import service as quotes
    from test_quotes import policy as discount_policy
    from test_catalog import send,update_body
    from test_crm import update_body as crm_update
    from datetime import datetime,timezone
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,parts,customer=prepare(one,i)
        if change=='discount':
            d=discount_policy(database,i.a)
            draft=ok(command(one,'/'+draft['id'],{**draft['config'],'discount_id':d,'expected_version':1},'put'),200)
        can=submit(one,draft)
        with client(engine,database,i.other,i.a) as two:
            ok(approve(two,can),200)
            assert two.get(P+'/candidates/'+can['id']).json()['state']=='approved'
            if change in ('policy','discount'):
                with i.owner.begin() as db:
                    db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:a,true)"),{'t':str(i.a),'a':str(i.user)})
                    if change=='policy':db.execute(text('UPDATE publication_policies SET enabled=false'))
                    else:db.execute(text("UPDATE quote_discounts SET version=version+1,maximum_discount=1"))
            elif change=='expiry':monkeypatch.setattr(s,'now',lambda:datetime(2098,1,1,tzinfo=timezone.utc))
            elif change=='price_time':
                class Clock:
                    @classmethod
                    def now(cls,tz):return datetime(2099,1,1,tzinfo=timezone.utc)
                monkeypatch.setattr(quotes,'datetime',Clock)
            elif change=='sku':ok(send(two,'/skus/'+parts[0]['id'],update_body(parts[0],'skus',enabled=False),'put'),200)
            else:ok(two.put('/api/v1/crm/customers/'+customer['id'],json=crm_update(customer,name='新名称')),200)
            assert issue(two,can).status_code in (409,422)
            assert two.get(P+'/versions').json()==[]

@pytest.mark.parametrize('change',['risks','forbid','limited','hard','disabled','missing','no_price'])
def test_risks_cannot_override_hard_errors(engine,database,identities,change):
    from test_catalog import send,update_body
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,parts,_=prepare(one,i)
        if change in ('forbid','limited'):
            with i.owner.begin() as db:
                db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:a,true)"),{'t':str(i.a),'a':str(i.user)})
                db.execute(text('UPDATE publication_policies SET '+("allow_risks=false" if change=='forbid' else "discount_quota='limited'")))
        if change in ('disabled','missing','no_price','hard'):
            body={**draft['config'],'expected_version':1}
            if change=='disabled':ok(send(one,'/skus/'+parts[0]['id'],update_body(parts[0],'skus',enabled=False),'put'),200)
            elif change=='missing':body['excluded_sku_ids']=[parts[0]['id']]
            elif change=='no_price':body['scope']='unconfigured'
            else:
                # A known insufficient PSU budget is deterministic BLOCK.
                from test_catalog import package,line
                rule=ok(send(one,'/rules',{'name':'known','source':'fictional','socket':'A','memory_generation':'D5','power_budget_w':10000}))
                psu=parts[2];psu=ok(send(one,'/skus/'+psu['id'],update_body(psu,'skus',specs={'power_w':1}),'put'),200)
                host=one.get('/api/v1/catalog/skus?q=PUB-H').json()[0]
                bom=publish(one,'boms',package(one,host,[line(p) for p in parts],rule_id=rule['id']))
                body['bom_id']=bom['id']
            draft=ok(command(one,'/'+draft['id'],body,'put'),200)
            r=call(one,'/drafts/'+draft['id']+'/submit',{'expected_version':draft['version'],'valid_until':'2098-01-01T00:00:00Z'})
            assert r.json()['code']=='PUBLICATION_HARD_BLOCK';return
        if change=='limited':
            assert call(one,'/drafts/'+draft['id']+'/submit',{'expected_version':1,'valid_until':'2098-01-01T00:00:00Z'}).json()['code']=='DISCOUNT_QUOTA_UNSUPPORTED';return
        can=submit(one,draft)
        with client(engine,database,i.other,i.a) as two:
            if change=='forbid':assert approve(two,can).json()['code']=='RISK_POLICY_FORBIDS'
            else:assert call(two,'/candidates/'+can['id']+'/decide',{'expected_version':1,'approved':True,'note':'x'}).json()['code']=='RISK_CONFIRMATION_REQUIRED'

def test_concurrent_decisions_publication_conversion_and_immutable_role(engine,database,identities):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,_,_=prepare(one,i);can=submit(one,draft)
    barrier=Barrier(2)
    def decide_once(approved):
        with client(engine,database,i.other,i.a) as two:
            barrier.wait(timeout=5)
            return approve(two,can) if approved else call(two,'/candidates/'+can['id']+'/decide',{'expected_version':1,'approved':False,'note':'驳回'})
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(decide_once,[True,False]))
    assert sorted(r.status_code for r in results)==[200,409]
    with client(engine,database,i.user,i.a) as one:can=submit(one,draft)
    with client(engine,database,i.other,i.a) as two:ok(approve(two,can),200)
    def publish_once(_):
        with client(engine,database,i.other,i.a) as two:
            barrier.wait(timeout=5);return ok(issue(two,can))
    with ThreadPoolExecutor(2) as pool:versions=list(pool.map(publish_once,range(2)))
    assert versions[0]['id']==versions[1]['id'];v=versions[0]
    def convert_once(_):
        with client(engine,database,i.other,i.a) as two:
            barrier.wait(timeout=5);return ok(convert(two,v))
    with ThreadPoolExecutor(2) as pool:contracts=list(pool.map(convert_once,range(2)))
    assert contracts[0]['id']==contracts[1]['id']
    for table in ['publication_candidates','publication_decisions','quote_versions','contract_drafts']:
        for sql in [f'DELETE FROM {table}',f'UPDATE {table} SET id=id']:
            with pytest.raises(DBAPIError):
                with tenant_transaction(engine,i.user,i.a,'quote.read','immutable') as (db,_):db.execute(text(sql))
    with engine.connect() as db:
        assert not db.scalar(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user"))
        for table in ['publication_candidates','quote_versions','contract_drafts']:assert db.scalar(text('SELECT count(*) FROM '+table))==0


def test_replay_checks_revoked_permissions_and_context(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,_,_=prepare(one,i);can=submit(one,draft)
        with client(engine,database,i.other,i.a) as two:
            ok(approve(two,can),200);key=str(uuid4());v=ok(issue(two,can,key))
            with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.other})
            assert issue(two,can,key).status_code==403
            two.headers['X-Session-Context']=str(uuid4())
            assert two.get(P+'/versions/'+v['id']).json()['code']=='CONTEXT_CHANGED'
        with client(engine,database,i.other,i.b) as other:
            assert other.get(P+'/versions/'+v['id']).status_code==404
            assert convert(other,v).status_code==404
        with i.owner.begin() as db:db.execute(text("UPDATE memberships SET active=false WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.other})
        assert issue(one,can).json()['code']=='PARTICIPANT_ACCESS_CHANGED'

@pytest.mark.parametrize('race',['edit','withdraw'])
def test_publish_edit_and_convert_withdraw_linear_order(engine,database,identities,race):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,_,_=prepare(one,i);can=submit(one,draft)
    with client(engine,database,i.other,i.a) as two:
        ok(approve(two,can),200)
        if race=='withdraw':v=ok(issue(two,can))
    barrier=Barrier(2)
    def left():
        with client(engine,database,i.other,i.a) as c:
            barrier.wait(timeout=5)
            return issue(c,can) if race=='edit' else convert(c,v)
    def right():
        with client(engine,database,i.user,i.a) as c:
            barrier.wait(timeout=5)
            return command(c,'/'+draft['id'],{**draft['config'],'quantity':7,'expected_version':1},'put') if race=='edit' else call(c,'/versions/'+v['id']+'/withdraw',{'expected_version':1,'reason':'竞态撤回'})
    with ThreadPoolExecutor(2) as pool:
        a=pool.submit(left);b=pool.submit(right);a=a.result(timeout=12);b=b.result(timeout=12)
    if race=='edit':assert (a.status_code,b.status_code) in [(201,409),(409,200)]
    else:assert b.status_code==200 and a.status_code in (201,409)
    with client(engine,database,i.other,i.a) as c:
        vs=c.get(P+'/versions').json();cts=c.get(P+'/contracts').json()
        if race=='edit' and vs:assert vs[0]['content']['config']['quantity']==3
        if race=='withdraw':
            assert vs[0]['state']=='withdrawn'
            assert len(cts)==(1 if a.status_code==201 else 0)
            if cts:assert cts[0]['source_state']=='withdrawn'

def test_new_validity_supersedes_old_approval_and_expiry_preserves_contract(engine,database,identities,monkeypatch):
    from datetime import datetime,timezone
    from silicon.publication import service as s
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,_,_=prepare(one,i);old=submit(one,draft)
        with client(engine,database,i.other,i.a) as two:
            ok(approve(two,old),200)
            new=ok(call(one,'/drafts/'+draft['id']+'/submit',{'expected_version':1,'valid_until':'2097-01-01T00:00:00Z'}))
            assert issue(two,old).json()['code']=='APPROVAL_INVALIDATED'
            ok(approve(two,new),200);v=ok(issue(two,new));ct=ok(convert(two,v))
            monkeypatch.setattr(s,'now',lambda:datetime(2097,1,1,tzinfo=timezone.utc))
            assert convert(two,v).json()['code']=='SOURCE_NOT_ACTIVE'
            history=two.get(P+'/contracts/'+ct['id']).json()
            assert history['source_state']=='expired' and history['content']==ct['content']

def test_customer_scope_and_current_replay_visibility(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,_,_=prepare(one,i);can=submit(one,draft)
        with client(engine,database,i.other,i.a) as two:
            ok(approve(two,can),200);v=ok(issue(two,can));key=str(uuid4());ok(convert(two,v,key))
            with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='member' WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.other})
            assert convert(two,v,key).status_code==404
            assert two.get(P+'/contracts').json()==[]
            assert two.get(P+'/versions/'+v['id']).status_code==404
            assert two.get(P+'/candidates/'+can['id']).status_code==404


def test_published_revision_gets_new_revision_number(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,_,_=prepare(one,i);can=submit(one,draft)
        with client(engine,database,i.other,i.a) as two:
            ok(approve(two,can),200);v=ok(issue(two,can))
            revised=ok(call(one,'/versions/'+v['id']+'/revise',{'expected_version':1}))
            next_candidate=submit(one,revised);ok(approve(two,next_candidate),200);next_version=ok(issue(two,next_candidate))
            assert next_version['number']=='Q-000001-R2' and next_version['revision']==2
            assert two.get(P+'/versions/'+v['id']).json()['content']==v['content']


def test_new_price_boundary_and_post_issue_crm_policy_leave_content_frozen(engine,database,identities,monkeypatch):
    from datetime import datetime,timezone
    from silicon.quotes import service as quotes
    from test_catalog import send,update_body
    from test_crm import update_body as customer_update
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,_,customer=prepare(one,i);can=submit(one,draft)
        with client(engine,database,i.other,i.a) as two:
            ok(approve(two,can),200);v=ok(issue(two,can));before=two.get(P+'/versions/'+v['id']).json()
            host=two.get('/api/v1/catalog/skus?q=PUB-H').json()[0]
            publish(two,'price-books',price(two,host,'200.00',valid_from='2099-01-01T00:00:00Z',valid_to='2100-01-01T00:00:00Z'))
            ok(two.put('/api/v1/crm/customers/'+customer['id'],json=customer_update(customer,name='变化后的 CRM 名称')),200)
            with i.owner.begin() as db:
                db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:a,true)"),{'t':str(i.a),'a':str(i.user)})
                db.execute(text('UPDATE publication_policies SET enabled=false'))
            after=two.get(P+'/versions/'+v['id']).json()
            assert before==after
            ct=ok(convert(two,v));assert ct['content']==v['content']
            with tenant_transaction(engine,i.user,i.a,'quote.read','frozen-json') as (db,_):
                published=db.scalar(text('SELECT content::text FROM quote_versions WHERE id=:id'),{'id':v['id']})
                contract=db.scalar(text('SELECT content::text FROM contract_drafts WHERE id=:id'),{'id':ct['id']})
                assert published==contract


def test_current_price_version_boundary_invalidates_approval(engine,database,identities,monkeypatch):
    from datetime import datetime,timezone
    from silicon.quotes import service as quotes
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,_,_=prepare(one,i);can=submit(one,draft)
        with client(engine,database,i.other,i.a) as two:
            ok(approve(two,can),200)
            host=two.get('/api/v1/catalog/skus?q=PUB-H').json()[0]
            publish(two,'price-books',price(two,host,'200.00',valid_from='2099-01-01T00:00:00Z',valid_to='2100-01-01T00:00:00Z'))
            class Clock:
                @classmethod
                def now(cls,tz):return datetime(2099,1,1,tzinfo=timezone.utc)
            monkeypatch.setattr(quotes,'datetime',Clock) # Price clock only, no database mock.
            assert two.get('/api/v1/quotes/'+draft['id']).json()['current_calculation']['total']=='600.00'
            assert issue(two,can).json()['code']=='APPROVAL_INVALIDATED'


def test_member_submit_viewer_redaction_and_composite_foreign_key(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as one:
        draft,_,_=prepare(one,i)
        with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='member' WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.user})
        can=submit(one,draft)
        with client(engine,database,i.other,i.a) as two:
            ok(approve(two,can),200);v=ok(issue(two,can))
        with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.user})
        detail=one.get(P+'/candidates/'+can['id']).json()
        assert detail['note'] is None and detail['confirmations'] is None
        assert convert(one,v).status_code==403
    with pytest.raises(DBAPIError):
        with tenant_transaction(engine,i.other,i.b,'quote.read','cross-fk') as (db,_):
            db.execute(text("INSERT INTO contract_drafts VALUES (:t,:id,:source,'x','{}',:a,now())"),{'t':i.b,'id':uuid4(),'source':v['id'],'a':i.other})
