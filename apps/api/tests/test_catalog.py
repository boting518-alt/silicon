"""Real PostgreSQL + production HTTP catalog tests. Session injection is test-only."""
from uuid import uuid4
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import threading,time
import pytest
from sqlalchemy import text,event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from test_crm import client,payload
from test_identity import identities
from silicon.identity.access import tenant_transaction

BASE='/api/v1/catalog'
def send(c,path,body,method='post',key=None):
    return c.request(method,BASE+path,json=body,headers={'Idempotency-Key':key or str(uuid4())})

def ok(r,status=201):
    assert r.status_code==status,r.text
    return r.json()

def product(c,number,category='host',**changes):
    return ok(send(c,'/skus',{'number':number,'name':'虚构 '+number,'category':category,'manufacturer':'虚构制造商','brand':'硅屿测试品牌','brand_kind':'own',**changes}))

def line(s,quantity=1,**kw):return {'sku_id':s['id'],'quantity':quantity,'required':True,'charge_mode':'included',**kw}

def package(c,host,lines,name='虚构包件',**kw):
    return ok(send(c,'/boms',{'name':name,'kind':'package','subject_sku_id':host['id'],'lines':lines,**kw}))

def publish(c,kind,value):return ok(send(c,f'/{kind}/{value["id"]}/publish',{'expected_version':value['version']}),200)

def price(c,sku,amount='100.00',**kw):
    return ok(send(c,'/price-books',{'name':'虚构价格','scope':'retail','currency':'CNY','tax_included':True,'valid_from':'2026-01-01T00:00:00Z','valid_to':'2027-01-01T00:00:00Z','source':'虚构测试定价单','lines':[{'sku_id':sku['id'],'amount':amount}],**kw}))

def update_body(item,kind,**kw):
    from silicon.catalog.models import SkuInput,BomInput,PriceInput
    cls={'skus':SkuInput,'boms':BomInput,'price-books':PriceInput}[kind]
    return {**{k:item[k] for k in cls.model_fields},'expected_version':item['version'],**kw}


def test_sku_maintenance_unique_specs_and_idempotency(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        s=product(c,'HW-1','cpu',specs={'socket':'DEMO-S1','power_w':200})
        assert s['specs']['socket']=='DEMO-S1' and 'cost' not in s
        assert send(c,'/skus',update_body(s,'skus')).status_code==422
        body=update_body(s,'skus',enabled=False,name='停用型号');key=str(uuid4())
        changed=ok(send(c,'/skus/'+s['id'],body,'put',key),200)
        assert changed['version']==2 and changed['enabled'] is False
        assert ok(send(c,'/skus/'+s['id'],body,'put',key),200)==changed
        assert send(c,'/skus/'+s['id'],{**body,'name':'different'},'put',key).json()['code']=='IDEMPOTENCY_CONFLICT'
        assert send(c,'/skus/'+s['id'],body,'put').json()['code']=='VERSION_CONFLICT'
        duplicate={k:s[k] for k in ('number','name','category','manufacturer','brand','brand_kind')}
        assert send(c,'/skus',duplicate).json()['code']=='CATALOG_DUPLICATE'
        assert send(c,'/skus',{**duplicate,'number':'HW-2','brand_kind':'third_party'}).json()['code']=='BRAND_KIND_CONFLICT'
        for category in ['host','gpu','memory','psu','system_disk','data_disk','nic','ib']:
            assert product(c,category,category,specs={'capacity_gb':128,'interface':'DEMO','speed_gbps':100})['category']==category
        assert c.get(BASE+'/skus?q=HW-1').json()==[changed]
    with client(engine,database,i.other,i.b) as c:assert product(c,'HW-1')['number']=='HW-1'


def test_permissions_cross_tenant_and_context(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        host=product(c,'A');other=product(c,'part','psu');b=package(c,host,[line(other)])
        c.post('/api/v1/session/tenant',json={'tenant_id':str(i.b)})
        for path in ['/skus','/skus/'+host['id'],'/boms','/boms/'+b['id'],'/rules','/price-books','/current-price/'+host['id']+'?scope=retail']:
            assert c.get(BASE+path).json()['code']=='CONTEXT_CHANGED'
        assert send(c,'/skus',{k:host[k] for k in ('number','name','category','manufacturer','brand','brand_kind')}).status_code==409
        session=c.get('/api/v1/session').json();c.headers.update({'X-Expected-Tenant':str(i.b),'X-Session-Context':session['context_id']})
        assert c.get(BASE+'/skus/'+host['id']).status_code==404
        assert send(c,'/boms',{'name':'x','kind':'package','subject_sku_id':host['id'],'lines':[]}).status_code==403
    with client(engine,database,i.other,i.b) as c:
        own=product(c,'B')
        r=send(c,'/boms',{'name':'x','kind':'package','subject_sku_id':own['id'],'lines':[line(other)]})
        assert r.status_code==404
        assert send(c,'/price-books',{'name':'x','scope':'retail','tax_included':True,'valid_from':'2026-01-01T00:00:00Z','valid_to':'2027-01-01T00:00:00Z','source':'test','lines':[{'sku_id':host['id'],'amount':'1.00'}]}).status_code==404
    with pytest.raises(DBAPIError):
        with tenant_transaction(engine,i.other,i.b,'catalog.write','FK') as (db,_):
            db.execute(text("INSERT INTO catalog_bom_lines VALUES (:t,:b,0,:s,NULL,1,true,'included')"),{'t':i.b,'b':b['id'],'s':other['id']})
    with engine.connect() as db:assert db.scalar(text('SELECT count(*) FROM catalog_skus'))==0


def test_packages_rules_versions_and_frozen_snapshot(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        host=product(c,'含电源');empty=product(c,'不含电源');psu=product(c,'PSU','psu',specs={'power_w':1200});cpu=product(c,'CPU','cpu',specs={'socket':'D1'});mem=product(c,'RAM','memory',specs={'memory_generation':'D5'})
        rule=ok(send(c,'/rules',{'name':'虚构平台规则','source':'示例工程说明，不是供应商资料','socket':'D1','memory_generation':'D5','power_budget_w':1000}))
        included=package(c,host,[line(psu,2),line(cpu),line(mem)],rule_id=rule['id'])
        assert all(x['charge_mode']=='included' for x in included['snapshot']['technical_lines'])
        assert any(x['code']=='POWER' and x['status']=='PASS' for x in included['snapshot']['checks'])
        bare=package(c,empty,[],rule_id=rule['id']);assert any(x['code']=='POWER' and x['status']=='BLOCK' for x in bare['snapshot']['checks'])
        frozen=publish(c,'boms',included)
        assert send(c,'/boms/'+frozen['id'],update_body(frozen,'boms',name='overwrite'),'put').json()['code']=='PUBLISHED_IMMUTABLE'
        revised=ok(send(c,'/boms/'+frozen['id']+'/revise',{'expected_version':frozen['version']}))
        assert revised['revision']==2 and revised['id']!=frozen['id']
        ok(send(c,'/boms/'+revised['id'],update_body(revised,'boms',lines=[line(cpu)]),'put'),200)
        ok(send(c,'/skus/'+psu['id'],update_body(psu,'skus',name='NEW PSU'),'put'),200)
        new_rule=ok(send(c,'/rules/'+rule['id']+'/revise',{'name':'规则修订','source':'新虚构资料','socket':'D2','expected_version':1}))
        assert new_rule['revision']==2
        assert c.get(BASE+'/boms/'+frozen['id']).json()==frozen
        machine=product(c,'整机方案')
        nested=ok(send(c,'/boms',{'name':'组合','kind':'bom','subject_sku_id':machine['id'],'rule_id':rule['id'],'lines':[line(host,package_version_id=frozen['id'],charge_mode='separate')]}))
        assert next(x for x in nested['snapshot']['technical_lines'] if x['sku']['id']==psu['id'])['charge_mode']=='included'
        assert next(x for x in nested['snapshot']['technical_lines'] if x['sku']['id']==psu['id'])['sku']['name']==psu['name']


def test_invalid_cycle_and_unknown_rules(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        a=product(c,'A');b=product(c,'B');p=product(c,'P','psu')
        for quantity in [0,-1,1.5,10001]:
            assert send(c,'/boms',{'name':'bad','kind':'package','subject_sku_id':a['id'],'lines':[line(p,quantity)]}).status_code==422
        assert send(c,'/boms',{'name':'self','kind':'package','subject_sku_id':a['id'],'lines':[line(a)]}).json()['code']=='CYCLIC_PACKAGE'
        a1=publish(c,'boms',package(c,a,[line(b)]))
        response=send(c,'/boms',{'name':'cycle','kind':'package','subject_sku_id':b['id'],'lines':[line(a,package_version_id=a1['id'])]})
        assert response.json()['code']=='CYCLIC_PACKAGE'
        unknown=package(c,b,[line(p)])
        assert any(x['status']=='UNKNOWN' for x in unknown['snapshot']['checks'])
        assert not any(x['status']=='PASS' for x in unknown['snapshot']['checks'])


def test_prices_unknown_zero_expiry_overlap_and_history(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        sku=product(c,'PRICE')
        def current(at):return c.get(BASE+'/current-price/'+sku['id'],params={'scope':'retail','as_of':at}).json()
        assert current('2026-01-01T00:00:00Z')['status']=='UNKNOWN'
        book=price(c,sku,'0.00');assert isinstance(book['lines'][0]['amount'],str)
        assert current('2026-01-01T00:00:00Z')['status']=='UNKNOWN'
        published=publish(c,'price-books',book)
        assert current('2025-12-31T23:59:59Z')['status']=='NOT_YET_VALID'
        value=current('2026-01-01T00:00:00Z');assert value['status']=='KNOWN' and value['amount']=='0.00' and value['revision']==1 and value['source']=='虚构测试定价单'
        assert current('2027-01-01T00:00:00Z')['status']=='EXPIRED' and current('2027-01-01T00:00:00Z')['amount'] is None
        overlap=price(c,sku,'9.00');assert send(c,'/price-books/'+overlap['id']+'/publish',{'expected_version':1}).json()['code']=='PRICE_OVERLAP'
        revision=ok(send(c,'/price-books/'+published['id']+'/revise',{'expected_version':published['version']}))
        revision=ok(send(c,'/price-books/'+revision['id'],update_body(revision,'price-books',valid_from='2027-01-01T00:00:00Z',valid_to='2028-01-01T00:00:00Z',lines=[{'sku_id':sku['id'],'amount':'12.34'}]),'put'),200)
        publish(c,'price-books',revision)
        assert current('2027-01-01T00:00:00Z')['amount']=='12.34'
        assert c.get(BASE+'/price-books/'+published['id']).json()==published
        assert send(c,'/price-books/'+published['id'],update_body(published,'price-books'),'put').json()['code']=='PUBLISHED_IMMUTABLE'
        bad=update_body(revision,'price-books',lines=[{'sku_id':sku['id'],'amount':'1.001'}]);assert send(c,'/price-books/'+revision['id'],bad,'put').status_code==422


def test_concurrent_update_and_publish_overlap(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c,client(engine,database,i.user,i.a) as d:
        sku=product(c,'RACE');body=update_body(sku,'skus',name='new');gate=threading.Barrier(2)
        def change(cl):gate.wait(3);return send(cl,'/skus/'+sku['id'],body,'put').status_code
        with ThreadPoolExecutor(2) as pool:assert sorted([f.result() for f in [pool.submit(change,c),pool.submit(change,d)]])==[200,409]
        a=price(c,sku);b=price(c,sku);gate=threading.Barrier(2)
        def pub(cl,book):gate.wait(3);return send(cl,'/price-books/'+book['id']+'/publish',{'expected_version':1}).status_code
        with ThreadPoolExecutor(2) as pool:assert sorted([f.result() for f in [pool.submit(pub,c,a),pool.submit(pub,d,b)]])==[200,409]


@pytest.mark.parametrize('kind',['skus','boms','price-books'])
def test_real_aggregate_read_waits_for_complete_write(engine,database,identities,kind):
    i=identities;paused=threading.Event();release=threading.Event();started=threading.Event();pid={}
    def after(db,cursor,statement,params,ctx,many):
        if threading.current_thread().name.startswith('catalog-read') and statement.startswith('SELECT * FROM '+{'skus':'catalog_skus','boms':'catalog_boms','price-books':'catalog_price_books'}[kind]+' WHERE id='):
            paused.set();assert release.wait(5)
    # Production TestClient uses an ASGI portal thread; test the same service/guard transaction directly.
    from silicon.catalog import service as s
    from silicon.catalog.models import SkuUpdate,BomUpdate,PriceUpdate
    with client(engine,database,i.user,i.a) as c:
        host=product(c,'CONSISTENT',specs={'socket':'OLD'});part=product(c,'PART','psu')
        original=host if kind=='skus' else package(c,host,[line(part)]) if kind=='boms' else price(c,host)
    read_fn={'skus':s.sku,'boms':s.bom,'price-books':s.price_book}[kind]
    write_fn={'skus':s.save_sku,'boms':s.save_bom,'price-books':s.save_price}[kind]
    model={'skus':SkuUpdate,'boms':BomUpdate,'price-books':PriceUpdate}[kind]
    changes={'specs':{'socket':'NEW'}} if kind=='skus' else {'lines':[line(part,2)]} if kind=='boms' else {'lines':[{'sku_id':host['id'],'amount':'200.00'}]}
    def read():
        with tenant_transaction(engine,i.user,i.a,'catalog.read','read') as (db,a):s.guard(db,a);return read_fn(db,original['id'])
    def write():
        with tenant_transaction(engine,i.user,i.a,'catalog.write','write') as (db,a):
            pid['writer']=db.scalar(text('SELECT pg_backend_pid()'));started.set();s.guard(db,a,True)
            return write_fn(db,a,model.model_validate(update_body(original,kind,name='NEW',**changes)),original['id'])
    event.listen(engine,'after_cursor_execute',after)
    try:
        with ThreadPoolExecutor(1,thread_name_prefix='catalog-read') as reads,ThreadPoolExecutor(1) as writes:
            r=reads.submit(read)
            try:
                assert paused.wait(2);w=writes.submit(write);assert started.wait(2)
                end=time.monotonic()+1;blocked=False
                while time.monotonic()<end:
                    with engine.connect() as db:blocked=bool(db.scalar(text('SELECT cardinality(pg_blocking_pids(:id))'),{'id':pid['writer']}))
                    if blocked:break
                    time.sleep(.01)
                assert blocked and not w.done()
            finally:release.set()
            old=r.result(3);new=w.result(3)
        assert old.version==1 and old.name==original['name']
        assert new.version==2 and new.name=='NEW'
        if kind=='skus':assert old.specs.socket=='OLD' and new.specs.socket=='NEW'
        elif kind=='boms':assert old.lines[0].quantity==1 and new.lines[0].quantity==2
        else:assert str(old.lines[0].amount)=='100.00' and str(new.lines[0].amount)=='200.00'
    finally:release.set();event.remove(engine,'after_cursor_execute',after)


def test_published_database_mutations_denied(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        host=product(c,'DB');psu=product(c,'PSU','psu');b=publish(c,'boms',package(c,host,[line(psu)]));p=publish(c,'price-books',price(c,host))
    for sql,id in [("UPDATE catalog_boms SET name='mutate' WHERE id=:id",b['id']),("DELETE FROM catalog_bom_lines WHERE bom_id=:id",b['id']),("UPDATE catalog_price_books SET source='mutate' WHERE id=:id",p['id']),("DELETE FROM catalog_price_lines WHERE book_id=:id",p['id'])]:
        with pytest.raises(DBAPIError):
            with tenant_transaction(engine,i.user,i.a,'catalog.write','db-boundary') as (db,_):db.execute(text(sql),{'id':id})


def test_context_guards_all_catalog_commands_and_csrf(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        host=product(c,'GUARD');part=product(c,'PART','psu');bom=package(c,host,[line(part)]);book=price(c,host)
        for header in ['X-Expected-Tenant','X-Session-Context']:
            saved=c.headers.pop(header);assert c.get(BASE+'/skus').status_code==428;c.headers[header]=saved
        csrf=c.headers.pop('X-CSRF-Token')
        assert send(c,'/boms/'+bom['id']+'/publish',{'expected_version':1}).status_code==403
        c.headers['X-CSRF-Token']=csrf
        c.post('/api/v1/session/tenant',json={'tenant_id':str(i.b)})
        for kind,item in [('skus',host),('boms',bom),('price-books',book)]:
            assert send(c,'/'+kind+'/'+item['id'],update_body(item,kind),'put').json()['code']=='CONTEXT_CHANGED'
            if kind!='skus':
                for action in ['publish','revise']:assert send(c,'/'+kind+'/'+item['id']+'/'+action,{'expected_version':1}).json()['code']=='CONTEXT_CHANGED'
        assert send(c,'/rules',{'name':'wrong','source':'test'}).json()['code']=='CONTEXT_CHANGED'
    with tenant_transaction(engine,i.user,i.a,'catalog.read','verify') as (db,_):
        assert db.scalar(text('SELECT version FROM catalog_skus WHERE id=:id'),{'id':host['id']})==1
        assert db.scalar(text("SELECT count(*) FROM audit_events WHERE action='sku.create' AND object_id=:id AND outcome='allowed'"),{'id':host['id']})==1


def test_catalog_rls_role_and_invalid_price_inputs(engine,database,identities):
    i=identities
    with engine.connect() as db:
        role=db.execute(text('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
        assert role==(False,False)
        assert db.scalar(text("SELECT bool_and(relrowsecurity AND relforcerowsecurity) FROM pg_class WHERE relname LIKE 'catalog_%' AND relkind='r'"))
    with client(engine,database,i.user,i.a) as c:
        host=product(c,'INPUT');book=price(c,host)
        raw=update_body(book,'price-books')
        for change in [{'currency':'USD'},{'valid_to':raw['valid_from']},{'valid_from':'2026-01-01T00:00:00'},{'lines':[{'sku_id':host['id'],'amount':'-1.00'}]},{'lines':[{'sku_id':host['id'],'amount':'NaN'}]}]:
            assert send(c,'/price-books/'+book['id'],{**raw,**change},'put').status_code==422
        package_draft=package(c,host,[])
        ok(send(c,'/skus/'+host['id'],update_body(host,'skus',enabled=False),'put'),200)
        detail=ok(c.get(BASE+'/boms/'+package_draft['id']),200)
        assert any(x['code']=='DISABLED_SKU' for x in detail['snapshot']['checks'])
        assert send(c,'/boms/'+package_draft['id']+'/publish',{'expected_version':1}).json()['code']=='DISABLED_SKU'


def test_expanded_quantity_is_bounded_without_commercial_credit(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        root=product(c,'ROOT');child=product(c,'CHILD');part=product(c,'PART','psu')
        package_version=publish(c,'boms',package(c,child,[line(part,10000)]))
        r=send(c,'/boms',{'name':'oversized','kind':'bom','subject_sku_id':root['id'],'lines':[line(child,10000,package_version_id=package_version['id'])]})
        assert r.status_code==422 and r.json()['code']=='PACKAGE_SIZE_LIMIT'
        published_price=publish(c,'price-books',price(c,child,'10.00'))
        revised=ok(send(c,'/boms/'+package_version['id']+'/revise',{'expected_version':package_version['version']}))
        ok(send(c,'/boms/'+revised['id'],update_body(revised,'boms',lines=[]),'put'),200)
        assert c.get(BASE+'/price-books/'+published_price['id']).json()['lines'][0]['amount']=='10.00'
