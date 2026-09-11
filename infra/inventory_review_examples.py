"""Explicit disposable R1/R2 browser preconditions, never production seeds.

Repository API/session fixtures create data only. Actual upload, activation,
query and download checks subsequently use real OIDC in the browser.
"""
from types import SimpleNamespace
from test_contracts import client
from test_inventory import setup_purchase,warehouse,receipt_body,post,ok

def seed(engine,database,actor,tenant,file_root):
    database.files=str(file_root)
    with client(engine,database,actor,tenant) as c:
        sku,active,order=setup_purchase(c,SimpleNamespace(user=actor),1)
        loc=warehouse(c)
        ok(post(c,'/receipts',receipt_body(order,loc,['REPAIR-RECEIPT'])))
        ok(post(c,'/contracts',{'number':'REPAIR-ATTACH','supplier_id':active['supplier_id'],'buyer':'虚构修复验收买方','manager_id':str(actor),'signing_date':'2026-01-01','lines':[{'sku_id':sku['id'],'quantity':1,'unit_price':'100.00','due_date':'2026-12-01'}]}))
        ok(post(c,'/opening/configure',{'cutoff':'2026-01-01','open':True,'reason':'虚构修复验收期初','expected_version':0}))
        csv='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'+f'REPAIR-OPEN,{sku["number"]},{loc["id"]},qualified,own,1,REPAIR-OPEN,,10.00,confirmed,CNY,2026-01-01,虚构期初成本\n'
        p=ok(post(c,'/opening/preview',{'csv':csv}))
        ok(post(c,'/opening/'+p['id']+'/commit',{'expected_version':1,'confirmed':True}))
        ok(post(c,'/opening/configure',{'cutoff':'2026-01-01','open':False,'reason':'关闭虚构期初','expected_version':1}))
