"""Real PostgreSQL/API inventory acceptance. Login fixture is a substitute only."""
from uuid import uuid4
from test_identity import identities
from test_contracts import client,file_root
from test_catalog import product
P='/api/v1/inventory'
def post(c,path,body,key=None):return c.post(P+path,json=body,headers={'Idempotency-Key':key or str(uuid4())})
def ok(r,status=200):
    assert r.status_code==status,r.text
    return r.json()
def test_supplier_persisted_and_scoped(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        body={'name':'虚构供应商','address':'测试路','contact':'测试联系人','phone':'test@example.invalid','enabled':True}
        s=ok(post(c,'/suppliers',body));assert s['version']==1
        assert ok(c.get(P+'/suppliers'))[0]['name']=='虚构供应商'
        assert ok(post(c,'/suppliers/'+s['id'],{**body,'expected_version':1,'name':'新名称'}))['version']==2
    with client(engine,database,i.other,i.b) as c:assert ok(c.get(P+'/suppliers'))==[]

def setup_purchase(c,i,quantity=5,tracking='sn'):
    sku=product(c,'INV-'+str(uuid4())[:8],'cpu')
    ok(post(c,'/tracking/'+sku['id'],{'mode':tracking,'unit':'piece','expected_version':0}))
    supplier=ok(post(c,'/suppliers',{'name':'虚构供应商'}))
    contract=ok(post(c,'/contracts',{'number':'PC-'+str(uuid4())[:8],'supplier_id':supplier['id'],'buyer':'虚构我方','manager_id':str(i.user),'signing_date':'2026-01-01','lines':[{'sku_id':sku['id'],'quantity':quantity,'unit_price':'100.00','tax_basis':'unconfirmed','due_date':'2026-12-01'}]}))
    active=ok(post(c,'/contracts/'+contract['id']+'/activate',{'expected_version':1,'confirmed':True}))
    order=ok(post(c,'/orders',{'number':'PO-'+str(uuid4())[:8],'contract_id':active['id'],'lines':[{'contract_line_id':active['lines'][0]['id'],'quantity':quantity}]}))
    order=ok(post(c,'/orders/'+order['id']+'/confirm',{'expected_version':1,'confirmed':True}))
    return sku,active,order

def test_contract_orders_bound_to_frozen_quantity(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        sku,contract,order=setup_purchase(c,i)
        assert order['state']=='confirmed' and order['lines'][0]['quantity']==5
        over=post(c,'/orders',{'number':'OVER','contract_id':contract['id'],'lines':[{'contract_line_id':contract['lines'][0]['id'],'quantity':1}]})
        assert over.status_code==409 and over.json()['code']=='CONTRACT_CAPACITY_EXCEEDED'
        assert ok(c.get(P+'/contracts/'+contract['id']))['snapshot']['supplier']['name']=='虚构供应商'

def warehouse(c):
    w=ok(post(c,'/locations',{'warehouse':'虚构仓','name':'A-01'}))
    return w

def test_receipt_partial_inspection_and_conserved_cost(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        sku,contract,order=setup_purchase(c,i);loc=warehouse(c)
        receipt=ok(post(c,'/receipts',{'order_id':order['id'],'received_on':'2026-09-11','location_id':loc['id'],'lines':[{'order_line_id':order['lines'][0]['id'],'quantity':5,'serials':['A1','A2','A3','A4','A5'],'batch':'','cost_status':'confirmed','unit_cost':'80.00','deductible_tax':'0.00','cost_basis':'虚构确认依据'}]}))
        assert ok(c.get(P+'/stock'))['items']==[]
        posted=ok(post(c,'/receipts/'+receipt['id']+'/post',{'expected_version':1,'confirmed':True}))
        stock=ok(c.get(P+'/stock'));assert len(stock['items'])==5 and stock['available_quantity']==0
        moves=[]
        for n,item in enumerate(stock['items']):
            moves.append(ok(post(c,'/transfers',{'layer_id':item['layer_id'],'source_location_id':loc['id'],'source_state':'pending','target_location_id':loc['id'],'target_state':'qualified' if n<4 else 'quarantine','quantity':1,'reason':'虚构质检','confirmed':True,'expected_version':item['version']})))
        stock=ok(c.get(P+'/stock'));assert stock['available_quantity']==4 and stock['known_cost']=='400.00'
        blocked=post(c,'/movements/'+posted['movement_id']+'/reverse',{'reason':'错误收货','confirmed':True,'expected_version':1})
        assert blocked.status_code==409 and blocked.json()['code']=='MOVEMENT_DEPENDENCY'

def test_opening_preview_atomic_dedupe_and_customer_ownership(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        sku=product(c,'OPENING','memory');ok(post(c,'/tracking/'+sku['id'],{'mode':'batch'}));loc=warehouse(c)
        ok(post(c,'/opening/configure',{'cutoff':'2026-01-01','open':True,'reason':'首次启用','expected_version':0}))
        csv='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'
        csv+=f'ROW-1,OPENING,{loc["id"]},qualified,own,3,,LOT-1,10.00,confirmed,CNY,2026-01-01,虚构依据\n'
        csv+=f'ROW-2,OPENING,{loc["id"]},qualified,customer,2,,LOT-2,,unknown,CNY,2026-01-01,客户代管\n'
        preview=ok(post(c,'/opening/preview',{'csv':csv}));assert preview['valid']
        assert ok(c.get(P+'/stock'))['items']==[]
        committed=ok(post(c,'/opening/'+preview['id']+'/commit',{'expected_version':1,'confirmed':True}))
        assert ok(post(c,'/opening/'+preview['id']+'/commit',{'expected_version':1,'confirmed':True}))['id']==committed['id']
        reordered='\n'.join([csv.splitlines()[0],*reversed(csv.splitlines()[1:])])+'\n'
        same=ok(post(c,'/opening/preview',{'csv':reordered}));assert same['id']==preview['id']
        stock=ok(c.get(P+'/stock'));assert stock['available_quantity']==3 and stock['known_cost']=='30.00'
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

def receipt_body(order,loc,serials):return {'order_id':order['id'],'received_on':'2026-09-11','location_id':loc['id'],'lines':[{'order_line_id':order['lines'][0]['id'],'quantity':len(serials),'serials':serials,'cost_status':'confirmed','unit_cost':'80.00','cost_basis':'虚构成本确认'}]}
def test_concurrent_receipts_reverse_replay_and_reconciliation(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        sku,contract,order=setup_purchase(c,i,2);loc=warehouse(c)
        r1=ok(post(c,'/receipts',receipt_body(order,loc,['S1','S2'])))
        r2=ok(post(c,'/receipts',receipt_body(order,loc,['S3','S4'])))
    barrier=Barrier(2)
    def run(r):
        with client(engine,database,i.user,i.a) as c:
            barrier.wait(timeout=5);return post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True})
    with ThreadPoolExecutor(2) as ex:
        futures=[ex.submit(run,r) for r in (r1,r2)];responses=[f.result(timeout=15) for f in futures]
    assert sorted(x.status_code for x in responses)==[200,409]
    posted=next(x.json() for x in responses if x.status_code==200)
    with client(engine,database,i.user,i.a) as c:
        before=ok(c.get(P+'/reconciliation'));assert before['projection_matches'] and before['stock']['known_cost']=='160.00'
        body={'expected_version':1,'reason':'整单错误冲销','confirmed':True};key=str(uuid4())
        rev=ok(post(c,'/movements/'+posted['movement_id']+'/reverse',body,key))
        assert ok(post(c,'/movements/'+posted['movement_id']+'/reverse',body,key))['id']==rev['id']
        assert post(c,'/movements/'+posted['movement_id']+'/reverse',body).status_code==409
        after=ok(c.get(P+'/reconciliation'));assert after['projection_matches'] and after['stock']['items']==[]
        assert ok(c.get(P+'/orders'))[0]['lines'][0]['received']==0

def test_serial_correction_reuses_physical_identity(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        sku,_,order=setup_purchase(c,i,1);loc=warehouse(c)
        r=ok(post(c,'/receipts',receipt_body(order,loc,['Case-SN'])));r=ok(post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}))
        unit=ok(c.get(P+'/stock'))['items'][0]['unit_id']
        ok(post(c,'/movements/'+r['movement_id']+'/reverse',{'expected_version':1,'confirmed':True,'reason':'成本录入错误'}))
        new=receipt_body(order,loc,['Case-SN']);new['lines'][0]['unit_cost']='81.00'
        r=ok(post(c,'/receipts',new));ok(post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}))
        stock=ok(c.get(P+'/stock'));assert stock['items'][0]['unit_id']==unit and stock['known_cost']=='81.00'
from sqlalchemy import text
import pytest

def test_batch_layers_unknown_zero_and_concurrent_transfer(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        sku,_,order=setup_purchase(c,i,5,'batch');loc=warehouse(c);dest=ok(post(c,'/locations',{'warehouse':'虚构仓','name':'B-02'}))
        b=receipt_body(order,loc,[]);b['lines'][0].update(quantity=5,serials=[],batch='B-1',unit_cost='0.00')
        r=ok(post(c,'/receipts',b));ok(post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}))
        item=ok(c.get(P+'/stock'))['items'][0];assert item['unit_cost']=='0.00'
    barrier=Barrier(2)
    body={'layer_id':item['layer_id'],'source_location_id':loc['id'],'source_state':'pending','target_location_id':dest['id'],'target_state':'pending','quantity':4,'reason':'分批移库','confirmed':True,'expected_version':1}
    def run():
        with client(engine,database,i.user,i.a) as c:barrier.wait(timeout=5);return post(c,'/transfers',body)
    with ThreadPoolExecutor(2) as ex:
        fs=[ex.submit(run) for _ in range(2)];rs=[f.result(timeout=15) for f in fs]
    assert sorted(x.status_code for x in rs)==[200,409]
    with client(engine,database,i.user,i.a) as c:
        st=ok(c.get(P+'/stock'));assert sorted(x['balance'] for x in st['items'])==[1,4] and st['known_cost']=='0.00' and st['cost_complete']
        assert ok(c.get(P+'/reconciliation'))['projection_matches']

def test_two_orders_batches_cancellation_and_amendment(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        sku,contract,o=setup_purchase(c,i,5);loc=warehouse(c)
        ok(post(c,'/orders/'+o['id']+'/cancel',{'expected_version':2,'line_id':o['lines'][0]['id'],'quantity':2,'reason':'未到部分调整','confirmed':True}))
        second=ok(post(c,'/orders',{'number':'SECOND','contract_id':contract['id'],'lines':[{'contract_line_id':contract['lines'][0]['id'],'quantity':2}]}))
        assert second['lines'][0]['quantity']==2
        for serials in [['B1'],['B2','B3']]:
            r=ok(post(c,'/receipts',receipt_body(o,loc,serials)));ok(post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}))
        current=next(x for x in ok(c.get(P+'/orders')) if x['id']==o['id']);assert current['lines'][0]['received']==3 and current['lines'][0]['cancelled']==2
        assert post(c,'/orders/'+o['id']+'/cancel',{'expected_version':3,'line_id':o['lines'][0]['id'],'quantity':1,'reason':'超取消','confirmed':True}).status_code==409
        ok(post(c,'/contracts/'+contract['id']+'/amend',{'expected_version':2,'line_id':contract['lines'][0]['id'],'extra_quantity':1,'reason':'明确追加一件','confirmed':True}))
        third=ok(post(c,'/orders',{'number':'THIRD','contract_id':contract['id'],'lines':[{'contract_line_id':contract['lines'][0]['id'],'quantity':1}]}))
        assert third['lines'][0]['quantity']==1
        assert ok(c.get(P+'/contracts/'+contract['id']))['snapshot']==contract['snapshot']

def test_current_permission_context_cost_and_cross_tenant(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        _,contract,o=setup_purchase(c,i,1);loc=warehouse(c);body=receipt_body(o,loc,['P-1']);key=str(uuid4());r=ok(post(c,'/receipts',body,key));ok(post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}))
        wrong=post(c,'/receipts',{**body,'received_on':'2026-01-02'},key);assert wrong.json()['code']=='IDEMPOTENCY_CONFLICT'
        c.headers['X-Expected-Tenant']=str(i.b);assert c.get(P+'/stock').json()['code']=='CONTEXT_CHANGED'
    with client(engine,database,i.other,i.b) as c:
        assert ok(c.get(P+'/stock'))['items']==[]
        assert c.get(P+'/contracts/'+contract['id']).status_code==404
        assert post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}).status_code==404
    with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='member' WHERE tenant_id=:a AND user_id=:u"),{'a':i.a,'u':i.user})
    with client(engine,database,i.user,i.a) as c:
        st=ok(c.get(P+'/stock'));assert 'known_cost' not in st and 'unit_cost' not in st['items'][0]
        assert 'unit_price' not in ok(c.get(P+'/orders'))[0]['lines'][0]
        assert post(c,'/receipts',body,key).status_code==403
    with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:a AND user_id=:u"),{'a':i.a,'u':i.user})
    with client(engine,database,i.user,i.a) as c:assert post(c,'/receipts',body,key).status_code==403

def test_opening_errors_closed_boundary_and_atomicity(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        sku,contract,o=setup_purchase(c,i,1);loc=warehouse(c)
        ok(post(c,'/opening/configure',{'cutoff':'2026-01-01','open':True,'reason':'首次导入','expected_version':0}))
        header='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'
        bad=header+f'X,{sku["number"]},{loc["id"]},qualified,own,1,SN-OPEN,,1.00,confirmed,CNY,2026-01-01,测试\nY,UNKNOWN,{loc["id"]},qualified,own,1,SN-OTHER,,1.00,confirmed,CNY,2026-01-01,测试\n'
        p=ok(post(c,'/opening/preview',{'csv':bad}));assert not p['valid']
        assert post(c,'/opening/'+p['id']+'/commit',{'expected_version':1,'confirmed':True}).status_code==422
        assert ok(c.get(P+'/stock'))['items']==[]
        r=ok(post(c,'/receipts',receipt_body(o,loc,['S1'])))
        assert post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}).json()['code']=='OPENING_BOUNDARY'
        ok(post(c,'/opening/configure',{'cutoff':'2026-01-01','open':False,'reason':'导入完成','expected_version':1}))
        ok(post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}))
        assert post(c,'/opening/configure',{'cutoff':'2026-01-01','open':True,'reason':'请求重开','expected_version':2}).json()['code']=='BUSINESS_ALREADY_POSTED'

def test_attachment_private_frozen_and_original_import_download(engine,database,identities):
    from test_contracts import PDF
    i=identities
    with client(engine,database,i.user,i.a) as c:
        _,_,o=setup_purchase(c,i,1);loc=warehouse(c);r=ok(post(c,'/receipts',receipt_body(o,loc,['FILE-SN'])))
        url=P+'/attachments/receipt/'+r['id']+'?name=proof.pdf&expected_version=1'
        f=ok(c.post(url,content=PDF,headers={'Idempotency-Key':str(uuid4())}));assert c.get(P+'/attachments/'+f['id']+'/download').content==PDF
        bad=c.post(url,content=b'%PDF-1.4\nfake\n%%EOF',headers={'Idempotency-Key':str(uuid4())});assert bad.status_code==422
        ok(post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}))
        assert c.post(url.replace('version=1','version=2'),content=PDF,headers={'Idempotency-Key':str(uuid4())}).status_code==409
    with client(engine,database,i.other,i.b) as c:assert c.get(P+'/attachments/'+f['id']+'/download').status_code==404

def test_upgrade_task007_keeps_signed_contract(engine,database,identities):
    from test_contracts import source,ready,request as conpost
    import subprocess,sys
    i=identities;draft,_=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w,_=ready(c,draft['id'],i);signed=ok(conpost(c,'/'+draft['id']+'/sign',{'expected_version':w['version'],'content_hash':w['content_hash'],'confirmed':True}),201)
    for command in [('downgrade','0008_contracts'),('upgrade','head')]:
        result=subprocess.run([sys.executable,'infra/migrate.py',*command],env=database.env,capture_output=True,text=True,timeout=30)
        assert result.returncode==0,result.stderr
    with client(engine,database,i.user,i.a) as c:assert ok(c.get('/api/v1/contracts/signed/'+signed['id']))==signed

def test_unknown_cost_and_original_supplier_snapshot(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        _,contract,o=setup_purchase(c,i,1);loc=warehouse(c)
        sup=next(s for s in ok(c.get(P+'/suppliers')) if s['id']==contract['supplier_id'])
        ok(post(c,'/suppliers/'+sup['id'],{'name':'变更后的供应商','expected_version':sup['version']}))
        assert ok(c.get(P+'/contracts/'+contract['id']))['snapshot']['supplier']['name']=='虚构供应商'
        body=receipt_body(o,loc,['UNKNOWN-COST']);body['lines'][0].update(cost_status='unknown',unit_cost=None,cost_basis='待财务确认')
        r=ok(post(c,'/receipts',body));ok(post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}))
        st=ok(c.get(P+'/stock'));assert st['known_cost']=='0.00' and st['unknown_quantity']==1 and st['total_cost'] is None and not st['cost_complete']
        assert post(c,'/tracking/'+st['items'][0]['sku_id'],{'mode':'batch','expected_version':1}).json()['code']=='TRACKING_FROZEN'

def test_same_serial_concurrent_different_orders_and_case_preservation(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        _,contract,o=setup_purchase(c,i,2);loc=warehouse(c)
        ok(post(c,'/orders/'+o['id']+'/cancel',{'expected_version':2,'line_id':o['lines'][0]['id'],'quantity':1,'reason':'拆单','confirmed':True}))
        o2=ok(post(c,'/orders',{'number':'SERIAL-SECOND','contract_id':contract['id'],'lines':[{'contract_line_id':contract['lines'][0]['id'],'quantity':1}]}));o2=ok(post(c,'/orders/'+o2['id']+'/confirm',{'expected_version':1,'confirmed':True}))
        r=[ok(post(c,'/receipts',receipt_body(x,loc,['Preserve-a']))) for x in [o,o2]]
    barrier=Barrier(2)
    def run(x):
        with client(engine,database,i.user,i.a) as c:barrier.wait(timeout=5);return post(c,'/receipts/'+x['id']+'/post',{'expected_version':1,'confirmed':True})
    with ThreadPoolExecutor(2) as ex:
        fs=[ex.submit(run,x) for x in r];rs=[f.result(timeout=15) for f in fs]
    assert sorted(x.status_code for x in rs)==[200,409]
    loser=next(r[n] for n,x in enumerate(rs) if x.status_code==409)
    with client(engine,database,i.user,i.a) as c:
        body=receipt_body(o if loser['order_id']==o['id'] else o2,loc,['Preserve-A'])
        other=ok(post(c,'/receipts',body));ok(post(c,'/receipts/'+other['id']+'/post',{'expected_version':1,'confirmed':True}))
        assert {x['serial_raw'] for x in ok(c.get(P+'/stock'))['items']}=={'Preserve-a','Preserve-A'}

def test_rls_no_context_immutable_facts_and_projection_discrepancy(engine,database,identities):
    from silicon.identity.access import tenant_transaction
    from sqlalchemy.exc import DBAPIError
    i=identities
    with client(engine,database,i.user,i.a) as c:
        _,_,o=setup_purchase(c,i,1);loc=warehouse(c);r=ok(post(c,'/receipts',receipt_body(o,loc,['RLS-SN'])));ok(post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}))
        item=ok(c.get(P+'/stock'))['items'][0]
    with engine.begin() as db:
        role=db.execute(text('SELECT rolname,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one();assert role[0]=='silicon_app' and not role[1] and not role[2]
        assert db.scalar(text('SELECT count(*) FROM inv_entries'))==0
    with pytest.raises(DBAPIError):
        with tenant_transaction(engine,i.user,i.a,'inventory.read','immutable-test') as (db,_):db.execute(text('UPDATE inv_entries SET quantity=20'))
    # Owner-only corruption probe verifies discrepancy detection, not normal app mutation.
    with i.owner.begin() as db:
        db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
        assert db.execute(text('UPDATE inv_balances SET quantity=2 WHERE tenant_id=:t AND layer_id=:l'),{'t':i.a,'l':item['layer_id']}).rowcount==1
    with client(engine,database,i.user,i.a) as c:
        result=ok(c.get(P+'/reconciliation'));assert not result['projection_matches'] and result['differences'][0]['ledger_quantity']==1 and result['differences'][0]['projected_quantity']==2
        assert result['stock']['known_cost']=='80.00'
        assert result['differences'][0]['ledger_cost']=='80.00' and result['differences'][0]['projected_cost']=='160.00'
        assert result['cost_projection']['ledger_known_cost']=='80.00' and result['cost_projection']['projected_known_cost']=='160.00'


def test_reverse_dependency_in_order_restores_cost_and_history(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        _,_,o=setup_purchase(c,i,1);loc=warehouse(c);r=ok(post(c,'/receipts',receipt_body(o,loc,['REV-SN'])));r=ok(post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}))
        it=ok(c.get(P+'/stock'))['items'][0]
        move=ok(post(c,'/transfers',{'layer_id':it['layer_id'],'source_location_id':loc['id'],'source_state':'pending','target_location_id':loc['id'],'target_state':'qualified','quantity':1,'reason':'检查合格','confirmed':True,'expected_version':1}))
        before=ok(c.get(P+'/stock'));at=before['as_of']
        body={'expected_version':1,'confirmed':True,'reason':'错误单据逆序恢复'}
        ok(post(c,'/movements/'+move['id']+'/reverse',body));assert ok(c.get(P+'/stock'))['items'][0]['state']=='pending'
        ok(post(c,'/movements/'+r['movement_id']+'/reverse',body));assert ok(c.get(P+'/stock'))['items']==[]
        assert ok(c.get(P+'/stock',params={'as_of':at}))['items'][0]['state']=='qualified'

def test_csv_malformed_location_is_row_error_not_database_failure(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        sku=product(c,'CSV-INVALID','memory');ok(post(c,'/tracking/'+sku['id'],{'mode':'batch'}))
        ok(post(c,'/opening/configure',{'cutoff':'2026-01-01','open':True,'reason':'测试','expected_version':0}))
        data='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\nX,CSV-INVALID,not-a-uuid,pending,own,1,,B,,unknown,CNY,2026-01-01,测试\n'
        result=ok(post(c,'/opening/preview',{'csv':data}));assert not result['valid'] and result['errors']
        assert ok(c.get(P+'/stock'))['items']==[]

def test_closed_opening_rejects_new_preview_and_reverse_checks_version(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        sku,_,o=setup_purchase(c,i,1);loc=warehouse(c)
        ok(post(c,'/opening/configure',{'cutoff':'2026-01-01','open':False,'reason':'不导入期初','expected_version':0}))
        csv='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'+f'X,{sku["number"]},{loc["id"]},pending,own,1,CLOSED-SN,,,unknown,CNY,2026-01-01,测试\n'
        assert post(c,'/opening/preview',{'csv':csv}).json()['code']=='OPENING_CLOSED'
        r=ok(post(c,'/receipts',receipt_body(o,loc,['VERSION-SN'])));r=ok(post(c,'/receipts/'+r['id']+'/post',{'expected_version':1,'confirmed':True}))
        assert post(c,'/movements/'+r['movement_id']+'/reverse',{'expected_version':999,'confirmed':True,'reason':'错误版本'}).json()['code']=='VERSION_CONFLICT'
