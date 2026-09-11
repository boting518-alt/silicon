"""R1 real PostgreSQL/API regressions; only authentication uses a login fixture."""
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from test_identity import identities
from test_contracts import file_root
from test_assembly import prepared, client, ok, post, confirm, invpost
from test_delivery import passing, send, make_ship
from test_service import cmd, get, v, new_work
from test_inventory import setup_purchase


def batch_rma(engine, database, i):
    o, loc, body = prepared(engine, database, i, independent=True)
    with client(engine, database, i.user, i.a) as c:
        w = confirm(c, ok(post(c, '/works', body)))
        for req in w['requirements']:
            w = ok(post(c, '/works/'+w['id']+'/reserve', {'expected_version':w['version'], 'confirmed':True, 'requirement_id':req['id'], 'quantity':req['quantity'], 'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}))
        w = ok(post(c, '/works/'+w['id']+'/issue', {'expected_version':w['version'], 'confirmed':True, 'lines':[{'reservation_id':r['id'], 'quantity':r['quantity']} for r in w['reservations']]}))
        w = ok(post(c, '/works/'+w['id']+'/complete', {'expected_version':w['version'], 'confirmed':True, 'serial':'R1-BATCH', 'location_id':loc['id']}))
        device = w['devices'][0]['id']; passing(c, device); send(c, make_ship(c, o, [device]))
        w = new_work(c, i, device); old = next(x for x in w['installations'] if x['quantity']==2)
        sku = ok(c.get('/api/v1/catalog/skus/'+old['sku_id']))
        csv = 'external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'+f'R1-SPARE,{sku["number"]},{loc["id"]},qualified,own,2,,R1-SPARE,5.00,confirmed,CNY,2026-01-01,虚构备件\n'
        preview=ok(invpost(c,'/opening/preview',{'csv':csv}));assert preview['valid']
        ok(invpost(c,'/opening/'+preview['id']+'/commit',{'expected_version':1,'confirmed':True}))
        w=ok(cmd(c,'/works/'+w['id']+'/reserve',v(w,sku_id=old['sku_id'],quantity=2)))
        w=ok(cmd(c,'/works/'+w['id']+'/issue',v(w,reservation_id=w['reservations'][0]['id'],quantity=2)))
        w=ok(cmd(c,'/works/'+w['id']+'/replace',v(w,old_installation_id=old['id'],issue_id=w['issues'][0]['id'],old_destination='quarantine',location_id=loc['id'],compatibility_basis='虚构同规格内存',manual_compatibility_confirmed=True)))
        _,co,_=setup_purchase(c,i)
        r=ok(cmd(c,'/rmas',{'work_id':w['id'],'expected_version':w['version'],'number':'R1-RMA','supplier_id':co['supplier_id'],'manager_id':str(i.user),'supplier_number':'虚构受理','fault':'虚构故障','expected_on':'2026-10-01','authorization_basis':'客户明确委托','old_part_ids':[w['old_parts'][0]['id']]}))
        r=ok(cmd(c,'/rmas/'+r['id']+'/send',v(r)))
        return w, r, loc


def return_one(c,r,loc):
    before={x['id'] for x in r['lines'][0]['returns']}
    r=ok(cmd(c,'/rmas/'+r['id']+'/return',v(r,line_id=r['lines'][0]['id'],quantity=1,kind='repair',location_id=loc['id'],performed_at='2026-09-11T00:00:00Z',result='虚构原件修复')))
    rr=next(x for x in r['lines'][0]['returns'] if x['id'] not in before)
    return r,rr


def hold(c,r,rr):
    return ok(cmd(c,'/rmas/'+r['id']+'/inspect',v(r,return_id=rr['id'],passed=False,disposition='hold',ownership_basis='继续客户代管隔离')))


def held_balance(c,layer,loc):
    return sum(x['balance'] for x in ok(c.get('/api/v1/inventory/stock'))['items'] if x['layer_id']==layer and x['location_id']==loc['id'] and x['state']=='quarantine')


def dispose_body(w,rr,kind='customer'):
    return v(w,return_id=rr['id'],old_part_id=None,disposition=kind,basis='虚构客户明确确认处置')


def test_same_layer_partial_returns_dispose_individually(engine,database,identities):
    i=identities;w,r,loc=batch_rma(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        r,first=return_one(c,r,loc);r=hold(c,r,first)
        r,second=return_one(c,r,loc);r=hold(c,r,second)
        assert held_balance(c,first['layer_id'],loc)==2
        stock=ok(c.get('/api/v1/inventory/stock'))
        assert all(x['ownership']=='customer' and x['cost_status']=='unknown' for x in stock['items'] if x['layer_id']==first['layer_id'])
        cost=stock['known_cost']
        w=get(c,'/works/'+w['id']);body=dispose_body(w,first);key=str(uuid4())
        w=ok(cmd(c,'/works/'+w['id']+'/dispose',body,key))
        assert held_balance(c,first['layer_id'],loc)==1
        assert ok(cmd(c,'/works/'+w['id']+'/dispose',body,key))==w
        assert cmd(c,'/works/'+w['id']+'/dispose',dispose_body(w,first)).status_code==409
        w=ok(cmd(c,'/works/'+w['id']+'/dispose',dispose_body(w,second,'scrap')))
        assert held_balance(c,first['layer_id'],loc)==0
        returns=get(c,'/rmas/'+r['id'])['lines'][0]['returns']
        assert {x['disposition']['disposition'] for x in returns}=={'customer','scrap'}
        for original in (first,second):
            current=next(x for x in returns if x['id']==original['id'])
            assert all(current[k]==value for k,value in original.items() if k not in ('inspections','disposition'))
        assert ok(c.get('/api/v1/inventory/stock'))['known_cost']==cost
        assert get(c,'/reconciliation')['matches']


def test_return_location_binding_and_missing_stock_fail_closed(engine,database,identities):
    i=identities;w,r,loc=batch_rma(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        other=ok(invpost(c,'/locations',{'warehouse':'虚构原料','name':'R1-B'}))
        r,first=return_one(c,r,loc);r,second=return_one(c,r,other)
        w=get(c,'/works/'+w['id'])
        assert cmd(c,'/works/'+w['id']+'/dispose',dispose_body(w,first)).status_code==409
        # Reverse chronological inspection must still use each receipt's location.
        r=hold(c,r,second);r=hold(c,r,first)
        assert held_balance(c,first['layer_id'],loc)==held_balance(c,first['layer_id'],other)==1
        layer=next(x for x in ok(c.get('/api/v1/inventory/stock'))['items'] if x['layer_id']==first['layer_id'])
        move=ok(invpost(c,'/transfers',{'layer_id':first['layer_id'],'source_location_id':loc['id'],'target_location_id':other['id'],'source_state':'quarantine','target_state':'quarantine','quantity':1,'expected_version':layer['version'],'confirmed':True,'reason':'虚构测试移离原保管库位'}))
        assert held_balance(c,first['layer_id'],loc)==0 and held_balance(c,first['layer_id'],other)==2
        w=get(c,'/works/'+w['id'])
        assert cmd(c,'/works/'+w['id']+'/dispose',dispose_body(w,first)).json()['code']=='SERVICE_PART_DEPENDENCY'
        w=ok(cmd(c,'/works/'+w['id']+'/dispose',dispose_body(w,second)))
        assert held_balance(c,first['layer_id'],other)==1
        layer=next(x for x in ok(c.get('/api/v1/inventory/stock'))['items'] if x['layer_id']==first['layer_id'])
        ok(invpost(c,'/transfers',{'layer_id':first['layer_id'],'source_location_id':other['id'],'target_location_id':loc['id'],'source_state':'quarantine','target_state':'quarantine','quantity':1,'expected_version':layer['version'],'confirmed':True,'reason':'受控移回原保管库位'}))
        w=ok(cmd(c,'/works/'+w['id']+'/dispose',dispose_body(w,first)))
        assert held_balance(c,first['layer_id'],loc)==0


def test_disposition_concurrent_commands_and_tenant_boundaries(engine,database,identities):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from contextlib import ExitStack
    i=identities;w,r,loc=batch_rma(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        r,first=return_one(c,r,loc);r=hold(c,r,first)
        r,second=return_one(c,r,loc);r=hold(c,r,second)
        w=get(c,'/works/'+w['id'])
    # Independent authenticated sessions/connections, finite synchronization and joins.
    def race(returns):
        barrier=Barrier(2)
        with ExitStack() as stack:
            clients=[stack.enter_context(client(engine,database,i.user,i.a)) for _ in range(2)]
            def run(n):
                barrier.wait(5)
                return cmd(clients[n],'/works/'+w['id']+'/dispose',dispose_body(w,returns[n]))
            with ThreadPoolExecutor(2) as pool:
                fs=[pool.submit(run,n) for n in range(2)]
                return [f.result(timeout=15) for f in fs]
    # One command wins and the stale expected_version loses, never an overdraft.
    results=race([first,second]);assert sorted(x.status_code for x in results)==[200,409]
    with client(engine,database,i.user,i.a) as c:
        assert held_balance(c,first['layer_id'],loc)==1
        rr=get(c,'/rmas/'+r['id'])['lines'][0]['returns']
        remaining=next(x for x in rr if not x['disposition'])
        w=get(c,'/works/'+w['id'])
    results=race([remaining,remaining]);assert sorted(x.status_code for x in results)==[200,409]
    with client(engine,database,i.user,i.a) as c:
        w=get(c,'/works/'+w['id']);assert held_balance(c,first['layer_id'],loc)==0
        assert cmd(c,'/works/'+w['id']+'/dispose',dispose_body(w,remaining)).status_code==409
        assert get(c,'/reconciliation')['matches']
    with client(engine,database,i.other,i.b) as c:
        assert cmd(c,'/works/'+w['id']+'/dispose',dispose_body(w,first)).status_code==404


def test_cross_work_and_revoked_permission_disposition_rejected(engine,database,identities):
    from sqlalchemy import text
    i=identities;w,r,loc=batch_rma(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        r,rr=return_one(c,r,loc);r=hold(c,r,rr)
        # A second real delivered device/work under the same order, not a forged row.
        order=ok(c.get('/api/v1/contracts/orders/'+w['order_id']))
        source=ok(c.get('/api/v1/assembly/devices/'+w['device_id']))
        rows=[]
        for n,install in enumerate(source['installations']):
            if install['removed_at']:continue
            sku=ok(c.get('/api/v1/catalog/skus/'+install['sku_id']))
            is_host=sku['category']=='host'
            rows.append(f'R1-OTHER-{n},{sku["number"]},{loc["id"]},qualified,own,{install["quantity"]},{"R1-OTHER-HOST" if is_host else ""},{"" if is_host else "R1-OTHER-MEM"},5.00,confirmed,CNY,2026-01-01,虚构另一设备')
        csv='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'+'\n'.join(rows)+'\n'
        preview=ok(invpost(c,'/opening/preview',{'csv':csv}));assert preview['valid'],preview
        ok(invpost(c,'/opening/'+preview['id']+'/commit',{'expected_version':1,'confirmed':True}))
        other=confirm(c,ok(post(c,'/works',{'order_id':order['id'],'product_sku_id':source['product']['id'],'manager_id':str(i.user),'planned_on':'2026-09-11'})))
        for req in other['requirements']:
            other=ok(post(c,'/works/'+other['id']+'/reserve',{'expected_version':other['version'],'confirmed':True,'requirement_id':req['id'],'quantity':req['quantity'],'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}))
        other=ok(post(c,'/works/'+other['id']+'/issue',{'expected_version':other['version'],'confirmed':True,'lines':[{'reservation_id':x['id'],'quantity':x['quantity']} for x in other['reservations']]}))
        other=ok(post(c,'/works/'+other['id']+'/complete',{'expected_version':other['version'],'confirmed':True,'serial':'R1-OTHER','location_id':loc['id']}))
        device=other['devices'][0]['id'];passing(c,device);send(c,make_ship(c,order,[device]))
        other=new_work(c,i,device)
        assert cmd(c,'/works/'+other['id']+'/dispose',dispose_body(other,rr)).status_code==404
        assert held_balance(c,rr['layer_id'],loc)==1
        w=get(c,'/works/'+w['id']);body=dispose_body(w,rr);key=str(uuid4())
        ok(cmd(c,'/works/'+w['id']+'/dispose',body,key))
        with i.owner.begin() as db:db.execute(text("DELETE FROM role_permissions WHERE role='admin' AND permission='service.rma'"))
        try:assert cmd(c,'/works/'+w['id']+'/dispose',body,key).status_code==403
        finally:
            with i.owner.begin() as db:db.execute(text("INSERT INTO role_permissions VALUES('admin','service.rma')"))
