"""Fictional browser prerequisites through existing APIs, never service facts."""
from types import SimpleNamespace
from uuid import UUID
from finance_examples import seed as finance_seed
from test_contracts import client
from test_delivery import passing,send,make_ship
from test_assembly import ok

def seed(engine,database,actor,tenant,file_root,issuer):
    finance_seed(engine,database,actor,tenant,file_root,issuer)
    with client(engine,database,actor,tenant) as c:
        devices=ok(c.get('/api/v1/assembly/devices'))
        d=devices[0];passing(c,d['id'])
        order=ok(c.get('/api/v1/contracts/orders/'+d['order_id']))
        send(c,make_ship(c,order,[d['id']]))
        from test_inventory import post
        host=order['content']['commercial']['host'];location=ok(c.get('/api/v1/inventory/locations'))[0]
        csv='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'+f'SERVICE-SPARE,{host["number"]},{location["id"]},qualified,own,3,,SVC-LOT,80.00,confirmed,CNY,2026-01-01,虚构售后备件期初\n'
        preview=ok(post(c,'/opening/preview',{'csv':csv}));assert preview['valid']
        ok(post(c,'/opening/'+preview['id']+'/commit',{'expected_version':1,'confirmed':True}))
