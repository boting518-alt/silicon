"""Real PG/API assembly seam; login fixture only substitutes OIDC."""
from uuid import uuid4
from test_identity import identities
from test_contracts import client,file_root,source,ready,request
from test_inventory import ok,post as invpost
P='/api/v1/assembly'
def post(c,path,body,key=None):return c.post(P+path,json=body,headers={'Idempotency-Key':key or str(uuid4())})
def order(engine,database,i,independent=False):
    if independent:
        from test_publication import prepare,submit,approve,issue,convert
        from test_quotes import command
        from test_catalog import price,publish
        with client(engine,database,i.user,i.a) as c:
            d,parts,_=prepare(c,i);part=next(x for x in parts if x['category']=='memory')
            publish(c,'price-books',price(c,part,'10.00',valid_from='2020-01-01T00:00:00Z',valid_to='2099-01-01T00:00:00Z'))
            d=ok(command(c,'/'+d['id'],{**d['config'],'expected_version':d['version'],'excluded_sku_ids':[part['id']],'additions':[{'sku_id':part['id'],'quantity':2}]},'put'),200)
            can=submit(c,d)
        with client(engine,database,i.other,i.a) as c:
            ok(approve(c,can));v=ok(issue(c,can),201);draft=ok(convert(c,v),201)
    else:draft,_=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        if independent:
            from test_contracts import fields,upload
            f=fields(i);f['payments']=[{'id':str(uuid4()),'name':'约定款','amount':draft['content']['calculation']['total'],'trigger':'signing','offset_days':7}]
            w=ok(request(c,'/'+draft['id']+'/save',{'expected_version':0,'fields':f}))
            proof=ok(upload(c,draft['id'],w['version']),201)
            w=ok(request(c,'/'+draft['id']+'/files/'+proof['id']+'/attach',{'expected_version':w['version']}))
            assert w['ready']
        else:w,_=ready(c,draft['id'],i)
        signed=ok(request(c,'/'+draft['id']+'/sign',{'expected_version':w['version'],'content_hash':w['content_hash'],'confirmed':True}),201)
        return ok(c.get('/api/v1/contracts/orders/'+signed['order_id']))
def test_order_work_mapping_and_capacity(engine,database,identities):
    i=identities;o=order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        r=c.get(P+'/orders');assert r.status_code==200,r.text
        src=r.json()[0];assert src['quantity']==3
        host=o['content']['commercial']['host']['id']
        ok(invpost(c,'/tracking/'+host,{'mode':'sn'}))
        body={'order_id':o['id'],'product_sku_id':host,'manager_id':str(i.user),'planned_on':'2026-09-11','notes':'虚构单台'}
        work=ok(post(c,'/works',body));assert work['state']=='draft'
        assert len(work['requirements'])==1 # all fixture parts included; no extra stock issue
        assert work['requirements'][0]['quantity']==1
        assert len(work['included'])==5
        for _ in range(2):ok(post(c,'/works',body))
        assert post(c,'/works',body).json()['code']=='ORDER_CAPACITY_EXCEEDED'

from datetime import datetime,timezone,timedelta
from test_catalog import product

def prepared(engine,database,i,mode="sn",cost="80.00",state="qualified",ownership="own",independent=False):
    o=order(engine,database,i,independent)
    with client(engine,database,i.user,i.a) as c:
        host=o['content']['commercial']['host'];ok(invpost(c,'/tracking/'+host['id'],{'mode':mode}))
        product_sku=product(c,'FINISHED');ok(invpost(c,'/tracking/'+product_sku['id'],{'mode':'sn'}))
        loc=ok(invpost(c,'/locations',{'warehouse':'虚构原料','name':'A'}))
        ok(invpost(c,'/opening/configure',{'cutoff':'2026-01-01','open':True,'reason':'虚构期初','expected_version':0}))
        csv='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'+f'H1,{host["number"]},{loc["id"]},{state},{ownership},{2 if mode=="batch" else 1},{"H1" if mode=="sn" else ""},{"LOT1" if mode=="batch" else ""},{cost},{"confirmed" if cost else "unknown"},CNY,2026-01-01,虚构成本\n'
        if mode=='batch':csv+=f'H2,{host["number"]},{loc["id"]},qualified,own,1,,LOT2,20.00,confirmed,CNY,2026-01-01,虚构第二层\n'
        if independent:
            part=next(x['sku'] for x in o['content']['commercial']['calculation']['technical_lines'] if x['sku']['category']=='memory')
            ok(invpost(c,'/tracking/'+part['id'],{'mode':'batch'}))
            csv+=f'M1,{part["number"]},{loc["id"]},qualified,own,2,,MEM,5.00,confirmed,CNY,2026-01-01,虚构内存成本\n'
        preview=ok(invpost(c,'/opening/preview',{'csv':csv}));assert preview['valid']
        ok(invpost(c,'/opening/'+preview['id']+'/commit',{'expected_version':1,'confirmed':True}))
        body={'order_id':o['id'],'product_sku_id':product_sku['id'],'manager_id':str(i.user),'planned_on':'2026-09-11'}
        return o,loc,body

def confirm(c,w):return ok(post(c,'/works/'+w['id']+'/ready',{'expected_version':w['version'],'confirmed':True}))
def reserve(c,w,quantity=1):return post(c,'/works/'+w['id']+'/reserve',{'expected_version':w['version'],'requirement_id':w['requirements'][0]['id'],'quantity':quantity,'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'reason':'虚构订单预留','confirmed':True})
def test_concurrent_sn_reservation_and_release_protects_old_stock(engine,database,identities):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    i=identities;o,loc,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        works=[confirm(c,ok(post(c,'/works',b))) for _ in range(2)]
    barrier=Barrier(2)
    def run(w):
        with client(engine,database,i.user,i.a) as c:barrier.wait(5);return reserve(c,w)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,works))
    assert sorted(r.status_code for r in results)==[200,409]
    winner=next(r.json() for r in results if r.status_code==200)
    with client(engine,database,i.user,i.a) as c:
        stock=ok(c.get('/api/v1/inventory/stock'));assert stock['available_quantity']==0 and stock['known_cost']=='80.00'
        layer=stock['items'][0]
        target=ok(invpost(c,'/locations',{'warehouse':'虚构原料','name':'B'}))
        r=invpost(c,'/transfers',{'layer_id':layer['layer_id'],'source_location_id':loc['id'],'source_state':'qualified','target_location_id':target['id'],'target_state':'qualified','quantity':1,'expected_version':layer['version'],'confirmed':True,'reason':'不能绕过预留'})
        assert r.json()['code']=='ACTIVE_RESERVATION'
        released=ok(post(c,'/works/'+winner['id']+'/release',{'expected_version':winner['version'],'confirmed':True,'reason':'取消预留'}))
        assert released['requirements'][0]['reserved']==0
        assert ok(c.get('/api/v1/inventory/stock'))['available_quantity']==1

def test_issue_completion_device_and_reverse_cost_continuity(engine,database,identities):
    i=identities;o,loc,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=ok(reserve(c,confirm(c,ok(post(c,'/works',b)))))
        r=w['reservations'][0]
        w=ok(post(c,'/works/'+w['id']+'/issue',{'expected_version':w['version'],'confirmed':True,'reason':'虚构领料','lines':[{'reservation_id':r['id'],'quantity':1}]}))
        assert w['state']=='in_progress' and w['wip_cost']=='80.00'
        stock=ok(c.get('/api/v1/inventory/stock'));assert stock['known_cost']=='80.00' and stock['available_quantity']==0
        body={'expected_version':w['version'],'confirmed':True,'reason':'虚构完工','serial':'FIN-001','location_id':loc['id']};key=str(uuid4())
        completed=ok(post(c,'/works/'+w['id']+'/complete',body,key));device=completed['devices'][0]
        assert completed['wip_cost']=='0.00' and completed['state']=='completed'
        assert ok(post(c,'/works/'+w['id']+'/complete',body,key))['devices'][0]['id']==device['id']
        assert post(c,'/works/'+w['id']+'/complete',body).status_code==409
        d=ok(c.get(P+'/devices/'+device['id']));assert d['inventory_unit_id'] and d['installations'][0]['serial']=='H1'
        assert d['cost']=='80.00' and d['inventory'][0]['state']=='pending'
        assert ok(c.get('/api/v1/inventory/reconciliation'))['stock']['known_cost']=='80.00'
        done_movement=d['movement_id']
        w=ok(post(c,'/works/'+w['id']+'/reverse',{'expected_version':completed['version'],'confirmed':True,'reason':'错误完工更正','movement_id':done_movement}))
        assert w['wip_cost']=='80.00'
        assert ok(c.get(P+'/devices/'+d['id']))['installations'][0]['removed_at'] is not None
        w=ok(post(c,'/works/'+w['id']+'/reverse',{'expected_version':w['version'],'confirmed':True,'reason':'错误领料更正','movement_id':w['issues'][0]['movement_id']}))
        assert w['wip_cost']=='0.00' and w['requirements'][0]['issued']==0
        assert ok(c.get('/api/v1/inventory/stock'))['known_cost']=='80.00'

def test_expiry_worker_revocation_and_cost_visibility(engine,database,identities):
    from sqlalchemy import text
    from silicon.shared.jobs import run_once
    i=identities;o,loc,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=ok(reserve(c,confirm(c,ok(post(c,'/works',b)))))
        with i.owner.begin() as db:
            db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
            db.execute(text("UPDATE asm_reservations SET expires_at=clock_timestamp()-interval '1 second'"))
            db.execute(text("UPDATE jobs SET available_at=clock_timestamp()-interval '1 second' WHERE kind='assembly.expire'"))
        r=post(c,'/works/'+w['id']+'/issue',{'expected_version':w['version'],'confirmed':True,'lines':[{'reservation_id':w['reservations'][0]['id'],'quantity':1}]})
        assert r.json()['code']=='RESERVATION_EXPIRED'
        assert run_once(engine)
        current=ok(c.get(P+'/works/'+w['id']));assert current['reservations'][0]['released']==1
        assert ok(c.get('/api/v1/inventory/stock'))['available_quantity']==1
        w=ok(reserve(c,current))
        with i.owner.begin() as db:
            db.execute(text("DELETE FROM role_permissions WHERE role='admin' AND permission='assembly.release'"))
            db.execute(text("UPDATE jobs SET available_at=clock_timestamp()-interval '1 second' WHERE kind='assembly.expire'"))
        try:
            assert run_once(engine)
            with i.owner.begin() as db:assert db.scalar(text("SELECT count(*) FROM jobs WHERE error_code='TENANT_AUTHORIZATION_DENIED'"))==1
        finally:
            with i.owner.begin() as db:db.execute(text("INSERT INTO role_permissions VALUES ('admin','assembly.release')"))
        with i.owner.begin() as db:db.execute(text("INSERT INTO memberships VALUES (:t,:u,'member',true) ON CONFLICT(tenant_id,user_id) DO UPDATE SET role='member'"),{'t':i.a,'u':i.other})
    with client(engine,database,i.other,i.a) as c:
        assert 'wip_cost' not in ok(c.get(P+'/works/'+w['id']))
        assert post(c,'/works/'+w['id']+'/reverse',{'expected_version':w['version'],'confirmed':True,'movement_id':str(uuid4())}).status_code==403
    with client(engine,database,i.other,i.b) as c:assert c.get(P+'/works/'+w['id']).status_code in (403,404)

def test_completed_device_dependency(engine,database,identities):
    from sqlalchemy import text
    i=identities;o,loc,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=ok(reserve(c,confirm(c,ok(post(c,'/works',b)))))
        w=ok(post(c,'/works/'+w['id']+'/issue',{'expected_version':w['version'],'confirmed':True,'lines':[{'reservation_id':w['reservations'][0]['id'],'quantity':1}]}))
        assert post(c,'/works/'+w['id']+'/cancel',{'expected_version':w['version'],'confirmed':True}).json()['code']=='WORK_STATE'
        w=ok(post(c,'/works/'+w['id']+'/complete',{'expected_version':w['version'],'confirmed':True,'serial':'DEPEND','location_id':loc['id']}))
        d=ok(c.get(P+'/devices/'+w['devices'][0]['id']))
        item=next(x for x in ok(c.get('/api/v1/inventory/stock'))['items'] if x['layer_id']==d['layer_id'])
        target=ok(invpost(c,'/locations',{'warehouse':'成品','name':'B'}))
        move={'layer_id':item['layer_id'],'source_location_id':loc['id'],'source_state':'pending','target_location_id':loc['id'],'target_state':'qualified','quantity':1,'expected_version':item['version'],'confirmed':True,'reason':'提前测试'}
        assert invpost(c,'/transfers',move).json()['code']=='DEVICE_TESTING_NOT_ENABLED'
        m=ok(invpost(c,'/transfers',{**move,'target_location_id':target['id'],'target_state':'pending','reason':'合法成品移库'}))
        r=post(c,'/works/'+w['id']+'/reverse',{'expected_version':w['version'],'confirmed':True,'movement_id':d['movement_id'],'reason':'不可绕过依赖'})
        assert r.status_code==409 and r.json()['code'].startswith('MOVEMENT_DEPENDENCY')
        assert invpost(c,'/movements/'+d['movement_id']+'/reverse',{'expected_version':1,'confirmed':True,'reason':'绕过'}).json()['code']=='USE_ASSEMBLY_REVERSAL'
        assert ok(c.get(P+'/devices?q=H1'))[0]['id']==d['id']

import pytest
@pytest.mark.parametrize('state,ownership,cost',[('pending','own','10.00'),('quarantine','own','10.00'),('qualified','customer','10.00'),('qualified','own','')])
def test_unsuitable_or_unknown_materials_block(engine,database,identities,state,ownership,cost):
    i=identities;_,_,b=prepared(engine,database,i,state=state,ownership=ownership,cost=cost)
    with client(engine,database,i.user,i.a) as c:
        w=confirm(c,ok(post(c,'/works',b)));r=reserve(c,w)
        if not cost:
            w=ok(r)
            response=post(c,'/works/'+w['id']+'/issue',{'expected_version':w['version'],'confirmed':True,'lines':[{'reservation_id':w['reservations'][0]['id'],'quantity':1}]})
            assert response.status_code==422 and response.json()['code'].startswith('UNKNOWN_COST:')
            assert ok(c.get(P+'/works/'+w['id']))['issues']==[]
        else:assert r.status_code==409 and r.json()['code']=='INSUFFICIENT_AVAILABLE_STOCK'

def test_fifo_fixed_sources_and_partial_consumption(engine,database,identities):
    i=identities;_,_,b=prepared(engine,database,i,mode='batch',cost='10.00')
    with client(engine,database,i.user,i.a) as c:
        works=[ok(reserve(c,confirm(c,ok(post(c,'/works',b))))) for _ in range(3)]
        layers=[w['reservations'][0]['layer_id'] for w in works]
        assert layers[0]==layers[1] and layers[2]!=layers[0]
        # Release one earlier allocation; later fixed reservation still costs20, never silently switches to10.
        ok(post(c,'/works/'+works[0]['id']+'/release',{'expected_version':works[0]['version'],'confirmed':True}))
        w=works[2];w=ok(post(c,'/works/'+w['id']+'/issue',{'expected_version':w['version'],'confirmed':True,'lines':[{'reservation_id':w['reservations'][0]['id'],'quantity':1}]}))
        assert w['wip_cost']=='20.00'
        assert ok(c.get('/api/v1/inventory/reconciliation'))['stock']['known_cost']=='40.00'

def test_partial_issue_fixed_configuration_and_atomic_completion(engine,database,identities):
    i=identities;_,loc,b=prepared(engine,database,i,independent=True)
    with client(engine,database,i.user,i.a) as c:
        w=confirm(c,ok(post(c,'/works',b)));assert len(w['requirements'])==2 and len(w['included'])==4
        for req in w['requirements']:
            w=ok(post(c,'/works/'+w['id']+'/reserve',{'expected_version':w['version'],'confirmed':True,'requirement_id':req['id'],'quantity':req['quantity'],'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}))
        memory=next(r for r in w['reservations'] if r['quantity']==2)
        w=ok(post(c,'/works/'+w['id']+'/issue',{'expected_version':w['version'],'confirmed':True,'lines':[{'reservation_id':memory['id'],'quantity':1}]}));assert w['wip_cost']=='5.00'
        assert post(c,'/works/'+w['id']+'/complete',{'expected_version':w['version'],'confirmed':True,'serial':'PARTIAL','location_id':loc['id']}).json()['code']=='MATERIALS_INCOMPLETE'
        w=ok(post(c,'/works/'+w['id']+'/issue',{'expected_version':w['version'],'confirmed':True,'lines':[{'reservation_id':r['id'],'quantity':r['quantity']-r['consumed']} for r in w['reservations'] if r['quantity']>r['consumed']]}))
        assert w['wip_cost']=='90.00'
        w=ok(post(c,'/works/'+w['id']+'/complete',{'expected_version':w['version'],'confirmed':True,'serial':'PARTIAL','location_id':loc['id']}))
        d=ok(c.get(P+'/devices/'+w['devices'][0]['id']));assert d['cost']=='90.00' and len(d['installations'])==2
        assert any(x['batch']=='MEM' and x['serial'] is None and x['quantity']==2 for x in d['installations'])

def test_release_issue_race_and_completion_concurrency(engine,database,identities):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    i=identities;_,loc,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:w=ok(reserve(c,confirm(c,ok(post(c,'/works',b)))))
    barrier=Barrier(2)
    def run(action):
        with client(engine,database,i.user,i.a) as c:
            body={'expected_version':w['version'],'confirmed':True}
            if action=='issue':body['lines']=[{'reservation_id':w['reservations'][0]['id'],'quantity':1}]
            barrier.wait(5);return post(c,'/works/'+w['id']+'/'+action,body)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,['release','issue']))
    assert sorted(r.status_code for r in results)==[200,409]
    with client(engine,database,i.user,i.a) as c:
        w=ok(c.get(P+'/works/'+w['id']))
        if w['state']=='ready':
            w=ok(reserve(c,w));r=w['reservations'][-1]
            r=next(r for r in w['reservations'] if r['released']==0)
            w=ok(post(c,'/works/'+w['id']+'/issue',{'expected_version':w['version'],'confirmed':True,'lines':[{'reservation_id':r['id'],'quantity':1}]}))
    barrier=Barrier(2)
    def finish(n):
        with client(engine,database,i.user,i.a) as c:
            barrier.wait(5);return post(c,'/works/'+w['id']+'/complete',{'expected_version':w['version'],'confirmed':True,'serial':'RACE-'+str(n),'location_id':loc['id']})
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(finish,[1,2]))
    assert sorted(r.status_code for r in results)==[200,409]
    with client(engine,database,i.user,i.a) as c:
        assert len(ok(c.get(P+'/devices')))==1
        assert ok(c.get(P+'/works/'+w['id']+'/reconciliation'))['matches']

def test_rls_installation_unique_revoked_replay_and_context(engine,database,identities):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from silicon.identity.access import tenant_transaction
    i=identities;_,loc,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=ok(reserve(c,confirm(c,ok(post(c,'/works',b)))))
        w=ok(post(c,'/works/'+w['id']+'/issue',{'expected_version':w['version'],'confirmed':True,'lines':[{'reservation_id':w['reservations'][0]['id'],'quantity':1}]}))
        body={'expected_version':w['version'],'confirmed':True,'serial':'UNIQUE','location_id':loc['id']};key=str(uuid4())
        w=ok(post(c,'/works/'+w['id']+'/complete',body,key));d=ok(c.get(P+'/devices/'+w['devices'][0]['id']))
        with engine.begin() as db:
            assert db.scalar(text('SELECT count(*) FROM asm_works'))==0
            assert not db.scalar(text('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user'))
        with pytest.raises(DBAPIError):
            with tenant_transaction(engine,i.user,i.a,'assembly.read','unique') as (db,_):
                db.execute(text('INSERT INTO asm_installations(tenant_id,id,device_id,layer_id,unit_id,quantity,position) SELECT tenant_id,:new,device_id,layer_id,unit_id,quantity,position FROM asm_installations WHERE id=:old'),{'new':uuid4(),'old':d['installations'][0]['id']})
        with i.owner.begin() as db:db.execute(text("DELETE FROM role_permissions WHERE role='admin' AND permission='assembly.complete'"))
        try:assert post(c,'/works/'+w['id']+'/complete',body,key).status_code==403
        finally:
            with i.owner.begin() as db:db.execute(text("INSERT INTO role_permissions VALUES ('admin','assembly.complete')"))
        c.headers['X-Expected-Tenant']=str(i.b)
        assert c.get(P+'/devices/'+d['id']).status_code==409

def test_upgrade_task008_preserves_original_inventory(engine,database,identities):
    import subprocess,sys
    i=identities;_,_,_=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        before=ok(c.get('/api/v1/inventory/stock'));contracts=ok(c.get('/api/v1/contracts/orders'))
    for args in [('downgrade','0009_inventory'),('upgrade','head')]:
        r=subprocess.run([sys.executable,'infra/migrate.py',*args],env=database.env,capture_output=True,text=True,timeout=30)
        assert r.returncode==0,r.stderr
    with client(engine,database,i.user,i.a) as c:
        after=ok(c.get('/api/v1/inventory/stock'));assert after['items']==before['items'] and after['known_cost']==before['known_cost']
        assert ok(c.get('/api/v1/contracts/orders'))==contracts

def test_draft_mapping_can_be_completed_and_source_snapshot_unchanged(engine,database,identities):
    i=identities;o=order(engine,database,i,independent=True)
    with client(engine,database,i.user,i.a) as c:
        host=o['content']['commercial']['host'];ok(invpost(c,'/tracking/'+host['id'],{'mode':'sn'}))
        w=ok(post(c,'/works',{'order_id':o['id'],'product_sku_id':host['id'],'manager_id':str(i.user),'planned_on':'2026-09-11'}))
        assert w['checks'] and len(w['requirements'])==1
        assert post(c,'/works/'+w['id']+'/ready',{'expected_version':w['version'],'confirmed':True}).json()['code']=='MAPPING_INCOMPLETE'
        part=next(x['sku'] for x in o['content']['commercial']['calculation']['technical_lines'] if x['sku']['category']=='memory')
        ok(invpost(c,'/tracking/'+part['id'],{'mode':'batch'}));w=confirm(c,w)
        assert not w['checks'] and len(w['requirements'])==2
        assert ok(c.get('/api/v1/contracts/orders/'+o['id']))==o

def test_aggregate_read_waits_for_whole_issue_commit(engine,database,identities,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from silicon.inventory import service as inv
    i=identities;_,_,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:w=ok(reserve(c,confirm(c,ok(post(c,'/works',b)))))
    inserted=Event();release=Event();started=Event();original=inv.entry
    def gate(db,a,*args,**kw):
        original(db,a,*args,**kw)
        if args[3]=='wip':inserted.set();assert release.wait(8)
    monkeypatch.setattr(inv,'entry',gate)
    def write():
        with client(engine,database,i.user,i.a) as c:return post(c,'/works/'+w['id']+'/issue',{'expected_version':w['version'],'confirmed':True,'lines':[{'reservation_id':w['reservations'][0]['id'],'quantity':1}]})
    # Establish reader identity/session before writer holds the domain lock.
    with client(engine,database,i.other,i.a) as reader:
        def read():started.set();return reader.get(P+'/works/'+w['id'])
        with ThreadPoolExecutor(2) as pool:
            future=pool.submit(write);assert inserted.wait(8);reading=pool.submit(read);assert started.wait(3)
            try:
                from concurrent.futures import TimeoutError
                with pytest.raises(TimeoutError):reading.result(timeout=.2)
            finally:release.set()
            assert future.result(timeout=8).status_code==200
            aggregate=ok(reading.result(timeout=8));assert aggregate['state']=='in_progress' and aggregate['wip_cost']=='80.00' and aggregate['requirements'][0]['issued']==1

def test_reservation_duration_uses_server_time_and_replays_original_expiry(engine,database,identities):
    i=identities;_,_,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=confirm(c,ok(post(c,'/works',b)));now=datetime.now(timezone.utc);key=str(uuid4())
        body={'expected_version':w['version'],'confirmed':True,'requirement_id':w['requirements'][0]['id'],'quantity':1,'duration_hours':24}
        saved=ok(post(c,'/works/'+w['id']+'/reserve',body,key));at=datetime.fromisoformat(saved['reservations'][0]['expires_at'])
        assert timedelta(hours=23,minutes=59)<at-now<timedelta(hours=24,minutes=1)
        assert ok(post(c,'/works/'+w['id']+'/reserve',body,key))['reservations'][0]['expires_at']==saved['reservations'][0]['expires_at']

def test_expired_reservation_can_be_replaced_without_worker(engine,database,identities):
    from sqlalchemy import text
    i=identities;_,_,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=ok(reserve(c,confirm(c,ok(post(c,'/works',b)))))
        with i.owner.begin() as db:
            db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
            db.execute(text("UPDATE asm_reservations SET expires_at=clock_timestamp()-interval '1 second'"))
        refreshed=ok(c.get(P+'/works/'+w['id']))
        assert refreshed['requirements'][0]['missing']==1
        replaced=ok(reserve(c,refreshed))
        assert sum(r['released'] for r in replaced['reservations'])==1
        assert replaced['requirements'][0]['reserved']==1
        assert replaced['requirements'][0]['missing']==0
