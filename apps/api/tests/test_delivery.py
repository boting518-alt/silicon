"""Real PostgreSQL and HTTP; login fixture substitutes only OIDC."""
from uuid import uuid4
from test_identity import identities
from test_contracts import file_root
from test_assembly import prepared,client,ok
from test_assembly_correction import issued_work,finish
P='/api/v1/delivery'
def cmd(c,path,body,key=None):return c.post(P+path,json=body,headers={'Idempotency-Key':key or str(uuid4())})
def setup(engine,database,i,n=1):
    o,loc,b=prepared(engine,database,i,mode='batch');devices=[]
    with client(engine,database,i.user,i.a) as c:
        for k in range(n):devices.append(ok(finish(c,issued_work(c,b),loc['id'],serial=f'DEL-{k}'))['devices'][0]['id'])
    return o,loc,devices

def test_test_history_eligibility_and_ship_gate(engine,database,identities):
    i=identities;o,loc,ids=setup(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        d=ok(c.get(P+'/devices/'+ids[0]));assert d['eligibility']=='pending'
        ship=ok(cmd(c,'/shipments',{'order_id':o['id'],'device_ids':ids,'recipient':'虚构接收方','address':'测试地址','contact':'测试经办'}))
        assert cmd(c,'/shipments/'+ship['id']+'/confirm',{'expected_version':1,'confirmed':True}).json()['code']=='DEVICE_TEST_REQUIRED'
        body={'expected_version':d['version'],'completion_id':d['completion_id'],'performed_at':'2026-09-11T00:00:00Z','items':[{'name':'启动检查','result':'fail'}],'notes':'虚构人工测试'}
        d=ok(cmd(c,'/devices/'+ids[0]+'/tests',body));assert d['eligibility']=='fail'
        d=ok(cmd(c,'/devices/'+ids[0]+'/tests',{**body,'expected_version':d['version'],'items':[{'name':'启动检查','result':'pass'}]}));assert d['eligibility']=='pass' and len(d['tests'])==2
        sent=ok(cmd(c,'/shipments/'+ship['id']+'/confirm',{'expected_version':1,'confirmed':True}));assert sent['state']=='confirmed'
        assert ok(c.get(P+'/devices/'+ids[0]))['eligibility']=='shipped'

def passing(c,id):
    d=ok(c.get(P+'/devices/'+id))
    return ok(cmd(c,'/devices/'+id+'/tests',{'expected_version':d['version'],'completion_id':d['completion_id'],'performed_at':'2026-09-11T00:00:00Z','items':[{'name':'虚构测试','result':'pass'}]}))
def make_ship(c,o,ids):return ok(cmd(c,'/shipments',{'order_id':o['id'],'device_ids':ids,'recipient':'虚构客户','address':'虚构地址','contact':'虚构联系人'}))
def send(c,s):return ok(cmd(c,'/shipments/'+s['id']+'/confirm',{'expected_version':s['version'],'confirmed':True}))
def test_split_accept_return_retest_original_cost_and_history(engine,database,identities):
    i=identities;o,loc,ids=setup(engine,database,i,3)
    with client(engine,database,i.user,i.a) as c:
        for id in ids:passing(c,id)
        first=send(c,make_ship(c,o,ids[:2]));second=send(c,make_ship(c,o,ids[2:]));assert second['progress']['remaining']==0
        body={'expected_version':first['version'],'confirmed':True,'line_ids':[first['lines'][0]['id']],'performed_at':'2026-09-11T00:00:00Z','confirmation':'虚构签收'}
        accepted=ok(cmd(c,'/shipments/'+first['id']+'/accept',body));assert accepted['progress']['accepted']==1
        assert cmd(c,'/shipments/'+first['id']+'/accept',{**body,'expected_version':accepted['version']}).status_code==409
        rb={'expected_version':accepted['version'],'confirmed':True,'line_ids':body['line_ids'],'performed_at':'2026-09-11T00:00:00Z','location_id':loc['id'],'reason':'实际收到虚构退货'}
        key=str(uuid4());returned=ok(cmd(c,'/shipments/'+first['id']+'/return',rb,key));assert ok(cmd(c,'/shipments/'+first['id']+'/return',rb,key))==returned
        assert returned['progress']['net_delivered']==2 and returned['progress']['remaining']==1 and returned['progress']['cost']=='100.00'
        did=first['lines'][0]['device_id'];d=ok(c.get(P+'/devices/'+did));assert d['eligibility']=='pending' and d['inventory'][0]['state']=='pending'
        stock=ok(c.get('/api/v1/inventory/stock'));assert stock['known_cost']=='80.00'
        retry=make_ship(c,o,[did]);assert cmd(c,'/shipments/'+retry['id']+'/confirm',{'expected_version':1,'confirmed':True}).status_code==409
        passing(c,did);again=send(c,retry);assert again['progress']['net_delivered']==3 and again['progress']['returned']==1 and again['progress']['cost']=='180.00'
        assert ok(c.get('/api/v1/inventory/stock'))['known_cost']=='0.00'
        assert ok(c.get(P+'/devices/'+did))['inventory_unit_id']==d['inventory_unit_id']

def test_concurrent_shipping_return_and_permission_replays(engine,database,identities):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import text
    i=identities;o,loc,ids=setup(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        passing(c,ids[0]);drafts=[make_ship(c,o,ids) for _ in range(2)]
    barrier=Barrier(2)
    def attempt(s):
        with client(engine,database,i.user,i.a) as c:
            barrier.wait(5);return cmd(c,'/shipments/'+s['id']+'/confirm',{'expected_version':1,'confirmed':True})
    with ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(attempt,x) for x in drafts];results=[f.result(timeout=15) for f in futures]
    assert sorted(x.status_code for x in results)==[200,409]
    s=next(x.json() for x in results if x.status_code==200)
    rb={'expected_version':s['version'],'confirmed':True,'line_ids':[s['lines'][0]['id']],'performed_at':'2026-09-11T00:00:00Z','location_id':loc['id'],'reason':'实收'}
    barrier=Barrier(2)
    def back(key):
        with client(engine,database,i.user,i.a) as c:
            barrier.wait(5);return key,cmd(c,'/shipments/'+s['id']+'/return',rb,key)
    with ThreadPoolExecutor(2) as pool:
        fs=[pool.submit(back,str(uuid4())) for _ in range(2)];results=[f.result(timeout=15) for f in fs]
    assert sorted(r.status_code for _,r in results)==[200,409]
    key,r=next(x for x in results if x[1].status_code==200)
    with client(engine,database,i.user,i.a) as c:
        assert ok(cmd(c,'/shipments/'+s['id']+'/return',rb,key))==r.json()
        assert ok(c.get('/api/v1/inventory/stock'))['known_cost']=='180.00' # returned80 plus untouched material100
        with i.owner.begin() as db:db.execute(text("DELETE FROM role_permissions WHERE role='admin' AND permission='delivery.return'"))
        try:assert cmd(c,'/shipments/'+s['id']+'/return',rb,key).status_code==403
        finally:
            with i.owner.begin() as db:db.execute(text("INSERT INTO role_permissions VALUES('admin','delivery.return')"))
        c.headers['X-Expected-Tenant']=str(i.b);assert cmd(c,'/shipments/'+s['id']+'/return',rb,key).status_code==409
    with client(engine,database,i.other,i.b) as c:assert c.get(P+'/shipments/'+s['id']).status_code==404
    with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.other})
    with client(engine,database,i.other,i.a) as c:
        v=ok(c.get(P+'/shipments/'+s['id']));assert 'cost' not in v['progress'] and 'cost' not in v['lines'][0]
        assert 'cost' not in ok(c.get(P+'/devices/'+ids[0]))
        assert cmd(c,'/shipments',{'order_id':o['id'],'device_ids':ids,'recipient':'a','address':'b','contact':'c'}).status_code==403

def test_history_correction_and_assembly_dependency(engine,database,identities):
    from test_assembly_correction import undo
    from test_assembly import post as asmcmd,P as AP
    i=identities;o,loc,ids=setup(engine,database,i,1)
    with client(engine,database,i.user,i.a) as c:
        d=passing(c,ids[0]);oldtest=d['tests'][0]
        w=ok(c.get(AP+'/works/'+d['work_id']));undone=undo(c,w)
        done=ok(finish(c,undone,loc['id'],serial=d['serial'],correction_of=d['completion_id']))
        changed=ok(c.get(P+'/devices/'+ids[0]));assert changed['eligibility']=='pending' and changed['tests'][0]==oldtest
        passing(c,ids[0]);s=send(c,make_ship(c,o,ids[:1]))
        assert asmcmd(c,'/works/'+w['id']+'/reverse',{'expected_version':done['version'],'confirmed':True,'movement_id':done['devices'][0]['movement_id']}).json()['code']=='DELIVERY_DEPENDENCY'
        # Generic inventory correction must not bypass the domain's downstream guard.
        from test_inventory import post as stockcmd
        assert stockcmd(c,'/movements/'+s['lines'][0]['movement_id']+'/reverse',{'expected_version':1,'confirmed':True,'reason':'错误入口'}).status_code==409
        ab={'expected_version':s['version'],'confirmed':True,'line_ids':[s['lines'][0]['id']],'performed_at':'2026-09-11T00:00:00Z','confirmation':'原验收'}
        accepted=ok(cmd(c,'/shipments/'+s['id']+'/accept',ab));original=accepted['lines'][0]['acceptances'][0]
        corrected=ok(cmd(c,'/shipments/'+s['id']+'/correct-acceptance',{'expected_version':accepted['version'],'confirmed':True,'acceptance_id':original['id'],'performed_at':'2026-09-11T00:00:00Z','confirmation':'纠正误登记','reason':'客户尚未完成验收'}))
        assert corrected['progress']['accepted']==0 and corrected['lines'][0]['acceptances'][0]==original
        assert cmd(c,'/shipments/'+s['id']+'/reverse',{'expected_version':corrected['version'],'confirmed':True}).json()['code']=='DELIVERY_DOWNSTREAM_DEPENDENCY'
        plan={k:w[k] for k in ('order_id','product_sku_id','manager_id','planned_on')}
        ids.append(ok(finish(c,issued_work(c,plan),loc['id'],serial='DEL-SECOND'))['devices'][0]['id'])
        passing(c,ids[1]);other=send(c,make_ship(c,o,ids[1:]));rev=ok(cmd(c,'/shipments/'+other['id']+'/reverse',{'expected_version':other['version'],'confirmed':True,'reason':'误操作冲销'}))
        assert rev['reversals'] and rev['progress']['net_delivered']==1
        assert ok(c.get(P+'/devices/'+ids[1]))['eligibility']=='pending'
        assert not ok(c.get('/api/v1/inventory/reconciliation'))['differences']
        assert ok(c.get(P+'/reconciliation'))['matches']

def test_upgrade_populated_0011_and_lossy_downgrade_refused(engine,database,identities):
    import os,subprocess,sys
    i=identities;o,loc,ids=setup(engine,database,i)
    def migrate(command,target,good=True):
        r=subprocess.run([sys.executable,'infra/migrate.py',command,target],env={**os.environ,'DATABASE_URL':database.url,'MIGRATION_DATABASE_URL':database.migration_url},capture_output=True,text=True)
        assert (r.returncode==0)==good,r.stderr
    with client(engine,database,i.user,i.a) as c:before=ok(c.get('/api/v1/assembly/devices/'+ids[0]))
    migrate('downgrade','0011_assembly_corrections');migrate('upgrade','head')
    with client(engine,database,i.user,i.a) as c:
        assert ok(c.get('/api/v1/assembly/devices/'+ids[0]))==before
        assert ok(c.get(P+'/orders'))[0]['quantity']==3
        passing(c,ids[0])
    migrate('downgrade','0011_assembly_corrections',False)
    with client(engine,database,i.user,i.a) as c:assert ok(c.get(P+'/devices/'+ids[0]))['eligibility']=='pass'

def test_latest_failure_move_invalidation_and_line_boundaries(engine,database,identities):
    from test_inventory import post as stockcmd
    i=identities;o,loc,ids=setup(engine,database,i,2)
    with client(engine,database,i.user,i.a) as c:
        d=passing(c,ids[0]);s=make_ship(c,o,ids[:1])
        fail={'expected_version':d['version'],'completion_id':d['completion_id'],'performed_at':'2026-09-10T00:00:00Z','items':[{'name':'后续失败','result':'fail'}]}
        d=ok(cmd(c,'/devices/'+ids[0]+'/tests',fail));assert d['eligibility']=='fail'
        assert cmd(c,'/shipments/'+s['id']+'/confirm',{'expected_version':1,'confirmed':True}).status_code==409
        d=passing(c,ids[0]);target=ok(stockcmd(c,'/locations',{'warehouse':'虚构成品','name':'新库位'}))
        ok(stockcmd(c,'/transfers',{'layer_id':d['layer_id'],'expected_version':d['version'],'confirmed':True,'source_location_id':loc['id'],'source_state':'pending','target_location_id':target['id'],'target_state':'pending','quantity':1,'reason':'验证移库使测试失效'}))
        assert ok(c.get(P+'/devices/'+ids[0]))['eligibility']=='pending'
        assert cmd(c,'/shipments/'+s['id']+'/confirm',{'expected_version':1,'confirmed':True}).status_code==409
        passing(c,ids[0]);s=send(c,s)
        other=make_ship(c,o,ids[1:])
        ab={'expected_version':s['version'],'confirmed':True,'performed_at':'2026-09-11T00:00:00Z','confirmation':'虚构确认','line_ids':[other['lines'][0]['id']]}
        assert cmd(c,'/shipments/'+s['id']+'/accept',ab).status_code==404
        assert cmd(c,'/shipments/'+other['id']+'/accept',{**ab,'expected_version':1}).status_code==409
        assert cmd(c,'/shipments/'+s['id']+'/accept',{**ab,'line_ids':[s['lines'][0]['id']]*2}).status_code==422
        assert ok(c.get(P+'/reconciliation'))['matches']
