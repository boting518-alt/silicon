"""Real PG/API analytics; authentication fixture only, never mock database."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from test_identity import identities
from test_contracts import client,file_root
from test_assembly import order
from test_inventory import ok
from test_finance import new_plan,new_cash,alloc,get
P='/api/v1/analytics'
def filters():
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date()
    return {'start':str(today.replace(month=1,day=1)),'end':str(today+timedelta(days=1)),'as_of':str(today)}
def test_contract_cash_and_plans_do_not_multiply(engine,database,identities):
    i=identities;o=order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        source=get(c,'sources')[0];p=new_plan(c,source,'100');cash=new_cash(c,source,'60');ok(alloc(c,cash,(p,'40')))
        report=ok(c.get(P+'/overview',params=filters()))
        metrics={x['id']:x for x in report['metrics']}
        assert metrics['contracts']['value']=='300.00'
        assert metrics['contract_count']['value']=='1'
        assert metrics['receivables']['value']=='60.00'
        assert metrics['receipts']['value']=='60.00'
        details=ok(c.get(P+'/details',params={**filters(),'metric':'contracts','snapshot':report['snapshot']}))
        assert details['total']==1 and details['items'][0]['value']=='300.00'

from decimal import Decimal
from sqlalchemy import text,event
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from test_finance import cmd,version,new_refund
from silicon.analytics.time import day
from silicon.analytics.regions import normalize

def report(c,**kwargs):return ok(c.get(P+'/overview',params={**filters(),**kwargs}))
def metrics(r):return {m['id']:m for m in r['metrics']}
def detail(c,r,id,**kwargs):return c.get(P+'/details',params={**{k:v for k,v in r['filters'].items() if v is not None},'metric':id,'snapshot':r['snapshot'],**kwargs})

def test_timezone_and_calendar_boundaries(engine,database,identities):
    assert str(day('2026-08-31T16:00:00Z'))=='2026-09-01'
    assert str(day('2026-08-31T15:59:59Z'))=='2026-08-31'
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0]
        new_cash(c,s,'11.11',occurred_at='2026-08-31T15:59:59Z')
        new_cash(c,s,'22.22',occurred_at='2026-08-31T16:00:00Z')
        new_cash(c,s,'33.33',occurred_at='2026-09-01T16:00:00Z')
        r=report(c,start='2026-09-01',end='2026-09-02')
        assert metrics(r)['receipts']['value']=='22.22'
        assert c.get(P+'/overview',params={**filters(),'end':'2027-01-01'}).status_code==422
        assert c.get(P+'/overview',params={**filters(),'start':filters()['end']}).status_code==422

def fixture_date(i,table,id,column,date):
    """Isolated fictional timeline setup, NOT a production history-editing path.
    Owner adjusts fixture clock only; immutable triggers remain active afterward.
    """
    assert table in {'analytics_confirmations','fin_allocations','fin_reversals','fin_adjustments','fin_adjustment_corrections'}
    assert column in {'created_at','confirmed_at'}
    with i.owner.begin() as db:
        db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
        db.execute(text(f'ALTER TABLE {table} DISABLE TRIGGER frozen'))
        db.execute(text(f'UPDATE {table} SET {column}=:at WHERE id=:id'),{'at':date,'id':id})
        db.execute(text(f'ALTER TABLE {table} ENABLE TRIGGER frozen'))

def test_historical_allocations_refunds_reversals_and_retention(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];p=new_plan(c,s,'100');ret=new_plan(c,s,'50',retention=True,release_condition='待验收释放',due_date=None)
        cash=new_cash(c,s,'100');allocated=ok(alloc(c,cash,(p,'40')));aid=allocated['allocations'][0]['id']
        for x in (p,ret,cash):fixture_date(i,'analytics_confirmations',x['id'],'confirmed_at','2026-01-01T00:00:00Z')
        fixture_date(i,'fin_allocations',aid,'created_at','2026-02-01T00:00:00Z')
        assert metrics(report(c,as_of='2026-01-31'))['receivables']['value']=='150.00'
        assert metrics(report(c,as_of='2026-02-01'))['receivables']['value']=='110.00'
        assert metrics(report(c,as_of='2026-02-01'))['overdue_receivables']['value']=='60.00'
        age=metrics(report(c,as_of='2026-02-01'))['receivable_age']['groups']
        assert next(x for x in age if x['key']=='待释放/到期日未知')['value']=='50.00'
        freed=ok(cmd(c,'/allocations/'+aid+'/reverse',version(allocated)))
        with i.owner.begin() as db:
            db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
            rid=db.scalar(text('SELECT id FROM fin_reversals WHERE allocation_id=:id'),{'id':aid})
        fixture_date(i,'fin_reversals',rid,'created_at','2026-03-01T00:00:00Z')
        assert metrics(report(c,as_of='2026-02-28'))['receivables']['value']=='110.00'
        assert metrics(report(c,as_of='2026-03-01'))['receivables']['value']=='150.00'
        refund=new_refund(c,freed,'20');refund=ok(cmd(c,'/refunds/'+refund['id']+'/confirm',version(refund,cash_version=freed['version'])))
        fixture_date(i,'analytics_confirmations',refund['id'],'confirmed_at','2026-01-02T00:00:00Z')
        assert metrics(report(c,as_of='2026-01-01'))['net_cash']['value']=='100.00'
        assert metrics(report(c,as_of='2026-01-02'))['net_cash']['value']=='80.00'
        ok(cmd(c,'/refunds/'+refund['id']+'/reverse',version(refund)))
        with i.owner.begin() as db:
            db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
            rid=db.scalar(text('SELECT id FROM fin_reversals WHERE refund_id=:id'),{'id':refund['id']})
        fixture_date(i,'fin_reversals',rid,'created_at','2026-04-01T00:00:00Z')
        assert metrics(report(c,as_of='2026-03-31'))['net_cash']['value']=='80.00'
        assert metrics(report(c,as_of='2026-04-01'))['net_cash']['value']=='100.00'
        current=metrics(report(c));summary=get(c,'summary')
        assert current['receivables']['value']==summary['receivable']
        assert current['net_cash']['value']==summary['net_cash_flow']

def test_missing_old_confirmation_is_unavailable_not_zero(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        p=new_plan(c,get(c,'sources')[0],'100')
        with i.owner.begin() as db:
            db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
            db.execute(text('ALTER TABLE analytics_confirmations DISABLE TRIGGER frozen'))
            db.execute(text('DELETE FROM analytics_confirmations WHERE id=:id'),{'id':p['id']})
            db.execute(text('ALTER TABLE analytics_confirmations ENABLE TRIGGER frozen'))
        m=metrics(report(c,as_of='2026-01-31'))['receivables'];assert m['value'] is None and m['status']=='unavailable'
        assert metrics(report(c))['receivables']['value']=='100.00'
        assert metrics(report(c))['receivables']['status']=='partial'

def test_regions_customer_rank_pagination_and_snapshot_change(engine,database,identities):
    from uuid import uuid4
    from test_crm import payload
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        for n,province in enumerate(['上海市','海外','未知城市']):
            b=payload();b.update(number='REGION-'+str(n),name='虚构地区客户'+str(n),province=province)
            assert c.post('/api/v1/crm/customers',json=b,headers={'Idempotency-Key':str(uuid4())}).status_code==201
        r=report(c);m=metrics(r)
        assert normalize('上海市')=='310000' and normalize('猜测北京路')=='unknown'
        for key in ('contracts','customer_distribution','net_delivery'):
            assert sum((Decimal(g['value']) for g in m[key]['groups']),Decimal(0))==Decimal(m[key]['value'])
        ds=[ok(detail(c,r,'customer_distribution',page=n,page_size=1)) for n in range(1,5)]
        assert len({d['items'][0]['id'] for d in ds})==4
        assert detail(c,r,'contracts',sort='random()').status_code==422
        assert detail(c,r,'contracts',page_size=101).status_code==422
        new_cash(c,get(c,'sources')[0],'1')
        assert detail(c,r,'contracts').json()['code']=='REPORT_CHANGED'
        filtered=report(c,region='overseas');assert metrics(filtered)['customer_distribution']['value']=='1'
        assert metrics(filtered)['payables']['status']=='not_applicable'

def test_domain_permissions_revoke_tenant_and_row_scope(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];new_plan(c,s,'100');new_cash(c,s,'20');r=report(c)
        with i.owner.begin() as db:db.execute(text("DELETE FROM role_permissions WHERE role='admin' AND permission IN('finance.read','inventory.cost')"))
        try:
            m=metrics(report(c));assert m['contracts']['value']=='300.00'
            for k in ('receivables','receipts','inventory_known_cost','inventory_unknown'):
                assert m[k]['value'] is None and m[k]['groups']==[] and not m[k]['drillable']
            assert detail(c,r,'receivables').status_code==403
        finally:
            with i.owner.begin() as db:db.execute(text("INSERT INTO role_permissions VALUES('admin','finance.read'),('admin','inventory.cost')"))
        try:
            with i.owner.begin() as db:db.execute(text("UPDATE roles SET data_scope='own' WHERE name='admin'"),{'t':i.a,'u':i.user})
            m=metrics(report(c));assert m['contracts']['value']=='300.00' and m['inventory_quantity']['status']=='not_applicable'
            with i.owner.begin() as db:
                db.execute(text('INSERT INTO memberships(tenant_id,user_id,role,active) VALUES(:t,:u,\'admin\',true) ON CONFLICT DO NOTHING'),{'t':i.a,'u':i.other})
                db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
                db.execute(text('UPDATE crm_customers SET owner_id=:u'),{'u':i.other})
            assert metrics(report(c))['contracts']['value']=='0.00'
            with client(engine,database,i.other,i.b) as c:assert metrics(report(c))['contracts']['value']=='0.00'
        finally:
            with i.owner.begin() as db:db.execute(text("UPDATE roles SET data_scope='all' WHERE name='admin'"))


def test_repeatable_projection_and_changed_details(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as seed:
        s=get(seed,'sources')[0];new_cash(seed,s,'10')
    entered=Event();release=Event();started=Event();once=[False]
    def pause(conn,cursor,statement,parameters,context,many):
        if 'SELECT * FROM crm_customers WHERE tenant_id=' in statement and not once[0]:
            once[0]=True;entered.set();assert release.wait(10)
    # Application creates a distinct engine per client. Attach at Engine class to
    # synchronize the exact projection query after the shared transaction guards.
    from sqlalchemy.engine import Engine
    event.listen(Engine,'before_cursor_execute',pause)
    def read():
        with client(engine,database,i.user,i.a) as c:return report(c)
    def write():
        with client(engine,database,i.user,i.a) as c:
            started.set();return new_cash(c,s,'20')
    try:
        with ThreadPoolExecutor(2) as pool:
            reading=pool.submit(read);assert entered.wait(10)
            writing=pool.submit(write);assert started.wait(10)
            assert not writing.done();release.set();old=reading.result(15);writing.result(15)
    finally:release.set();event.remove(Engine,'before_cursor_execute',pause)
    assert metrics(old)['receipts']['value']=='10.00'
    with client(engine,database,i.user,i.a) as c:
        assert metrics(report(c))['receipts']['value']=='30.00'
        assert detail(c,old,'receipts').json()['code']=='REPORT_CHANGED'

def test_inventory_delivery_cost_and_age_reconcile(engine,database,identities):
    from test_delivery import setup,passing,send,make_ship,cmd as ship_cmd
    i=identities;o,loc,ids=setup(engine,database,i,3)
    with client(engine,database,i.user,i.a) as c:
        for id in ids:passing(c,id)
        first=send(c,make_ship(c,o,ids[:2]));send(c,make_ship(c,o,ids[2:]))
        m=metrics(report(c));assert m['contracts']['value']=='300.00' and m['dispatched']['value']=='3'
        assert m['completion_to_ship']['value'] is not None
        returned=ok(ship_cmd(c,'/shipments/'+first['id']+'/return',{'expected_version':first['version'],'confirmed':True,'line_ids':[first['lines'][0]['id']],'performed_at':'2026-09-11T00:00:00Z','location_id':loc['id'],'reason':'虚构实际退回'}))
        r=report(c);m=metrics(r);stock=ok(c.get('/api/v1/inventory/stock'))
        assert m['returned']['value']=='1' and m['net_delivery']['value']=='2'
        assert m['inventory_known_cost']['value']==stock['known_cost']=='80.00'
        assert m['contracts']['value']=='300.00'
        assert sum(Decimal(x['value']) for x in m['inventory_age_bands']['groups'])==Decimal(m['inventory_quantity']['value'])
        assert Decimal(m['net_delivery']['value'])==returned['progress']['net_delivered']
        assert m['DIO']['value'] is None and m['DSO']['status']=='unavailable'
        assert ok(detail(c,r,'inventory_known_cost'))['total']==1

def test_rma_partial_returns_disposal_and_customer_cost_exclusion(engine,database,identities):
    from test_service_disposition import batch_rma,return_one,hold,dispose_body
    from test_service import cmd as service_cmd,get as service_get
    i=identities;w,r,loc=batch_rma(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        m=metrics(report(c));assert m['rma_outside']['value']=='2'
        r,first=return_one(c,r,loc);r=hold(c,r,first)
        m=metrics(report(c));assert m['rma_outside']['value']=='1' and m['rma_held']['value']=='1'
        r,second=return_one(c,r,loc);r=hold(c,r,second)
        before=metrics(report(c));assert before['rma_outside']['value']=='0' and before['rma_held']['value']=='2'
        w=service_get(c,'/works/'+w['id']);w=ok(service_cmd(c,'/works/'+w['id']+'/dispose',dispose_body(w,first)))
        after=metrics(report(c));assert after['rma_held']['value']=='1'
        assert after['inventory_known_cost']['value']==before['inventory_known_cost']['value']==ok(c.get('/api/v1/inventory/stock'))['known_cost']
        assert Decimal(after['customer_custody']['value'])>=1
        assert service_get(c,'/reconciliation')['matches']

def test_runtime_rls_and_expected_context(engine,database,identities):
    i=identities;order(engine,database,i)
    with engine.begin() as db:
        role=db.execute(text('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one();assert role==(False,False)
        assert db.scalar(text('SELECT count(*) FROM analytics_confirmations'))==0
    with client(engine,database,i.user,i.a) as c:
        c.headers.pop('X-Expected-Tenant');assert c.get(P+'/overview',params=filters()).status_code==428
        c.headers['X-Expected-Tenant']=str(i.b);assert c.get(P+'/overview',params=filters()).status_code==409


def test_bounded_batch_queries_and_plan(engine,database,identities,capsys):
    from sqlalchemy.engine import Engine
    from uuid import uuid4
    import time,json
    i=identities
    with i.owner.begin() as db:
        db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
        db.execute(text("INSERT INTO crm_customers(tenant_id,id,number,name,owner_id,province) SELECT :t,gen_random_uuid(),'PERF-'||n,'虚构客户'||n,:u,'上海' FROM generate_series(1,2000) n"),{'t':i.a,'u':i.user})
        plan=db.execute(text('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT * FROM crm_customers WHERE tenant_id=:t LIMIT 100001'),{'t':i.a}).scalar()
    statements=[]
    def count(conn,cursor,statement,parameters,context,many):statements.append(statement)
    with client(engine,database,i.user,i.a) as c:
        event.listen(Engine,'before_cursor_execute',count)
        try:
            began=time.monotonic();r=report(c);elapsed=time.monotonic()-began
        finally:event.remove(Engine,'before_cursor_execute',count)
        assert metrics(r)['customer_distribution']['value']=='2000'
        assert len(statements)<70
        d=ok(detail(c,r,'customer_distribution',page=80,page_size=25));assert len(d['items'])==25 and d['total']==2000
        print(json.dumps({'fixture_customers':2000,'request_statements':len(statements),'elapsed_seconds':elapsed,'query_plan':plan},default=str))

def test_upgrade_0015_preserves_facts_and_backfills_confirmations(engine,database,identities):
    import sys,subprocess
    from conftest import ROOT,run
    i=identities;env={**database.env,'DATABASE_URL':database.migration_url}
    run(sys.executable,'infra/migrate.py','downgrade','0015_service',cwd=ROOT,env=env)
    order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        source=get(c,'sources')[0];p=new_plan(c,source,'100');cash=new_cash(c,source,'20')
        before=get(c,'summary');run(sys.executable,'infra/migrate.py','upgrade','head',cwd=ROOT,env=env)
        assert get(c,'summary')==before or get(c,'summary')['receivable']==before['receivable']
        assert get(c,'plans',p['id'])==p
        m=metrics(report(c));assert m['receivables']['value']=='100.00' and m['receivables']['status']=='complete'
        with engine.begin() as db:
            db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
            assert db.scalar(text("SELECT count(*) FROM analytics_confirmations WHERE source='audit'"))==2
        new_cash(c,source,'1')
        down=subprocess.run([sys.executable,'infra/migrate.py','downgrade','0015_service'],cwd=ROOT,env=env,text=True,capture_output=True)
        assert down.returncode and 'confirmation time history' in down.stderr
        assert metrics(report(c))['receipts']['value']=='21.00'

def test_adjustment_correction_historical_cutoff(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        p=new_plan(c,get(c,'sources')[0],'100');fixture_date(i,'analytics_confirmations',p['id'],'confirmed_at','2026-01-01T00:00:00Z')
        p=ok(cmd(c,'/plans/'+p['id']+'/adjust',version(p,amount='-20',basis_ref='虚构减价')))
        adjustment=p['adjustments'][0];fixture_date(i,'fin_adjustments',adjustment['id'],'created_at','2026-02-01T00:00:00Z')
        p=ok(cmd(c,'/plans/'+p['id']+'/correct-adjustment',version(p,adjustment_id=adjustment['id'],basis_ref='虚构误减更正')))
        fixture_date(i,'fin_adjustment_corrections',p['corrections'][0]['id'],'created_at','2026-03-01T00:00:00Z')
        assert metrics(report(c,as_of='2026-01-31'))['receivables']['value']=='100.00'
        assert metrics(report(c,as_of='2026-02-28'))['receivables']['value']=='80.00'
        assert metrics(report(c,as_of='2026-03-01'))['receivables']['value']=='100.00'

def test_unknown_cost_and_transfer_preserves_layer_age(engine,database,identities):
    from test_assembly import prepared,invpost
    i=identities;o,loc,b=prepared(engine,database,i,mode='batch')
    with client(engine,database,i.user,i.a) as c:
        sku=o['content']['commercial']['host']
        csv='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'+f'UNKNOWN,{sku["number"]},{loc["id"]},pending,own,1,,UNKNOWN,,unknown,CNY,2026-01-01,虚构未知成本\n'
        p=ok(invpost(c,'/opening/preview',{'csv':csv}));assert p['valid'],p
        ok(invpost(c,'/opening/'+p['id']+'/commit',{'expected_version':1,'confirmed':True}))
        m=metrics(report(c));assert m['inventory_unknown']['value']=='1' and m['inventory_known_cost']['status']=='partial'
        assert m['inventory_known_cost']['value']==ok(c.get('/api/v1/inventory/stock'))['known_cost']
        x=next(x for x in ok(c.get('/api/v1/inventory/stock'))['items'] if x['batch']=='UNKNOWN')
        before=ok(detail(c,report(c),'inventory_age_bands'))
        ok(invpost(c,'/transfers',{'layer_id':x['layer_id'],'source_location_id':x['location_id'],'source_state':x['state'],'target_location_id':x['location_id'],'target_state':'quarantine','quantity':1,'expected_version':x['version'],'confirmed':True,'reason':'虚构移库保留库龄'}))
        after=ok(detail(c,report(c),'inventory_age_bands'))
        assert next(y['date'] for y in before['items'] if y['id'].startswith(x['layer_id']))==next(y['date'] for y in after['items'] if y['id'].startswith(x['layer_id']))=='2026-01-01'

def test_rma_hold_is_physical_state_not_test_pass_boolean(engine,database,identities):
    from test_service_disposition import batch_rma,return_one
    from test_service import cmd as service_cmd,v
    i=identities;w,r,loc=batch_rma(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        r,one=return_one(c,r,loc)
        r=ok(service_cmd(c,'/rmas/'+r['id']+'/inspect',v(r,return_id=one['id'],passed=True,disposition='hold',ownership_basis='测试通过但待客户确认处置')))
        assert metrics(report(c))['rma_held']['value']=='1'
        r,two=return_one(c,r,loc)
        ok(service_cmd(c,'/rmas/'+r['id']+'/inspect',v(r,return_id=two['id'],passed=False,disposition='scrap',ownership_basis='测试失败且客户明确报废')))
        assert metrics(report(c))['rma_held']['value']=='1'

def test_customer_rank_uses_stable_identity_and_number(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];new_plan(c,s,'10');new_plan(c,s,'30')
        m=metrics(report(c))
        a=m['customer_rank']['groups'];b=m['customer_receivable_rank']['groups']
        assert len(a)==len(b)==1 and a[0]['key']==b[0]['key']
        from uuid import UUID
        assert UUID(a[0]['key']) and 'PUB' in a[0]['label']
        assert b[0]['value']=='40.00'
