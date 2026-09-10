"""Real PG/HTTP quote seam; only session setup is injected, never pricing/DB."""
from uuid import uuid4
from test_crm import client,payload
from test_identity import identities
from test_catalog import product,package,line,price,publish,send,ok,update_body

Q='/api/v1/quotes'
def command(c,path,body,method='post',key=None):return c.request(method,Q+path,json=body,headers={'Idempotency-Key':key or str(uuid4())})

def fixture(c):
    customer=ok(c.post('/api/v1/crm/customers',json=payload('QUOTE-CUSTOMER'),headers={'Idempotency-Key':str(uuid4())}))
    host=product(c,'Q-HOST');psu=product(c,'Q-PSU','psu')
    bom=publish(c,'boms',package(c,host,[line(psu,2)]))
    publish(c,'price-books',price(c,host,'10.01',valid_from='2020-01-01T00:00:00Z',valid_to='2099-01-01T00:00:00Z'))
    return customer,host,psu,bom

def config(customer,bom,**kw):return dict(name='虚构报价草稿',customer_id=customer['id'],project_id=customer['projects'][0]['id'],bom_id=bom['id'],quantity=3,scope='retail',tax_included=True,additions=[],excluded_sku_ids=[],discount_id=None,**kw)


def test_quote_included_not_charged_persisted_and_server_authoritative(engine,database,identities):
    with client(engine,database,identities.user,identities.a) as c:
        customer,host,psu,bom=fixture(c);body=config(customer,bom)
        calc=ok(command(c,'/evaluate',body),200)
        assert calc['subtotal']=='30.03' and calc['total']=='30.03'
        assert [x['sku_id'] for x in calc['priced_lines']]==[host['id']]
        assert any(x['sku']['id']==psu['id'] and x['charge_mode']=='included' for x in calc['technical_lines'])
        assert calc['sale_ready'] is False and any(x['status']=='UNKNOWN' for x in calc['checks'])
        assert command(c,'/evaluate',{**body,'total':'0.01'}).status_code==422
        saved=ok(command(c,'',body));again=ok(c.get(Q+'/'+saved['id']),200)
        assert again['config']==body and again['saved_calculation']['total']=='30.03'
        assert again['needs_reprice'] is False


def policy(database,tenant,**changes):
    from silicon.shared.db import make_engine
    from silicon.quotes.service import code_hash
    from sqlalchemy import text
    id=uuid4();values=dict(t=tenant,id=id,hash=code_hash(tenant,'FICTIONAL5'),enabled=True,start='2020-01-01T00:00:00Z',end='2099-01-01T00:00:00Z',scope='retail',tax=True,bps=500,minimum='0.00',maximum='9999.00');values.update(changes)
    engine=make_engine(database.migration_url)
    with engine.begin() as db:
        actor=db.scalar(text("SELECT user_id FROM memberships WHERE tenant_id=:t AND role='admin'"),{'t':tenant})
        db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:a,true)"),{'t':str(tenant),'a':str(actor)})
        db.execute(text("INSERT INTO quote_discounts VALUES (:t,:id,:hash,'虚构优惠',1,:enabled,CAST(:start AS timestamptz),CAST(:end AS timestamptz),:scope,:tax,:bps,:minimum,:maximum)"),values)
    engine.dispose();return str(id)


def test_discount_decimal_rounding_caps_removal_and_no_redemption(engine,database,identities):
    with client(engine,database,identities.user,identities.a) as c:
        customer,host,psu,bom=fixture(c);body=config(customer,bom)
        id=policy(database,identities.a)
        resolved=ok(command(c,'/discount',{'code':'FICTIONAL5'}),200);assert resolved['id']==id and 'code' not in resolved
        with_discount={**body,'discount_id':id}
        calc=ok(command(c,'/evaluate',with_discount),200)
        assert (calc['subtotal'],calc['discount_amount'],calc['total'])==('30.03','1.50','28.53')
        saved=ok(command(c,'',with_discount));assert saved['saved_calculation']['total']=='28.53'
        # No reservation or redemption: another independent save is permitted.
        assert ok(command(c,'',with_discount))['saved_calculation']['discount_amount']=='1.50'
        removed=ok(command(c,'/'+saved['id'],{**body,'expected_version':saved['version']},'put'),200)
        assert removed['saved_calculation']['discount_amount']=='0.00'
        from sqlalchemy import text
        from silicon.identity.access import tenant_transaction
        with tenant_transaction(engine,identities.user,identities.a,'quote.read','audit') as (db,_):
            assert db.scalar(text("SELECT count(*) FROM audit_events WHERE action LIKE 'quote.%' AND object_id LIKE '%FICTIONAL5%'"))==0


def test_discount_round_half_up_and_cap(engine,database,identities):
    with client(engine,database,identities.user,identities.a) as c:
        customer,host,psu,bom=fixture(c)
        id=policy(database,identities.a,bps=5000,maximum='5.00')
        body={**config(customer,bom),'quantity':1,'discount_id':id}
        calc=ok(command(c,'/evaluate',body),200)
        assert calc['subtotal']=='10.01' and calc['discount_amount']=='5.00' and calc['total']=='5.01'


def test_missing_prices_retirement_and_replacement_never_credit_base(engine,database,identities):
    with client(engine,database,identities.user,identities.a) as c:
        customer,host,psu,bom=fixture(c);replacement=product(c,'Q-REPLACEMENT','psu')
        body={**config(customer,bom),'quantity':1,'excluded_sku_ids':[psu['id']],'additions':[{'sku_id':replacement['id'],'quantity':2}]}
        missing=ok(command(c,'/evaluate',body),200)
        assert missing['total'] is None and any(x['code']=='PRICE_UNKNOWN' for x in missing['checks'])
        assert ok(command(c,'',body))['saved_calculation']['total'] is None
        publish(c,'price-books',price(c,replacement,'1.23',valid_from='2020-01-01T00:00:00Z',valid_to='2099-01-01T00:00:00Z'))
        complete=ok(command(c,'/evaluate',body),200)
        assert complete['total']=='12.47' # 10.01 full base + 2 * 1.23, never a PSU credit.
        assert any(x['code']=='MISSING_cpu' for x in complete['checks'])
        ok(send(c,'/skus/'+replacement['id'],update_body(replacement,'skus',enabled=False),'put'),200)
        disabled=ok(command(c,'/evaluate',body),200)
        assert disabled['sale_ready'] is False and any(x['code']=='DISABLED_SKU' for x in disabled['checks'])
        assert ok(c.get('/api/v1/catalog/boms/'+bom['id']),200)==bom
        for quantity in [0,-1,1.5,10001]:assert command(c,'/evaluate',{**body,'quantity':quantity}).status_code==422


def test_quote_price_time_boundaries_and_reprice_history(engine,database,identities,monkeypatch):
    from datetime import datetime,timezone
    from silicon.quotes import service
    class Clock:
        instant=datetime(2026,12,31,23,59,59,tzinfo=timezone.utc)
        @classmethod
        def now(cls,tz):return cls.instant
    monkeypatch.setattr(service,'datetime',Clock) # Clock seam only; all DB/auth/pricing are real.
    with client(engine,database,identities.user,identities.a) as c:
        customer=ok(c.post('/api/v1/crm/customers',json=payload('TIME'),headers={'Idempotency-Key':str(uuid4())}))
        host=product(c,'TIME-H');bom=publish(c,'boms',package(c,host,[]));body={**config(customer,bom),'quantity':1}
        old=publish(c,'price-books',price(c,host,'0.00'))
        new=publish(c,'price-books',price(c,host,'0.10',valid_from='2027-01-01T00:00:00Z',valid_to='2028-01-01T00:00:00Z'))
        saved=ok(command(c,'',body));assert saved['saved_calculation']['total']=='0.00'
        Clock.instant=datetime(2027,1,1,tzinfo=timezone.utc)
        reopened=ok(c.get(Q+'/'+saved['id']),200)
        assert reopened['needs_reprice'] and reopened['saved_calculation']['total']=='0.00' and reopened['current_calculation']['total']=='0.10'
        id=policy(database,identities.a)
        rounded=ok(command(c,'/evaluate',{**body,'discount_id':id}),200)
        assert rounded['discount_amount']=='0.01' and rounded['total']=='0.09'
        Clock.instant=datetime(2028,1,1,tzinfo=timezone.utc)
        assert any(x['code']=='PRICE_EXPIRED' for x in ok(command(c,'/evaluate',body),200)['checks'])
        Clock.instant=datetime(2025,12,31,tzinfo=timezone.utc)
        assert any(x['code']=='PRICE_NOT_YET_VALID' for x in ok(command(c,'/evaluate',body),200)['checks'])
        assert ok(c.get('/api/v1/catalog/price-books/'+old['id']),200)==old
        assert ok(c.get('/api/v1/catalog/price-books/'+new['id']),200)==new


def test_quote_permissions_context_and_tenant_links(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        customer,host,psu,bom=fixture(c);body=config(customer,bom);saved=ok(command(c,'',body));id=policy(database,i.a)
        c.post('/api/v1/session/tenant',json={'tenant_id':str(i.b)})
        for path in ['', '/'+saved['id']]:assert c.get(Q+path).json()['code']=='CONTEXT_CHANGED'
        assert command(c,'/evaluate',body).json()['code']=='CONTEXT_CHANGED'
        assert command(c,'',body).json()['code']=='CONTEXT_CHANGED'
    with client(engine,database,i.other,i.b) as c:
        assert c.get(Q+'/'+saved['id']).status_code==404
        assert command(c,'',body).status_code==404
        own=ok(c.post('/api/v1/crm/customers',json=payload('B-CUSTOMER'),headers={'Idempotency-Key':str(uuid4())}))
        assert command(c,'/evaluate',{**body,'customer_id':own['id'],'project_id':own['projects'][0]['id']}).status_code==404
    with client(engine,database,i.user,i.b) as c:
        assert command(c,'/discount',{'code':'FICTIONAL5'}).status_code==403
    from silicon.shared.db import make_engine
    from sqlalchemy import text
    owner=make_engine(database.migration_url)
    with owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE user_id=:u AND tenant_id=:t"),{'u':i.user,'t':i.a})
    owner.dispose()
    with client(engine,database,i.user,i.a) as c:
        assert command(c,'',body).status_code==403
        assert command(c,'/discount',{'code':'FICTIONAL5'}).status_code==403


def test_quote_idempotency_concurrent_edit_and_unlimited_trial(engine,database,identities):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    i=identities
    with client(engine,database,i.user,i.a) as c,client(engine,database,i.user,i.a) as d:
        customer,host,psu,bom=fixture(c);body=config(customer,bom);key=str(uuid4())
        saved=ok(command(c,'',body,key=key));assert ok(command(c,'',body,key=key))==saved
        assert command(c,'',{**body,'name':'changed'},key=key).json()['code']=='IDEMPOTENCY_CONFLICT'
        update={**body,'quantity':2,'expected_version':saved['version']};gate=threading.Barrier(2)
        def run(cl):gate.wait(3);return command(cl,'/'+saved['id'],update,'put').status_code
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(run,c);b=pool.submit(run,d);assert sorted([a.result(),b.result()])==[200,409]
        id=policy(database,i.a);trial={**body,'discount_id':id};gate=threading.Barrier(2)
        def evaluate(cl):gate.wait(3);return command(cl,'/evaluate',trial).status_code
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(evaluate,c);b=pool.submit(evaluate,d);assert [a.result(),b.result()]==[200,200]


import pytest
@pytest.mark.parametrize('change',[{'enabled':False},{'end':'2020-01-02T00:00:00Z'},{'start':'2098-01-01T00:00:00Z'},{'scope':'partner'},{'tax':False},{'minimum':'30.04'}])
def test_discount_conditions_fail_closed(engine,database,identities,change):
    with client(engine,database,identities.user,identities.a) as c:
        customer,host,psu,bom=fixture(c);id=policy(database,identities.a,**change)
        body={**config(customer,bom),'discount_id':id}
        calc=ok(command(c,'/evaluate',body),200)
        assert calc['total'] is None and calc['amount_complete'] is False
        assert any(x['code']=='DISCOUNT_UNAVAILABLE' for x in calc['checks'])
        assert command(c,'/evaluate',{**body,'discount_amount':'100.00'}).status_code==422


def test_quote_nested_current_retirement_and_deferred_project_relation(engine,database,identities):
    from test_crm import update_body as customer_update
    from sqlalchemy import text
    from silicon.identity.access import tenant_transaction
    i=identities
    with client(engine,database,i.user,i.a) as c:
        customer,host,psu,bom=fixture(c);root=product(c,'NESTED-ROOT')
        nested=publish(c,'boms',package(c,root,[line(host,package_version_id=bom['id'])]))
        body={**config(customer,nested),'quantity':1};saved=ok(command(c,'',body))
        # CRM replaces its project rows inside the transaction; same project IDs remain valid.
        updated=ok(c.put('/api/v1/crm/customers/'+customer['id'],json=customer_update(customer,name='客户更新'),headers={'Idempotency-Key':str(uuid4())}),200)
        assert ok(c.get(Q+'/'+saved['id']),200)['config']['project_id']==body['project_id']
        removed=customer_update(updated,projects=[])
        assert c.put('/api/v1/crm/customers/'+customer['id'],json=removed,headers={'Idempotency-Key':str(uuid4())}).status_code==422
        ok(send(c,'/skus/'+psu['id'],update_body(psu,'skus',enabled=False),'put'),200)
        current=ok(c.get(Q+'/'+saved['id']),200)
        assert current['needs_reprice'] and any(x['code']=='DISABLED_SKU' for x in current['current_calculation']['checks'])
        assert ok(c.get('/api/v1/catalog/boms/'+bom['id']),200)==bom
        c.headers.pop('X-Expected-Tenant');assert c.get(Q).status_code==428
    with engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM quote_drafts'))==0
        assert db.execute(text('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()==(False,False)
    with tenant_transaction(engine,i.user,i.a,'quote.read','relation') as (db,_):
        assert db.scalar(text('SELECT count(*) FROM quote_drafts'))==1


def test_required_bom_category_cannot_disappear_on_replacement(engine,database,identities):
    with client(engine,database,identities.user,identities.a) as c:
        customer,host,psu,bom=fixture(c);gpu=product(c,'REQUIRED-GPU','gpu')
        required=publish(c,'boms',package(c,host,[line(psu),line(gpu)]))
        body={**config(customer,required),'excluded_sku_ids':[gpu['id']]}
        calc=ok(command(c,'/evaluate',body),200)
        assert any(x['code']=='MISSING_gpu' and x['status']=='BLOCK' for x in calc['checks'])


def test_quote_aggregate_holds_catalog_read_snapshot_against_sku_writer(engine,database,identities):
    from concurrent.futures import ThreadPoolExecutor
    import threading,time
    from sqlalchemy import event,text
    from sqlalchemy.engine import Engine
    i=identities;paused=threading.Event();release=threading.Event();started=threading.Event();pids={}
    def after(db,cursor,statement,params,ctx,many):
        if not paused.is_set() and statement.startswith('SELECT * FROM quote_drafts'):
            pids['read']=db.connection.driver_connection.info.backend_pid;paused.set();assert release.wait(2)
    with client(engine,database,i.user,i.a) as c,client(engine,database,i.user,i.a) as reader,client(engine,database,i.user,i.a) as writer:
        customer,host,psu,bom=fixture(c);saved=ok(command(c,'',config(customer,bom)))
        event.listen(Engine,'after_cursor_execute',after)
        # before_cursor_execute identifies the waiting writer before the lock is granted.
        def before(db,cursor,statement,params,ctx,many):
            if paused.is_set() and not release.is_set() and statement.startswith('SELECT pg_advisory_xact_lock('):
                pids['write']=db.connection.driver_connection.info.backend_pid;started.set()
        event.listen(Engine,'before_cursor_execute',before)
        try:
            with ThreadPoolExecutor(1,thread_name_prefix='quote-read') as rp,ThreadPoolExecutor(1,thread_name_prefix='quote-write') as wp:
                pending=rp.submit(reader.get,Q+'/'+saved['id']);assert paused.wait(2)
                writing=wp.submit(send,writer,'/skus/'+psu['id'],update_body(psu,'skus',enabled=False),'put')
                try:
                    assert started.wait(1)
                    deadline=time.monotonic()+1
                    blocked=False
                    while time.monotonic()<deadline:
                        with engine.connect() as db:blocked=pids['read'] in db.scalar(text('SELECT pg_blocking_pids(:pid)'),{'pid':pids['write']})
                        if blocked:break
                        time.sleep(.01)
                    assert blocked and not writing.done()
                finally:release.set()
                old=ok(pending.result(2),200);ok(writing.result(2),200)
                assert not any(x['code']=='DISABLED_SKU' for x in old['current_calculation']['checks'])
        finally:
            release.set();event.remove(Engine,'after_cursor_execute',after);event.remove(Engine,'before_cursor_execute',before)
        new=ok(c.get(Q+'/'+saved['id']),200)
        assert new['needs_reprice'] and any(x['code']=='DISABLED_SKU' for x in new['current_calculation']['checks'])


def test_selected_optional_cpu_is_checked_and_excluded_cpu_is_not(engine,database,identities):
    with client(engine,database,identities.user,identities.a) as c:
        customer,host,psu,_=fixture(c)
        cpu_a=product(c,'OPTIONAL-CPU-A','cpu',specs={'socket':'A'})
        cpu_b=product(c,'OPTIONAL-CPU-B','cpu',specs={'socket':'B'})
        rule=ok(send(c,'/rules',{'name':'虚构选择规则','source':'测试资料','socket':'A','power_budget_w':1000}))
        bom=publish(c,'boms',package(c,host,[line(psu,2),line(cpu_a,charge_mode='separate'),line(cpu_b,required=False,charge_mode='separate')],rule_id=rule['id'],kind='bom'))
        for sku in (cpu_a,cpu_b):publish(c,'price-books',price(c,sku,'2.00',valid_from='2020-01-01T00:00:00Z',valid_to='2099-01-01T00:00:00Z'))
        body={**config(customer,bom),'quantity':1}
        selected=ok(command(c,'/evaluate',body),200)
        assert next(x for x in selected['checks'] if x['code']=='socket')['status']=='BLOCK'
        assert selected['total']=='14.01'
        assert next(x for x in selected['technical_lines'] if x['sku']['id']==cpu_b['id'])['required'] is False
        excluded=ok(command(c,'/evaluate',{**body,'excluded_sku_ids':[cpu_b['id']]}),200)
        assert next(x for x in excluded['checks'] if x['code']=='socket')['status']=='PASS'
        assert excluded['total']=='12.01'
        assert cpu_b['id'] not in [x['sku_id'] for x in excluded['priced_lines']]
        assert psu['id'] not in [x['sku_id'] for x in selected['priced_lines']]
        assert ok(c.get('/api/v1/catalog/boms/'+bom['id']),200)==bom


def test_selected_optional_memory_and_categories_preserve_template_requirements(engine,database,identities):
    with client(engine,database,identities.user,identities.a) as c:
        customer,host,psu,_=fixture(c)
        cpu=product(c,'OPT-CPU','cpu',specs={'socket':'A'})
        ram_a=product(c,'REQ-RAM','memory',specs={'memory_generation':'D5'})
        ram_b=product(c,'OPT-RAM','memory',specs={'memory_generation':'D4'})
        gpu=product(c,'REQ-GPU','gpu')
        rule=ok(send(c,'/rules',{'name':'虚构内存规则','source':'测试','socket':'A','memory_generation':'D5','power_budget_w':1000}))
        bom=publish(c,'boms',package(c,host,[line(cpu,required=False),line(ram_a),line(ram_b,required=False),line(psu,2),line(gpu)],rule_id=rule['id']))
        body={**config(customer,bom),'quantity':1}
        value=ok(command(c,'/evaluate',body),200)
        assert next(x for x in value['checks'] if x['code']=='memory_generation')['status']=='BLOCK'
        assert not any(x['code']=='MISSING_cpu' for x in value['checks'])
        assert value['total']=='10.01' # All selected template parts are included.
        without=ok(command(c,'/evaluate',{**body,'excluded_sku_ids':[ram_b['id'],gpu['id']]}),200)
        assert next(x for x in without['checks'] if x['code']=='memory_generation')['status']=='PASS'
        assert any(x['code']=='MISSING_gpu' for x in without['checks'])
        assert ram_b['id'] not in [x['sku']['id'] for x in without['technical_lines']]
        no_cpu=ok(command(c,'/evaluate',{**body,'excluded_sku_ids':[cpu['id']]}),200)
        assert next(x for x in no_cpu['checks'] if x['code']=='socket')['status']=='UNKNOWN'
        assert ok(c.get('/api/v1/catalog/boms/'+bom['id']),200)==bom


@pytest.mark.parametrize(('quantity','status'),[(1,'WARN'),(2,'PASS')])
def test_selected_optional_power_counts_for_capacity_and_completeness(engine,database,identities,quantity,status):
    with client(engine,database,identities.user,identities.a) as c:
        customer,host,_,_=fixture(c)
        psu=product(c,'OPT-POWER','psu',specs={'power_w':1200})
        cpu=product(c,'REQ-CPU','cpu',specs={'socket':'A'})
        rule=ok(send(c,'/rules',{'name':'虚构容量规则','source':'测试','socket':'A','power_budget_w':1000}))
        bom=publish(c,'boms',package(c,host,[line(cpu),line(psu,quantity,required=False)],rule_id=rule['id']))
        body={**config(customer,bom),'quantity':1}
        value=ok(command(c,'/evaluate',body),200)
        assert next(x for x in value['checks'] if x['code']=='POWER')['status']==status
        assert not any(x['code']=='MISSING_psu' for x in value['checks'])
        assert value['total']=='10.01' and [x['sku_id'] for x in value['priced_lines']]==[host['id']]
        excluded=ok(command(c,'/evaluate',{**body,'excluded_sku_ids':[psu['id']]}),200)
        assert next(x for x in excluded['checks'] if x['code']=='POWER')['status']=='BLOCK'
        assert any(x['code']=='MISSING_psu' for x in excluded['checks'])
        assert ok(c.get('/api/v1/catalog/boms/'+bom['id']),200)==bom


def test_identical_create_intents_and_lost_response_replay_are_distinct(engine,database,identities):
    with client(engine,database,identities.user,identities.a) as c:
        customer,_,_,bom=fixture(c);body=config(customer,bom);key=str(uuid4())
        first=ok(command(c,'',body,key=key))
        # Caller loses the first response but retries the same command.
        assert ok(command(c,'',body,key=key))==first
        second=ok(command(c,'',body,key=str(uuid4())))
        assert second['id']!=first['id']
        assert len(ok(c.get(Q),200))==2
        ok(command(c,'/'+second['id'],{**body,'name':'仅修改第二份','expected_version':1},'put'),200)
        assert ok(c.get(Q+'/'+first['id']),200)['config']['name']==body['name']
        assert ok(c.get(Q+'/'+second['id']),200)['version']==2
