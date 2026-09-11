"""R1 real PostgreSQL/API correction lifecycle; login fixture substitutes OIDC only."""
from uuid import uuid4
from test_identity import identities
from test_contracts import file_root
from test_assembly import prepared,client,ok,post,confirm,reserve,P,invpost

def issued_work(c,body):
    w=ok(reserve(c,confirm(c,ok(post(c,'/works',body)))))
    return ok(post(c,'/works/'+w['id']+'/issue',{'expected_version':w['version'],'confirmed':True,'lines':[{'reservation_id':w['reservations'][0]['id'],'quantity':1}]}))

def finish(c,w,location,serial='FIN-001',**extra):
    return post(c,'/works/'+w['id']+'/complete',{'expected_version':w['version'],'confirmed':True,'serial':serial,'location_id':location,**extra})

def undo(c,w):
    return ok(post(c,'/works/'+w['id']+'/reverse',{'expected_version':w['version'],'confirmed':True,'reason':'更正录错库位','movement_id':w['devices'][0]['movement_id']}))

def test_same_serial_completion_correction_retains_physical_identity(engine,database,identities):
    i=identities;_,loc,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=issued_work(c,b);done=ok(finish(c,w,loc['id']))
        original=ok(c.get(P+'/devices/'+done['devices'][0]['id']))
        restored=undo(c,done)
        target=ok(invpost(c,'/locations',{'warehouse':'虚构成品','name':'更正库位'}))
        corrected=ok(finish(c,restored,target['id'],correction_of=original['completion_id']))
        current=ok(c.get(P+'/devices/'+original['id']))
        assert current['inventory_unit_id']==original['inventory_unit_id']
        assert len(ok(c.get(P+'/devices')))==1
        assert current['inventory']==[{'location_id':target['id'],'state':'pending','quantity':1}]
        assert current['completions'][0]['id']==original['completion_id']
        assert current['completions'][0]['reversed_by'] is not None
        assert current['completions'][1]['correction_of']==original['completion_id']
        old_installs=[x for x in current['installations'] if x['completion_id']==original['completion_id']]
        assert [x['id'] for x in old_installs]==[x['id'] for x in original['installations']]
        assert all(x['removed_at'] for x in old_installs)
        assert len([x for x in current['installations'] if x['removed_at'] is None])==1
        assert current['cost']=='80.00' and corrected['wip_cost']=='0.00'
        assert ok(c.get(P+'/works/'+w['id']+'/reconciliation'))['completed_quantity']==1

def test_concurrent_correction_replay_permissions_and_repeated_history(engine,database,identities):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import text
    i=identities;_,loc,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        done=ok(finish(c,issued_work(c,b),loc['id']))
        original=ok(c.get(P+'/devices/'+done['devices'][0]['id']));restored=undo(c,done)
    barrier=Barrier(2)
    body={'expected_version':restored['version'],'confirmed':True,'serial':'FIN-001','location_id':loc['id'],'correction_of':original['completion_id']}
    def attempt(key):
        with client(engine,database,i.user,i.a) as c:
            barrier.wait(5)
            return key,post(c,'/works/'+done['id']+'/complete',body,key)
    with ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(attempt,str(uuid4())) for _ in range(2)]
        results=[f.result(timeout=10) for f in futures]
    assert sorted(r.status_code for _,r in results)==[200,409]
    key,response=next(x for x in results if x[1].status_code==200)
    with client(engine,database,i.user,i.a) as c:
        assert ok(post(c,'/works/'+done['id']+'/complete',body,key))==response.json()
        assert post(c,'/works/'+done['id']+'/complete',{**body,'reason':'另一意图'},key).json()['code']=='IDEMPOTENCY_CONFLICT'
        current=ok(c.get(P+'/devices/'+original['id']))
        assert len(current['completions'])==2 and len(ok(c.get(P+'/devices')))==1
        restored_again=undo(c,response.json())
        assert ok(c.get(P+'/devices/'+original['id']))['cost']=='0.00'
        # An older reversed source must not skip the latest correction history.
        assert finish(c,restored_again,loc['id'],correction_of=original['completion_id']).json()['code']=='CORRECTION_SOURCE_NOT_LATEST'
        done_again=ok(finish(c,restored_again,loc['id'],correction_of=current['completion_id']))
        final=ok(c.get(P+'/devices/'+original['id']))
        assert final['inventory_unit_id']==original['inventory_unit_id'] and len(final['completions'])==3
        assert sum(x['reversed_by'] is None for x in final['completions'])==1
        assert sum(x['removed_at'] is None for x in final['installations'])==1
        assert ok(c.get(P+'/works/'+done['id']+'/reconciliation'))['finished_cost']=='80.00'
        with i.owner.begin() as db:db.execute(text("DELETE FROM role_permissions WHERE role='admin' AND permission='assembly.complete'"))
        try:assert post(c,'/works/'+done['id']+'/complete',body,key).status_code==403
        finally:
            with i.owner.begin() as db:db.execute(text("INSERT INTO role_permissions VALUES ('admin','assembly.complete')"))
        c.headers['X-Expected-Tenant']=str(i.b)
        assert post(c,'/works/'+done['id']+'/complete',body,key).status_code==409
    with client(engine,database,i.other,i.b) as c:assert c.get(P+'/devices/'+original['id']).status_code==404
    with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.other})
    with client(engine,database,i.other,i.a) as c:
        visible=ok(c.get(P+'/devices/'+original['id']))
        assert 'cost' not in visible and len(visible['completions'])==3
        assert post(c,'/works/'+done['id']+'/complete',body,key).status_code==403


def test_correction_rejects_foreign_work_nonreversed_serial_and_dependency(engine,database,identities):
    i=identities;_,loc,b=prepared(engine,database,i,mode='batch')
    with client(engine,database,i.user,i.a) as c:
        first=ok(finish(c,issued_work(c,b),loc['id']));d=ok(c.get(P+'/devices/'+first['devices'][0]['id']))
        second=issued_work(c,b)
        assert finish(c,second,loc['id']).json()['code']=='SERIAL_ALREADY_EXISTS'
        assert finish(c,second,loc['id'],correction_of=d['completion_id']).json()['code']=='CORRECTION_SOURCE_MISMATCH'
        # Existing downstream movement blocks reversal, hence no correction authorization.
        target=ok(invpost(c,'/locations',{'warehouse':'虚构成品','name':'转库'}))
        layer=next(x for x in ok(c.get('/api/v1/inventory/stock'))['items'] if x['layer_id']==d['layer_id'])
        moved=ok(invpost(c,'/transfers',{'layer_id':layer['layer_id'],'source_location_id':loc['id'],'source_state':'pending','target_location_id':target['id'],'target_state':'pending','quantity':1,'expected_version':layer['version'],'confirmed':True,'reason':'后续依赖'}))
        blocked=post(c,'/works/'+first['id']+'/reverse',{'expected_version':first['version'],'confirmed':True,'movement_id':d['movement_id']})
        assert blocked.status_code==409 and blocked.json()['code'].startswith('MOVEMENT_DEPENDENCY')
        assert finish(c,first,loc['id'],correction_of=d['completion_id']).status_code==409
        assert ok(c.get(P+'/devices/'+d['id']))['inventory'][0]['location_id']==target['id']


def test_upgrade_0010_keeps_active_and_reversed_devices(engine,database,identities):
    import subprocess,sys
    from sqlalchemy import text
    i=identities;_,loc,b=prepared(engine,database,i,mode='batch')
    with client(engine,database,i.user,i.a) as c:
        first=ok(finish(c,issued_work(c,b),loc['id']))
        second=ok(finish(c,issued_work(c,b),loc['id'],'FIN-002'));restored=undo(c,second)
        before=ok(c.get('/api/v1/inventory/stock'))
    def migrate(*args):
        r=subprocess.run([sys.executable,'infra/migrate.py',*args],env=database.env,capture_output=True,text=True,timeout=30)
        assert r.returncode==0,r.stderr
    migrate('downgrade','0010_assembly')
    def frozen():
        with i.owner.begin() as db:
            db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
            return {table:list(db.execute(text('SELECT to_jsonb(t) FROM '+table+' t ORDER BY id')).scalars()) for table in ['asm_devices','inv_layers','inv_entries','inv_movements','sales_orders']}
    historical=frozen();migrate('upgrade','head');assert frozen()==historical
    with client(engine,database,i.user,i.a) as c:
        after=ok(c.get('/api/v1/inventory/stock'));assert after['items']==before['items'] and after['known_cost']==before['known_cost']
        active=ok(c.get(P+'/devices/'+first['devices'][0]['id']));old=ok(c.get(P+'/devices/'+second['devices'][0]['id']))
        assert not active['reversed'] and old['reversed']
        assert old['completions'][0]['reversed_by'] and all(x['removed_at'] for x in old['installations'])
        corrected=ok(finish(c,restored,loc['id'],'FIN-002',correction_of=old['completion_id']))
        assert ok(c.get(P+'/devices/'+old['id']))['inventory_unit_id']==old['inventory_unit_id']
        assert corrected['state']=='completed'
    with i.owner.begin() as db:
        assert db.scalar(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname='asm_completions'"))
        assert db.scalar(text("SELECT bool_and(relrowsecurity AND relforcerowsecurity) FROM pg_class WHERE relname IN ('asm_devices','asm_installations','inv_movements')"))

def test_legacy_successful_completion_replays_without_new_intent(engine,database,identities):
    """Reconstruct the documented 0010 command envelope, retaining its original digest."""
    import hashlib,json
    from sqlalchemy import text
    i=identities;_,loc,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=issued_work(c,b);key=str(uuid4())
        body={'expected_version':w['version'],'confirmed':True,'reason':'确认','serial':'FIN-001','location_id':loc['id']}
        done=ok(post(c,'/works/'+w['id']+'/complete',body,key))
        legacy={k:v for k,v in done.items() if k!='completions'}
        digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with i.owner.begin() as db:
            db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
            legacy_key=str(uuid4())
            db.execute(text('INSERT INTO inv_commands SELECT tenant_id,actor_id,operation,:new,:h,CAST(:r AS jsonb) FROM inv_commands WHERE key=:k'),{'new':legacy_key,'h':digest,'r':json.dumps(legacy),'k':key})
        restored=undo(c,done)
        assert ok(post(c,'/works/'+w['id']+'/complete',body,legacy_key))==legacy
        assert ok(c.get(P+'/works/'+w['id']))['state']=='in_progress'
        assert len(ok(c.get(P+'/devices')))==1


def test_old_inventory_cannot_reintroduce_reversed_device(engine,database,identities):
    i=identities;_,loc,b=prepared(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        done=ok(finish(c,issued_work(c,b),loc['id']));restored=undo(c,done)
        # A zero-balance historical device must not be resurrected via opening inventory.
        csv='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'+f'BAD,FINISHED,{loc["id"]},qualified,own,1,FIN-001,,80.00,confirmed,CNY,2026-01-01,fixture\n'
        preview=ok(invpost(c,'/opening/preview',{'csv':csv}));assert not preview['valid']
        assert any(x['code']=='SERIAL_DUPLICATE' for x in preview['errors'])
        ok(invpost(c,'/opening/configure',{'cutoff':'2026-01-01','open':False,'reason':'close fixture opening','expected_version':1}))
        supplier=ok(invpost(c,'/suppliers',{'name':'fictional correction supplier'}))
        contract=ok(invpost(c,'/contracts',{'number':'PC-CORRECTION','supplier_id':supplier['id'],'buyer':'fictional','manager_id':str(i.user),'signing_date':'2026-01-01','lines':[{'sku_id':b['product_sku_id'],'quantity':1,'unit_price':'80.00','tax_basis':'unconfirmed','due_date':'2026-12-01'}]}))
        active=ok(invpost(c,'/contracts/'+contract['id']+'/activate',{'expected_version':1,'confirmed':True}))
        order=ok(invpost(c,'/orders',{'number':'PO-CORRECTION','contract_id':active['id'],'lines':[{'contract_line_id':active['lines'][0]['id'],'quantity':1}]}))
        order=ok(invpost(c,'/orders/'+order['id']+'/confirm',{'expected_version':1,'confirmed':True}))
        receipt=ok(invpost(c,'/receipts',{'order_id':order['id'],'received_on':'2026-09-11','location_id':loc['id'],'lines':[{'order_line_id':order['lines'][0]['id'],'quantity':1,'serials':['FIN-001'],'batch':'','cost_status':'confirmed','unit_cost':'80.00','deductible_tax':'0.00','cost_basis':'fictional'}]}))
        rejected=invpost(c,'/receipts/'+receipt['id']+'/post',{'expected_version':1,'confirmed':True})
        assert rejected.status_code==409 and rejected.json()['code']=='ASSEMBLY_CORRECTION_REQUIRED'
        d=ok(c.get(P+'/devices/'+done['devices'][0]['id']))
        corrected=ok(finish(c,restored,loc['id'],correction_of=d['completion_id']))
        current=ok(c.get(P+'/devices/'+d['id']));layer=next(x for x in ok(c.get('/api/v1/inventory/stock'))['items'] if x['layer_id']==current['layer_id'])
        # New completion layers must retain the original TASK-010 boundary.
        r=invpost(c,'/transfers',{'layer_id':layer['layer_id'],'source_location_id':loc['id'],'source_state':'pending','target_location_id':loc['id'],'target_state':'qualified','quantity':1,'expected_version':layer['version'],'confirmed':True,'reason':'not enabled'})
        assert r.json()['code']=='DEVICE_TESTING_NOT_ENABLED'
