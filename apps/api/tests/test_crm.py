"""Real PG production CRM endpoints; session injection only substitutes authentication."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from silicon.main import create_app
from silicon.settings import Settings
from silicon.identity.routes import SESSION,CSRF
from silicon.identity.access import tenant_transaction
from test_identity import identities,session_insert


def payload(number='CUS-001',name='澄川大学 · 人工智能学院'):
    one,two,p1,p2=(str(uuid4()) for _ in range(4))
    return {'number':number,'name':name,'province':'浙江','city':'杭州','industry':'高校',
            'contacts':[{'id':one,'name':'周明远','email':'zhou@example.invalid'},{'id':two,'name':'许知微'}],
            'projects':[{'id':p1,'name':'科研平台','people':[{'contact_id':one,'role':'project_lead'},{'contact_id':two,'role':'key_person'}]},
                        {'id':p2,'name':'教学平台','people':[{'contact_id':two,'role':'project_lead'}]}],
            'sites':[{'id':str(uuid4()),'name':'科研楼','address':'虚构科研路 18 号'}]}


@contextmanager
def client(engine,database,user,tenant):
    token,csrf=session_insert(engine,user,tenant)
    with TestClient(create_app(Settings(database.url,'test')),base_url='https://localhost:5173') as c:
        c.cookies.set(SESSION,token);c.cookies.set(CSRF,csrf)
        c.headers.update({'Origin':'https://localhost:5173','X-CSRF-Token':csrf,'Idempotency-Key':str(uuid4())})
        context=c.get('/api/v1/session').json()
        c.headers.update({'X-Expected-Tenant':str(tenant),'X-Session-Context':context['context_id']})
        yield c


def update_body(response,**changes):
    fields=('number','name','province','city','industry','level','stage','notes','contacts','projects','sites','responsibilities')
    return {**{k:response[k] for k in fields},'expected_version':response['version'],**changes}


def test_crud_relationships_refresh_history_and_audit(engine,database,identities):
    i=identities;body=payload();body['responsibilities']=[{'role':'sales','user_id':str(i.user)}]
    with client(engine,database,i.user,i.a) as c:
        created=c.post('/api/v1/crm/customers',json=body);assert created.status_code==201,created.text
        data=created.json();url='/api/v1/crm/customers/'+data['id']
        assert len(data['contacts'])==2 and len(data['projects'])==2 and len(data['role_history'])==4
        edit=update_body(data,name='更新后的虚构学院',projects=[next(p for p in data['projects'] if p['name']=='科研平台')],responsibilities=[])
        response=c.put(url,json=edit);assert response.status_code==200,response.text
        result=response.json();assert result['version']==2 and any(r['valid_until'] for r in result['role_history'])
    with client(engine,database,i.user,i.a) as fresh:
        persisted=fresh.get(url).json();assert persisted['name']=='更新后的虚构学院' and persisted['version']==2
        assert fresh.get('/api/v1/crm/customers?q=周明远').json()['total']==1
    with tenant_transaction(engine,i.user,i.a,'crm.read','audit') as (db,_):
        rows=db.execute(text("SELECT action,object_id,request_id FROM audit_events WHERE action LIKE 'customer.%'")).all()
        assert ('customer.create',data['id'],created.headers['X-Request-ID']) in [tuple(r) for r in rows]
        assert db.scalar(text('SELECT count(*) FROM crm_role_history WHERE valid_until IS NOT NULL'))==2


def test_idempotency_and_concurrent_edit_conflict(engine,database,identities):
    i=identities;body=payload();key=str(uuid4())
    with client(engine,database,i.user,i.a) as c:
        first=c.post('/api/v1/crm/customers',json=body,headers={'Idempotency-Key':key})
        again=c.post('/api/v1/crm/customers',json=body,headers={'Idempotency-Key':key});assert first.json()==again.json()
        assert c.post('/api/v1/crm/customers',json={**body,'name':'different'},headers={'Idempotency-Key':key}).status_code==409
        data=first.json();url='/api/v1/crm/customers/'+data['id']
    def write(name):
        with client(engine,database,i.user,i.a) as c:return c.put(url,json=update_body(data,name=name)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(write,['edit A','edit B']))
    assert sorted(results)==[200,409]
    with client(engine,database,i.user,i.a) as c:
        assert c.get(url).json()['version']==2
        assert c.get('/api/v1/crm/customers').json()['total']==1


def test_concurrent_duplicate_create_single_customer(engine,database,identities):
    i=identities;body=payload();key=str(uuid4())
    def create(_):
        with client(engine,database,i.user,i.a) as c:return c.post('/api/v1/crm/customers',json=body,headers={'Idempotency-Key':key}).json()['id']
    with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(create,range(2)))
    assert len(set(ids))==1


def test_tenants_permissions_default_rls_and_invalid_input(engine,database,identities):
    i=identities;body=payload()
    with client(engine,database,i.user,i.a) as a:
        created=a.post('/api/v1/crm/customers',json=body).json();url='/api/v1/crm/customers/'+created['id']
        for bad in ({**body,'name':' '},{**body,'tenant_id':str(i.b)}, {**body,'projects':[{'id':str(uuid4()),'name':'bad','people':[{'contact_id':str(uuid4()),'role':'key_person'}]}]}):
            assert a.post('/api/v1/crm/customers',json=bad).status_code==422
        assert a.post('/api/v1/crm/customers',json=payload('CUS-002'),headers={'X-CSRF-Token':''}).status_code==403
        assert a.post('/api/v1/crm/customers',json=body,headers={'Idempotency-Key':str(uuid4())}).status_code==409
        assert a.get('/api/v1/crm/customers?page_size=101').status_code==422
    with client(engine,database,i.other,i.b) as b:
        assert b.get(url).status_code==404
        assert b.put(url,json=update_body(created)).status_code==404
        assert b.get('/api/v1/crm/customers').json()['total']==0
        assert b.post('/api/v1/crm/customers',json=body).status_code==201 # same business number, other tenant
    with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:t AND user_id=:u"),dict(t=i.a,u=i.user))
    with client(engine,database,i.user,i.a) as a:
        assert a.get(url).status_code==200
        assert a.put(url,json=update_body(created)).status_code==403
    with engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM crm_customers'))==0
        assert db.scalar(text("SELECT bool_and(relrowsecurity AND relforcerowsecurity) FROM pg_class WHERE relname LIKE 'crm_%' AND relkind='r'"))
    with pytest.raises(DBAPIError):
        with engine.begin() as db:db.execute(text("INSERT INTO crm_customers(tenant_id,id,number,name,owner_id) VALUES (:t,:id,'forged','forged',:u)"),dict(t=i.a,id=uuid4(),u=i.user))


def test_pagination_search_own_scope_and_foreign_membership(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.b) as c:
        for n in range(3):
            assert c.post('/api/v1/crm/customers',json=payload(f'CUS-{n}',f'客户 {n}'),headers={'Idempotency-Key':str(uuid4())}).status_code==201
        first=c.get('/api/v1/crm/customers?page_size=2').json()
        second=c.get('/api/v1/crm/customers?page=2&page_size=2').json()
        assert first['total']==3 and len(first['items'])==2 and len(second['items'])==1
        assert not {x['id'] for x in first['items']} & {x['id'] for x in second['items']}
        assert c.get('/api/v1/crm/customers?q=客户 1').json()['total']==1
        bad=payload('BAD');bad['responsibilities']=[{'role':'sales','user_id':str(uuid4())}]
        assert c.post('/api/v1/crm/customers',json=bad,headers={'Idempotency-Key':'bad-owner'}).status_code==422
    with client(engine,database,i.other,i.b) as c:
        other=c.post('/api/v1/crm/customers',json=payload('OTHER')).json()
    with client(engine,database,i.user,i.b) as c:
        assert c.get('/api/v1/crm/customers').json()['total']==3
        assert c.get('/api/v1/crm/customers/'+other['id']).status_code==404


def test_child_relationships_cannot_cross_customers(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        first=c.post('/api/v1/crm/customers',json=payload()).json()
        second=c.post('/api/v1/crm/customers',json=payload('CUS-002'),headers={'Idempotency-Key':'second'}).json()
        invalid=update_body(second,contacts=first['contacts'],projects=[])
        assert c.put('/api/v1/crm/customers/'+second['id'],json=invalid,headers={'Idempotency-Key':'bad-rel'}).status_code==422
    with pytest.raises(DBAPIError):
        with tenant_transaction(engine,i.user,i.a,'crm.write','fk-check') as (db,_):
            db.execute(text('INSERT INTO crm_project_people VALUES (:t,:c,:p,:person,\'key_person\')'),
              dict(t=i.a,c=first['id'],p=first['projects'][0]['id'],person=second['contacts'][0]['id']))


@pytest.mark.parametrize('start_revision',['0002_identity','0003_crm','0004_session_context','0005_catalog','0006_quotes'])
def test_upgrade_from_task002_preserves_identity_and_tenant_job(database,start_revision):
    import subprocess,sys
    from pathlib import Path
    from sqlalchemy.engine import make_url
    from silicon.shared.db import make_engine
    root=Path(__file__).resolve().parents[3]
    bootstrap=make_engine(str(make_url(database.url).set(username='silicon_bootstrap',database='postgres')))
    name='silicon_crm_upgrade'
    with bootstrap.connect().execution_options(isolation_level='AUTOCOMMIT') as db:db.execute(text(f'CREATE DATABASE {name} OWNER silicon_migrator'))
    url=str(make_url(database.migration_url).set(database=name));owner=make_engine(url)
    actor,tenant,job=(uuid4() for _ in range(3))
    env={**database.env,'MIGRATION_DATABASE_URL':url}
    try:
        with owner.begin() as db:db.execute(text('GRANT USAGE ON SCHEMA public TO silicon_app'))
        for revision in (start_revision,'head'):
            result=subprocess.run([sys.executable,'infra/migrate.py','upgrade',revision],cwd=root,env=env,capture_output=True,text=True,timeout=15)
            assert result.returncode==0,result.stderr
            if revision==start_revision:
                with owner.begin() as db:
                    db.execute(text("INSERT INTO identity_users(id,issuer,subject,display_name) VALUES (:u,'test','legacy','legacy user')"),{'u':actor})
                    db.execute(text("INSERT INTO tenants VALUES (:t,'legacy tenant')"),{'t':tenant})
                    db.execute(text("INSERT INTO memberships VALUES (:t,:u,'admin',true)"),dict(t=tenant,u=actor))
                    db.execute(text("INSERT INTO jobs(id,kind,dedupe_key,tenant_id,actor_id) VALUES (:id,'identity.check','legacy-tenant-job',:t,:u)"),dict(id=job,t=tenant,u=actor))
                    db.execute(text("INSERT INTO sessions(token_hash,user_id,tenant_id,csrf_hash,expires_at) VALUES ('legacy-session',:u,:t,'legacy-csrf',now()+interval '5 minutes')"),dict(u=actor,t=tenant))
                    if start_revision in ('0004_session_context','0005_catalog','0006_quotes'):
                        db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),dict(t=str(tenant),u=str(actor)))
                        db.execute(text("INSERT INTO crm_customers(tenant_id,id,number,name,owner_id) VALUES (:t,:id,'UPGRADE-CUSTOMER','原客户',:u)"),dict(t=tenant,id=actor,u=actor))
                        db.execute(text("INSERT INTO crm_contacts(tenant_id,customer_id,id,name,title,phone,email) VALUES (:t,:id,:id,'原联系人','','','')"),dict(t=tenant,id=actor))
                if start_revision in ('0005_catalog','0006_quotes'):
                    import sys
                    sys.path.insert(0,str(root/'infra'))
                    from catalog_examples import seed
                    old_app=make_engine(str(make_url(database.url).set(database=name)))
                    seed(old_app,actor,tenant)
                    if start_revision=='0006_quotes':
                        with owner.begin() as db:
                            db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),dict(t=str(tenant),u=str(actor)))
                            db.execute(text("INSERT INTO crm_projects(tenant_id,customer_id,id,name,notes) VALUES (:t,:id,:id,'原项目','')"),dict(t=tenant,id=actor))
                            bom=db.scalar(text("SELECT id FROM catalog_boms WHERE state='published' LIMIT 1"))
                            db.execute(text("INSERT INTO quote_drafts(tenant_id,id,name,customer_id,project_id,bom_id,quantity,scope,tax_included,calculation,owner_id) VALUES (:t,:id,'原草稿',:id,:id,:bom,1,'retail',true,'{}',:id)"),dict(t=tenant,id=actor,bom=bom))
                    old_app.dispose()
        app=make_engine(str(make_url(database.url).set(database=name)))
        with tenant_transaction(app,actor,tenant,'crm.read','upgrade') as (db,_):
            assert db.scalar(text('SELECT version_num FROM alembic_version'))=='0012_delivery'
            assert db.scalar(text("SELECT context_id IS NOT NULL FROM sessions WHERE token_hash='legacy-session'"))
            assert db.scalar(text('SELECT count(*) FROM crm_customers'))==(1 if start_revision in ('0004_session_context','0005_catalog','0006_quotes') else 0)
            if start_revision in ('0004_session_context','0005_catalog','0006_quotes'):
                assert db.scalar(text('SELECT name FROM crm_customers'))=='原客户'
                assert db.scalar(text('SELECT name FROM crm_contacts'))=='原联系人'
            if start_revision in ('0005_catalog','0006_quotes'):
                assert db.scalar(text('SELECT count(*) FROM catalog_skus'))==3
                assert db.scalar(text("SELECT count(*) FROM catalog_boms WHERE state='published'"))==2
                assert str(db.scalar(text('SELECT amount FROM catalog_price_lines')))=='10000.50'
            if start_revision=='0006_quotes':
                assert db.scalar(text('SELECT name FROM quote_drafts'))=='原草稿'
                assert db.scalar(text('SELECT calculation FROM quote_drafts'))=={}
            assert db.scalar(text('SELECT tenant_id FROM jobs WHERE id=:id'),{'id':job})==tenant
        from silicon.shared.jobs import run_once
        assert run_once(app)
        with app.connect() as db:assert db.scalar(text('SELECT status FROM jobs WHERE id=:id'),{'id':job})=='completed'
        app.dispose()
    finally:
        owner.dispose()
        # DROP checkpoints all prior test activity: observed 3.176s after the full
        # suite, exceeding the application's 3s query budget. Maintenance only;
        # business requests and concurrency tests retain their original timeout.
        with bootstrap.connect().execution_options(isolation_level='AUTOCOMMIT') as db:
            db.execute(text("SET statement_timeout='30s'"))
            db.execute(text(f'DROP DATABASE {name}'))
        bootstrap.dispose()
