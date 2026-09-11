"""Real PostgreSQL/API finance seams. Only OIDC login is substituted here."""
from uuid import uuid4
from test_identity import identities
from test_contracts import client,file_root
from test_assembly import order
from test_inventory import ok,setup_purchase
P='/api/v1/finance'
def cmd(c,path,body,key=None):return c.post(P+path,json=body,headers={'Idempotency-Key':key or str(uuid4())})
def version(v,**extra):return {'expected_version':v['version'],'confirmed':True,'reason':'虚构业务确认',**extra}
def test_explicit_source_plan_and_cash_are_distinct(engine,database,identities):
    i=identities;o=order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        sources=ok(c.get(P+'/sources'));s=next(x for x in sources if x['direction']=='receivable')
        assert s['order_ids']==[o['id']]
        plan=ok(cmd(c,'/plans',{'direction':'receivable','source_id':s['id'],'node':'首期','amount':s['amount'],'due_date':'2026-10-01'}))
        assert plan['state']=='draft' and plan['effective']=='0.00'
        plan=ok(cmd(c,'/plans/'+plan['id']+'/confirm',version(plan)))
        assert plan['remaining']==s['amount'] and plan['allocated']=='0.00'
        summary=ok(c.get(P+'/summary'));assert summary['received']=='0.00' and summary['receivable']==s['amount']

from decimal import Decimal as D
from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

def get(c,kind,id=None):return ok(c.get(P+'/'+kind+('/'+id if id else '')))
def new_plan(c,s,amount,node=None,**extra):
    p=ok(cmd(c,'/plans',{'direction':s['direction'],'source_id':s['id'],'node':node or str(uuid4()),'amount':amount,'due_date':'2026-01-01',**extra}))
    return ok(cmd(c,'/plans/'+p['id']+'/confirm',version(p)))
def new_cash(c,s,amount,**extra):
    v=ok(cmd(c,'/cash',{'direction':s['direction'],'party_id':s['party_id'],'amount':amount,'occurred_at':'2026-01-01T00:00:00Z','method':'人工登记','account':'虚构账户','notes':'确认线下发生，无银行操作',**extra}))
    return ok(cmd(c,'/cash/'+v['id']+'/confirm',version(v)))
def alloc(c,cash,*items,key=None):return cmd(c,'/cash/'+cash['id']+'/allocate',version(cash,lines=[{'plan_id':p['id'],'expected_version':p['version'],'amount':amount} for p,amount in items]),key)
def new_refund(c,cash,amount,key=None):
    r=ok(cmd(c,'/refunds',{'cash_id':cash['id'],'amount':amount,'occurred_at':'2026-01-02T00:00:00Z','account':'虚构账户','reason':'实退登记'},key))
    return r

def test_nodes_cap_retention_and_source_adjustment(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];key=str(uuid4());body={'source_id':s['id']}
        plans=ok(cmd(c,'/plans/import',body,key));assert ok(cmd(c,'/plans/import',body,key))==plans and len(plans)==2
        assert cmd(c,'/plans/import',body).status_code==409
        for p in plans:ok(cmd(c,'/plans/'+p['id']+'/confirm',version(p)))
        assert get(c,'summary')['receivable']=='300.00'
        p=ok(cmd(c,'/plans',{'direction':'receivable','source_id':s['id'],'node':'重复金额','amount':'1','due_date':'2026-01-01'}))
        assert cmd(c,'/plans/'+p['id']+'/confirm',version(p)).json()['code']=='FIN_SOURCE_CAP_EXCEEDED'
        ok(cmd(c,'/plans/'+p['id']+'/cancel',version(p)))
        # A documented allowance increase neither edits the contract nor recognizes cash.
        adj={'direction':'receivable','source_id':s['id'],'amount':'100','basis_ref':'虚构补充协议','reason':'明确增加约定','confirmed':True,'expected_version':s['version']}
        ok(cmd(c,'/source-adjustments',adj))
        retained=new_plan(c,s,'100','质保金',retention=True,release_condition='验收满一年',due_date=None)
        assert not retained['overdue'] and retained['due_date'] is None
        cash=new_cash(c,s,'100',purpose='advance')
        assert alloc(c,cash,(retained,'100')).json()['code']=='FIN_PLAN_NOT_SETTLEABLE'
        released=ok(cmd(c,'/plans/'+retained['id']+'/release',version(retained,due_date='2026-01-01')))
        assert released['effective']=='100.00' and released['overdue']
        ok(alloc(c,cash,(released,'100')));assert get(c,'summary')['receivable']=='300.00'
        assert get(c,'sources')[0]['base_amount']=='300.00' and get(c,'summary')['received']=='100.00'

def test_multi_allocation_reversal_refund_and_money_conservation(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];p1=new_plan(c,s,'100');p2=new_plan(c,s,'200');c1=new_cash(c,s,'150',purpose='advance');c2=new_cash(c,s,'150')
        key=str(uuid4());allocated=ok(alloc(c,c1,(p1,'100'),(p2,'50'),key=key))
        assert ok(alloc(c,c1,(p1,'100'),(p2,'50'),key=key))==allocated
        p2=get(c,'plans',p2['id']);ok(alloc(c,c2,(p2,'150')))
        assert get(c,'summary')['receivable']=='0.00' and get(c,'summary')['net_cash_flow']=='300.00'
        refund=new_refund(c,allocated,'50')
        assert cmd(c,'/refunds/'+refund['id']+'/confirm',version(refund,cash_version=allocated['version'])).json()['code']=='FIN_REFUND_EXCEEDED'
        line=next(x for x in allocated['allocations'] if x['plan_id']==p2['id'])
        freed=ok(cmd(c,'/allocations/'+line['id']+'/reverse',version(allocated)))
        p2=get(c,'plans',p2['id']);ok(cmd(c,'/plans/'+p2['id']+'/adjust',version(p2,amount='-50',basis_ref='虚构减价协议')))
        r=ok(cmd(c,'/refunds/'+refund['id']+'/confirm',version(refund,cash_version=freed['version'])))
        assert get(c,'summary')['net_cash_flow']=='250.00' and get(c,'summary')['receivable']=='0.00'
        assert get(c,'reconciliation')['matches']
        ok(cmd(c,'/refunds/'+r['id']+'/reverse',version(r)));assert get(c,'summary')['net_cash_flow']=='300.00'
        assert get(c,'cash',c1['id'])['available']=='50.00'

def test_atomic_failure_duplicate_target_precision_and_party_boundaries(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];p=new_plan(c,s,'100');p2=new_plan(c,s,'200');cash=new_cash(c,s,'200')
        assert alloc(c,cash,(p,'50'),(p2,'201')).status_code==409
        assert get(c,'plans',p['id'])['allocated']=='0.00' and get(c,'cash',cash['id'])['version']==cash['version']
        assert alloc(c,cash,(p,'10'),(p,'10')).status_code==422
        # An earlier valid line must roll back when a later target fails remaining validation.
        assert alloc(c,cash,(p2,'50'),(p,'101')).json()['code']=='FIN_REMAINING_EXCEEDED'
        assert get(c,'plans',p2['id'])['allocated']=='0.00'
        _,_,po=setup_purchase(c,i);sp=next(x for x in get(c,'sources') if x['direction']=='payable');ap=new_plan(c,sp,'100')
        assert alloc(c,cash,(ap,'20')).json()['code']=='FIN_PARTY_DIRECTION_MISMATCH'
        for amount in [0,-1,1.25,'0.001','NaN','Infinity','10000000000000000']:
            assert cmd(c,'/plans',{'direction':'receivable','source_id':s['id'],'node':str(uuid4()),'amount':amount,'due_date':'2026-01-01'}).status_code==422
        assert cmd(c,'/plans',{'direction':'receivable','source_id':s['id'],'node':'错币种','amount':'1','currency':'USD'}).status_code==422
        assert get(c,'reconciliation')['matches']

def test_concurrent_allocations_and_refunds_and_confirm_dedup(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];p=new_plan(c,s,'100');cash=[new_cash(c,s,'80') for _ in range(2)]
    def race(fn,values):
        barrier=Barrier(len(values))
        def worker(v):
            with client(engine,database,i.user,i.a) as c:barrier.wait(5);return fn(c,v)
        with ThreadPoolExecutor(len(values)) as pool:
            fs=[pool.submit(worker,v) for v in values];return [f.result(timeout=15) for f in fs]
    results=race(lambda c,v:alloc(c,v,(p,'80')),cash)
    assert sorted(r.status_code for r in results)==[200,409]
    with client(engine,database,i.user,i.a) as c:
        free=next(get(c,'cash',x['id']) for x in cash if get(c,'cash',x['id'])['allocated']=='0.00')
        refunds=[new_refund(c,free,'60') for _ in range(2)]
    results=race(lambda c,r:cmd(c,'/refunds/'+r['id']+'/confirm',version(r,cash_version=free['version'])),refunds)
    assert sorted(r.status_code for r in results)==[200,409]
    with client(engine,database,i.user,i.a) as c:
        assert get(c,'cash',free['id'])['available']=='20.00' and get(c,'reconciliation')['matches']
        # Business reference remains occupied even after controlled reversal.
        first=new_cash(c,s,'10',external_ref='REF-UNIQUE')
        second=ok(cmd(c,'/cash',{'direction':s['direction'],'party_id':s['party_id'],'amount':'10','occurred_at':'2026-01-01T00:00:00Z','method':'人工','account':'虚构账户','external_ref':'REF-UNIQUE','notes':'重复人工录入'}))
        assert cmd(c,'/cash/'+second['id']+'/confirm',version(second)).status_code==409
        ok(cmd(c,'/cash/'+first['id']+'/reverse',version(first)))
        assert cmd(c,'/cash/'+second['id']+'/confirm',version(second)).status_code==409

def test_same_cash_concurrency_and_lost_response_retry(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];plans=[new_plan(c,s,'100') for _ in range(2)];cash=new_cash(c,s,'100')
    barrier=Barrier(2)
    def worker(p):
        with client(engine,database,i.user,i.a) as c:barrier.wait(5);return alloc(c,cash,(p,'80'))
    with ThreadPoolExecutor(2) as pool:
        fs=[pool.submit(worker,p) for p in plans];results=[f.result(timeout=15) for f in fs]
    assert sorted(r.status_code for r in results)==[200,409]
    with client(engine,database,i.user,i.a) as c:
        key=str(uuid4());body={'direction':s['direction'],'party_id':s['party_id'],'amount':'0.30','occurred_at':'2026-01-01T00:00:00Z','method':'人工','account':'测试','notes':'显式无外部流水'}
        first=ok(cmd(c,'/cash',body,key));assert ok(cmd(c,'/cash',body,key))==first
        assert cmd(c,'/cash',{**body,'amount':'0.31'},key).json()['code']=='IDEMPOTENCY_CONFLICT'
        assert len(get(c,'cash'))==2
        vbody=version(first);confirmed=ok(cmd(c,'/cash/'+first['id']+'/confirm',vbody,key))
        assert ok(cmd(c,'/cash/'+first['id']+'/confirm',vbody,key))==confirmed
        assert get(c,'summary')['received']=='100.30'

def invoice_body(s,amount='100',**extra):return {'direction':s['direction'],'party_id':s['party_id'],'number':str(uuid4()),'kind':'人工发票登记','issued_on':'2026-01-01','buyer':'虚构买方','seller':'虚构卖方','amount':amount,'lines':[{'source_id':s['id'],'amount':amount}],**extra}
def test_invoice_partial_red_void_cap_and_no_cash_effect(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];body=invoice_body(s,'200',net_amount='180',tax_amount='20');v=ok(cmd(c,'/invoices',body));v=ok(cmd(c,'/invoices/'+v['id']+'/confirm',version(v)))
        assert v['tax_state']=='manually_registered' and get(c,'summary')['received']=='0.00'
        bad=ok(cmd(c,'/invoices',invoice_body(s,'101')));assert cmd(c,'/invoices/'+bad['id']+'/confirm',version(bad)).json()['code']=='FIN_INVOICE_CAP_EXCEEDED'
        red=ok(cmd(c,'/invoices',invoice_body(s,'50',original_id=v['id'])));red=ok(cmd(c,'/invoices/'+red['id']+'/confirm',version(red)))
        assert get(c,'sources/receivable',s['id'])['invoiced']=='150.00'
        assert cmd(c,'/invoices/'+v['id']+'/reverse',version(v)).json()['code']=='FIN_DOWNSTREAM_DEPENDENCY'
        extra=ok(cmd(c,'/invoices',invoice_body(s,'150')));extra=ok(cmd(c,'/invoices/'+extra['id']+'/confirm',version(extra)))
        assert cmd(c,'/invoices/'+red['id']+'/reverse',version(red)).json()['code']=='FIN_INVOICE_CAP_EXCEEDED'
        ok(cmd(c,'/invoices/'+extra['id']+'/reverse',version(extra)));ok(cmd(c,'/invoices/'+red['id']+'/reverse',version(red)));ok(cmd(c,'/invoices/'+v['id']+'/reverse',version(v)))
        assert get(c,'sources/receivable',s['id'])['invoiced']=='0.00' and get(c,'reconciliation')['matches']
        duplicate=ok(cmd(c,'/invoices',body));assert cmd(c,'/invoices/'+duplicate['id']+'/confirm',version(duplicate)).status_code==409
        assert cmd(c,'/invoices',invoice_body(s,'100',net_amount='90',tax_amount='11')).status_code==422
        assert cmd(c,'/invoices',invoice_body(s,'100',lines=[{'source_id':s['id'],'amount':'50'}])).status_code==422

def test_purchase_advance_multiple_payments_and_supplier_refund(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        setup_purchase(c,i);s=get(c,'sources')[0];assert s['direction']=='payable' and s['amount']=='500.00'
        p1=new_plan(c,s,'200');p2=new_plan(c,s,'300');advance=new_cash(c,s,'300',purpose='advance');pay=new_cash(c,s,'250')
        assert get(c,'summary')['advance_paid']=='300.00'
        ok(alloc(c,advance,(p1,'200'),(p2,'100')));p2=get(c,'plans',p2['id']);pay=ok(alloc(c,pay,(p2,'200')))
        r=new_refund(c,pay,'50');ok(cmd(c,'/refunds/'+r['id']+'/confirm',version(r,cash_version=pay['version'])))
        sums=get(c,'summary');assert sums['payable']=='0.00' and sums['paid']=='550.00' and sums['supplier_refunds']=='50.00' and sums['net_cash_flow']=='-500.00'
        assert get(c,'reconciliation')['matches']

def test_real_return_deallocate_adjust_and_customer_refund(engine,database,identities):
    from test_delivery import setup,passing,make_ship,send,cmd as delivery
    i=identities;o,loc,ids=setup(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=next(x for x in get(c,'sources') if x['direction']=='receivable')
        # Explicit fictional supplementary commercial agreement reaches the task's 1000 example.
        ok(cmd(c,'/source-adjustments',{'direction':'receivable','source_id':s['id'],'expected_version':s['version'],'amount':'700','basis_ref':'虚构补充商业约定1000','reason':'测试示例，不改原报价','confirmed':True}))
        p1=new_plan(c,s,'400');p2=new_plan(c,s,'200');p3=new_plan(c,s,'300');ret=new_plan(c,s,'100',retention=True,release_condition='一年后',due_date=None)
        c1=new_cash(c,s,'600');c1=ok(alloc(c,c1,(p1,'400'),(p2,'200')));c2=new_cash(c,s,'300');ok(alloc(c,c2,(p3,'300')))
        passing(c,ids[0]);sh=send(c,make_ship(c,o,ids));returned=ok(delivery(c,'/shipments/'+sh['id']+'/return',{'expected_version':sh['version'],'confirmed':True,'line_ids':[sh['lines'][0]['id']],'performed_at':'2026-09-11T00:00:00Z','location_id':loc['id'],'reason':'实收虚构退货'}))
        rid=returned['lines'][0]['returns'][0]['id'];p2=get(c,'plans',p2['id']);body=version(p2,amount='-200',basis_ref='商业退货确认',return_id=rid)
        assert cmd(c,'/plans/'+p2['id']+'/adjust',body).json()['code']=='FIN_DEALLOCATE_FIRST'
        line=next(x for x in c1['allocations'] if x['plan_id']==p2['id']);c1=ok(cmd(c,'/allocations/'+line['id']+'/reverse',version(c1)))
        p2=get(c,'plans',p2['id']);adjusted=ok(cmd(c,'/plans/'+p2['id']+'/adjust',version(p2,amount='-200',basis_ref='商业退货确认',return_id=rid)))
        assert cmd(c,'/plans/'+p3['id']+'/adjust',version(get(c,'plans',p3['id']),amount='-1',basis_ref='重复退货',return_id=rid)).status_code==409
        r=new_refund(c,c1,'200');ok(cmd(c,'/refunds/'+r['id']+'/confirm',version(r,cash_version=c1['version'])))
        sums=get(c,'summary');assert sums['net_cash_flow']=='700.00' and sums['receivable']=='100.00' and sums['customer_refunds']=='200.00'
        assert get(c,'plans',ret['id'])['effective']=='100.00' and not get(c,'plans',ret['id'])['overdue']
        assert ok(c.get('/api/v1/delivery/shipments/'+sh['id']))==returned
        assert get(c,'reconciliation')['matches'] and adjusted['effective']=='0.00'

def test_permission_recheck_rls_and_cost_independence(engine,database,identities):
    from sqlalchemy.exc import DBAPIError
    import pytest
    i=identities;o=order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];key=str(uuid4());body={'direction':'receivable','source_id':s['id'],'node':'权限测试','amount':'100','due_date':'2026-01-01'};p=ok(cmd(c,'/plans',body,key))
        with i.owner.begin() as db:db.execute(text("DELETE FROM role_permissions WHERE role='admin' AND permission IN ('inventory.cost','finance.plan')"))
        try:
            assert get(c,'sources')[0]['amount']=='300.00'
            assert cmd(c,'/plans',body,key).status_code==403
        finally:
            with i.owner.begin() as db:db.execute(text("INSERT INTO role_permissions VALUES('admin','inventory.cost'),('admin','finance.plan')"))
        c.headers['X-Expected-Tenant']=str(i.b);assert cmd(c,'/plans',body,key).status_code==409
    with client(engine,database,i.other,i.b) as c:assert c.get(P+'/plans/'+p['id']).status_code==404
    with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.other})
    with client(engine,database,i.other,i.a) as c:
        assert c.get(P+'/summary').status_code==403
        assert c.get('/api/v1/contracts/orders/'+o['id']).status_code==200
        assert c.get('/api/v1/assembly/devices').status_code==200
    with engine.begin() as db:
        assert db.scalar(text('SELECT count(*) FROM fin_plans'))==0
        assert db.scalar(text("SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname=current_user"))
        db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
        with pytest.raises(DBAPIError):db.execute(text("UPDATE fin_plans SET amount=1 WHERE id=:id"),{'id':p['id']})

def test_concurrent_plan_confirmation_cannot_exceed_contract(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];plans=[ok(cmd(c,'/plans',{'direction':'receivable','source_id':s['id'],'node':str(uuid4()),'amount':'200','due_date':'2026-01-01'})) for _ in range(2)]
    barrier=Barrier(2)
    def worker(p):
        with client(engine,database,i.user,i.a) as c:barrier.wait(5);return cmd(c,'/plans/'+p['id']+'/confirm',version(p))
    with ThreadPoolExecutor(2) as pool:
        fs=[pool.submit(worker,p) for p in plans];results=[f.result(timeout=15) for f in fs]
    assert sorted(x.status_code for x in results)==[200,409]
    with client(engine,database,i.user,i.a) as c:assert get(c,'summary')['receivable']=='200.00'

def test_aggregate_read_blocks_write_until_complete_snapshot(engine,database,identities):
    from threading import Event
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    import time
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];p=new_plan(c,s,'100');cash=new_cash(c,s,'100')
    reading=Event();release=Event();once=Event()
    def pause(conn,cursor,statement,parameters,context,executemany):
        if statement.startswith('SELECT * FROM fin_adjustments') and not once.is_set():
            once.set();reading.set();assert release.wait(8)
    event.listen(Engine,'after_cursor_execute',pause)
    def read():
        with client(engine,database,i.user,i.a) as c:return get(c,'plans',p['id'])
    def write():
        with client(engine,database,i.user,i.a) as c:return ok(alloc(c,cash,(p,'100')))
    try:
        with ThreadPoolExecutor(2) as pool:
            old=pool.submit(read);assert reading.wait(5);mutation=pool.submit(write)
            deadline=time.monotonic()+5;waiting=False
            while time.monotonic()<deadline:
                with engine.connect() as db:waiting=bool(db.scalar(text("SELECT 1 FROM pg_stat_activity WHERE usename=current_user AND wait_event='advisory' AND query LIKE '%pg_advisory_xact_lock(%' LIMIT 1")))
                if waiting:break
                time.sleep(.02)
            assert waiting and not mutation.done() # real server wait, not a timeout/failure surrogate
            release.set();v=old.result(timeout=8);mutation.result(timeout=8)
            assert v['version']==p['version'] and v['allocated']=='0.00' and v['allocations']==[]
        with client(engine,database,i.user,i.a) as c:
            v=get(c,'plans',p['id']);assert v['version']==p['version']+1 and v['allocated']=='100.00' and len(v['allocations'])==1
    finally:release.set();event.remove(Engine,'after_cursor_execute',pause)

def test_upgrade_from_0012_preserves_contract_and_nonempty_downgrade_refused(engine,database,identities):
    from conftest import ROOT,run
    import sys
    i=identities;o=order(engine,database,i)
    env={**database.env,'DATABASE_URL':database.migration_url}
    down=run(sys.executable,'infra/migrate.py','downgrade','0012_delivery',cwd=ROOT,env=env)
    assert down.returncode==0,down.stdout+down.stderr
    up=run(sys.executable,'infra/migrate.py','upgrade','head',cwd=ROOT,env=env);assert up.returncode==0,up.stdout+up.stderr
    with client(engine,database,i.user,i.a) as c:
        assert ok(c.get('/api/v1/contracts/orders/'+o['id']))==o
        s=get(c,'sources')[0];new_plan(c,s,'100')
    import subprocess
    blocked=subprocess.run([sys.executable,'infra/migrate.py','downgrade','0012_delivery'],cwd=ROOT,env=env,text=True,capture_output=True)
    assert blocked.returncode!=0 and 'finance history prevents downgrade' in blocked.stderr
    with client(engine,database,i.user,i.a) as c:assert get(c,'summary')['receivable']=='100.00'

def test_cross_party_and_multi_source_invoice_with_replays(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];p=new_plan(c,s,'100')
        from test_crm import payload
        # Existing fictional CRM source helper is not needed: a new customer is created through API.
        customer=ok(c.post('/api/v1/crm/customers',json={'number':'FIN-OTHER','name':'另一虚构客户','contacts':[],'projects':[]},headers={'Idempotency-Key':str(uuid4())}),201)
        other={**s,'party_id':customer['id']};cash=new_cash(c,other,'100')
        assert alloc(c,cash,(p,'1')).json()['code']=='FIN_PARTY_DIRECTION_MISMATCH'
        assert cmd(c,'/invoices',invoice_body(other)).json()['code']=='FIN_PARTY_DIRECTION_MISMATCH'
        # Same supplier, two distinct active contracts; invoice spans both without merging sources.
        sku,co,po=setup_purchase(c,i)
        from test_inventory import post as purchase
        co2=ok(purchase(c,'/contracts',{'number':'FIN-SECOND','supplier_id':co['supplier_id'],'buyer':'虚构买方','manager_id':str(i.user),'signing_date':'2026-01-01','lines':[{'sku_id':sku['id'],'quantity':2,'unit_price':'100','tax_basis':'unconfirmed','due_date':'2026-10-01'}]}))
        co2=ok(purchase(c,'/contracts/'+co2['id']+'/activate',{'expected_version':co2['version'],'confirmed':True}))
        sp=next(x for x in get(c,'sources') if x['id']==co['id']);body=invoice_body(sp,'150',lines=[{'source_id':co['id'],'amount':'50'},{'source_id':co2['id'],'amount':'100'}]);key=str(uuid4())
        invoice=ok(cmd(c,'/invoices',body,key));assert ok(cmd(c,'/invoices',body,key))==invoice
        invoice=ok(cmd(c,'/invoices/'+invoice['id']+'/confirm',version(invoice)))
        assert get(c,'sources/payable',co['id'])['invoiced']=='50.00' and get(c,'sources/payable',co2['id'])['invoiced']=='100.00'
        distinct=ok(cmd(c,'/invoices',invoice_body(sp,'10',lines=[{'source_id':co2['id'],'amount':'10'}]),key))
        assert distinct['id']!=invoice['id'] # same key, distinct source set: independent intent scope
        assert get(c,'summary')['paid']=='0.00' and get(c,'reconciliation')['matches']
