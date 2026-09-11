"""Real PG/API service lifecycle; only login uses identity fixtures."""
from uuid import uuid4
from test_identity import identities
from test_contracts import file_root
from test_delivery import setup,passing,send,make_ship
from test_assembly import client,ok
P='/api/v1/service'
def cmd(c,path,body,key=None):return c.post(P+path,json=body,headers={'Idempotency-Key':key or str(uuid4())})
def get(c,path):return ok(c.get(P+path))
def v(w,**extra):return {'expected_version':w['version'],'confirmed':True,'reason':'虚构明确处理',**extra}
def shipped(engine,database,i):
    o,loc,ids=setup(engine,database,i)
    with client(engine,database,i.user,i.a) as c:passing(c,ids[0]);s=send(c,make_ship(c,o,ids))
    return o,loc,ids[0],s

def test_shipped_device_source_and_customer_custody_not_sales_return(engine,database,identities):
    i=identities;o,loc,id,sh=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        stock=ok(c.get('/api/v1/inventory/stock'));body={'device_id':id,'number':'SV-TEST','fault':'虚构启动故障','reported_at':'2026-09-11T00:00:00Z','contact':'虚构联系人','mode':'return','priority':'normal','manager_id':str(i.user),'planned_on':'2026-10-01'}
        w=ok(cmd(c,'/works',body));assert w['order_id']==o['id'] and w['customer_name']==sh['progress']['customer_name']
        w=ok(cmd(c,'/works/'+w['id']+'/receive',v(w,location_id=loc['id'],performed_at='2026-09-11T00:00:00Z',appearance='完整',accessories='仅主机')))
        assert w['custody']=='company' and w['warranty']=='pending'
        assert ok(c.get('/api/v1/inventory/stock'))['known_cost']==stock['known_cost']
        assert ok(c.get('/api/v1/delivery/shipments/'+sh['id']))==sh

def new_work(c,i,id):return ok(cmd(c,'/works',{'device_id':id,'number':'SV-'+str(uuid4()),'fault':'虚构故障','reported_at':'2026-09-11T00:00:00Z','contact':'虚构联系人','mode':'onsite','manager_id':str(i.user),'planned_on':'2026-10-01'}))
def test_spare_issue_return_and_install_cost_counted_once(engine,database,identities):
    i=identities;o,loc,id,sh=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=new_work(c,i,id);old=w['installations'][0]
        w=ok(cmd(c,'/works/'+w['id']+'/reserve',v(w,sku_id=old['sku_id'],quantity=old['quantity'])))
        r=w['reservations'][0];w=ok(cmd(c,'/works/'+w['id']+'/issue',v(w,reservation_id=r['id'],quantity=r['quantity'])))
        issue=w['issues'][0];assert w['material_cost']=='0.00'
        w=ok(cmd(c,'/works/'+w['id']+'/replace',v(w,old_installation_id=old['id'],issue_id=issue['id'],old_destination='quarantine',location_id=loc['id'],compatibility_basis='虚构人工核对同型号插槽',manual_compatibility_confirmed=True)))
        assert not w['test_valid'] and w['material_cost']!='0.00'
        assert cmd(c,'/works/'+w['id']+'/spare-return',v(w,issue_id=issue['id'],quantity=issue['quantity'])).status_code==409
        current=[x for x in w['installations'] if not x['removed_at']];assert any(x['service_work_id']==w['id'] for x in current)
        assert next(x for x in w['installations'] if x['id']==old['id'])['removed_at']
        assert w['old_parts'][0]['owner']=='customer'
        assert ok(c.get('/api/v1/delivery/shipments/'+sh['id']))==sh

def changed_work(c,i,id,loc):
    w=new_work(c,i,id);old=w['installations'][0]
    w=ok(cmd(c,'/works/'+w['id']+'/reserve',v(w,sku_id=old['sku_id'],quantity=old['quantity'])))
    r=w['reservations'][0];w=ok(cmd(c,'/works/'+w['id']+'/issue',v(w,reservation_id=r['id'],quantity=r['quantity'])))
    return ok(cmd(c,'/works/'+w['id']+'/replace',v(w,old_installation_id=old['id'],issue_id=w['issues'][0]['id'],old_destination='quarantine',location_id=loc['id'],compatibility_basis='虚构人工资料',manual_compatibility_confirmed=True)))

def test_rma_return_inspection_and_service_financial_sources(engine,database,identities):
    from test_inventory import setup_purchase
    from test_finance import cmd as fc,new_plan,new_cash,alloc,version
    i=identities;o,loc,id,sh=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=changed_work(c,i,id,loc);_,co,_=setup_purchase(c,i)
        r=ok(cmd(c,'/rmas',{'work_id':w['id'],'expected_version':w['version'],'number':'RMA-1','supplier_id':co['supplier_id'],'manager_id':str(i.user),'supplier_number':'虚构受理1','fault':'故障件','expected_on':'2026-10-01','authorization_basis':'期初来源无供应商，明确委托授权','old_part_ids':[w['old_parts'][0]['id']]}))
        r=ok(cmd(c,'/rmas/'+r['id']+'/send',v(r)));assert r['outside_quantity']==1
        r=ok(cmd(c,'/rmas/'+r['id']+'/return',v(r,line_id=r['lines'][0]['id'],quantity=1,kind='repair',location_id=loc['id'],performed_at='2026-09-11T00:00:00Z',result='原件人工修复')))
        assert r['pending_quantity']==1 and r['outside_quantity']==0
        r=ok(cmd(c,'/rmas/'+r['id']+'/inspect',v(r,return_id=r['lines'][0]['returns'][0]['id'],passed=True,disposition='customer',ownership_basis='归还客户所有物')))
        assert r['pending_quantity']==0
        w=get(c,'/works/'+w['id']);charge=ok(cmd(c,'/works/'+w['id']+'/charge',v(w,kind='customer_service',amount='100',basis_ref='虚构服务确认单',number='SERVICE-1')))
        w=get(c,'/works/'+w['id']);w=ok(cmd(c,'/works/'+w['id']+'/cost',v(w,kind='labor',person_id=str(i.user),hours='1.50',amount='20.50',basis='虚构人工工时确认',occurred_on='2026-09-11')))
        w=ok(cmd(c,'/works/'+w['id']+'/cost',v(w,kind='other',amount='2.50',basis='虚构运输费确认',occurred_on='2026-09-11')))
        assert w['labor_cost']=='20.50' and w['other_cost']=='2.50'
        sources=ok(c.get('/api/v1/finance/sources'));s=next(x for x in sources if x['id']==charge['id'])
        assert s['kind']=='customer_service' and s['amount']=='100.00'
        p=new_plan(c,s,'100');cash=new_cash(c,s,'100');ok(alloc(c,cash,(p,'100')))
        assert ok(c.get('/api/v1/finance/plans/'+p['id']))['remaining']=='0.00'
        assert ok(c.get('/api/v1/delivery/shipments/'+sh['id']))==sh

def test_swap_correction_and_quarantine_disposition(engine,database,identities):
    i=identities;_,loc,id,_=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=changed_work(c,i,id,loc);change=w['changes'][0]
        w=ok(cmd(c,'/works/'+w['id']+'/reverse-change',v(w,change_id=change['id'])))
        assert w['material_cost']=='0.00' and w['issues'][0]['unused']>0
        assert get(c,'/reconciliation')['matches']
        issue=w['issues'][0];w=ok(cmd(c,'/works/'+w['id']+'/spare-return',v(w,issue_id=issue['id'],quantity=issue['unused'])))
        assert get(c,'/reconciliation')['matches']

def test_old_customer_part_disposal_requires_record_and_blocks_rma(engine,database,identities):
    i=identities;_,loc,id,_=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=changed_work(c,i,id,loc);p=w['old_parts'][0]
        w=ok(cmd(c,'/works/'+w['id']+'/dispose',v(w,old_part_id=p['id'],return_id=None,disposition='customer',basis='客户实际签收旧件')))
        assert w['old_parts'][0]['disposition']['disposition']=='customer'
        assert cmd(c,'/works/'+w['id']+'/dispose',v(w,old_part_id=p['id'],return_id=None,disposition='scrap',basis='重复处置')).status_code==409

def test_context_options_permissions_and_replay(engine,database,identities):
    from sqlalchemy import text
    i=identities;_,loc,id,_=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        assert get(c,'/context')['people'];assert get(c,'/options')['stock'];assert get(c,'/devices')
        w=new_work(c,i,id);body=v(w,sku_id=w['installations'][0]['sku_id'],quantity=1);key=str(uuid4())
        saved=ok(cmd(c,'/works/'+w['id']+'/reserve',body,key));assert ok(cmd(c,'/works/'+w['id']+'/reserve',body,key))==saved
        with i.owner.begin() as db:db.execute(text("DELETE FROM role_permissions WHERE role='admin' AND permission='service.spares'"))
        try:assert cmd(c,'/works/'+w['id']+'/reserve',body,key).status_code==403
        finally:
            with i.owner.begin() as db:db.execute(text("INSERT INTO role_permissions VALUES('admin','service.spares')"))
        with i.owner.begin() as db:db.execute(text("DELETE FROM role_permissions WHERE role='admin' AND permission IN('service.cost','inventory.cost')"))
        try:
            data=get(c,'/works/'+w['id']);assert not {'material_cost','labor_cost','costs'}&data.keys()
        finally:
            with i.owner.begin() as db:db.execute(text("INSERT INTO role_permissions VALUES('admin','service.cost'),('admin','inventory.cost')"))
    with client(engine,database,i.other,i.b) as c:assert c.get(P+'/works/'+w['id']).status_code==404
    with engine.connect() as db:
        assert not db.scalar(text('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user'))
        assert db.scalar(text('SELECT count(*) FROM svc_works'))==0


def test_concurrent_issue_and_unused_return(engine,database,identities):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    i=identities;_,loc,id,_=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=new_work(c,i,id);w=ok(cmd(c,'/works/'+w['id']+'/reserve',v(w,sku_id=w['installations'][0]['sku_id'],quantity=1)))
    gate=Barrier(2);body=v(w,reservation_id=w['reservations'][0]['id'],quantity=1)
    def attempt(_):
        with client(engine,database,i.user,i.a) as c:gate.wait(5);return cmd(c,'/works/'+w['id']+'/issue',body)
    with ThreadPoolExecutor(2) as pool:
        results=[f.result(timeout=15) for f in [pool.submit(attempt,n) for n in range(2)]]
    assert sorted(x.status_code for x in results)==[200,409]
    with client(engine,database,i.user,i.a) as c:
        w=get(c,'/works/'+w['id']);assert len(w['issues'])==1
        w=ok(cmd(c,'/works/'+w['id']+'/spare-return',v(w,issue_id=w['issues'][0]['id'],quantity=1)))
        assert get(c,'/reconciliation')['matches']


def test_test_failure_state_custody_and_sales_return_protection(engine,database,identities):
    from test_delivery import cmd as delivery_cmd
    i=identities;_,loc,id,sh=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=ok(cmd(c,'/works',{'device_id':id,'number':'LOOP','fault':'故障','reported_at':'2026-09-11T00:00:00Z','contact':'虚构','mode':'return','manager_id':str(i.user),'planned_on':'2026-10-01'}))
        w=ok(cmd(c,'/works/'+w['id']+'/receive',v(w,location_id=loc['id'],performed_at='2026-09-11T00:00:00Z',appearance='完整',accessories='无')))
        assert delivery_cmd(c,'/shipments/'+sh['id']+'/return',v(sh,line_ids=[sh['lines'][0]['id']],location_id=loc['id'],performed_at='2026-09-11T00:00:00Z')).status_code==409
        w=ok(cmd(c,'/works/'+w['id']+'/diagnose',v(w,manager_id=str(i.user),diagnosis='虚构诊断',solution='虚构修复',warranty='pending')))
        for result in ['pass','fail']:
            w=ok(cmd(c,'/works/'+w['id']+'/test',v(w,performed_at='2026-09-11T00:00:00Z',items=[{'name':'启动','result':result}])))
        assert not w['test_valid']
        w=ok(cmd(c,'/works/'+w['id']+'/state',v(w,state='verify')))
        assert cmd(c,'/works/'+w['id']+'/state',v(w,state='resolved',customer_confirmation='同意')).status_code==409
        w=ok(cmd(c,'/works/'+w['id']+'/test',v(w,performed_at='2026-09-11T00:00:00Z',items=[{'name':'启动','result':'pass'}])))
        w=ok(cmd(c,'/works/'+w['id']+'/state',v(w,state='resolved',customer_confirmation='客户确认')))
        w=ok(cmd(c,'/works/'+w['id']+'/return',v(w,receipt_id=w['receipts'][0]['id'],performed_at='2026-09-11T00:00:00Z',customer_confirmation='客户实收')))
        w=ok(cmd(c,'/works/'+w['id']+'/state',v(w,state='closed')));assert w['custody']=='customer'
        assert get(c,'/reconciliation')['matches']

def test_0014_upgrade_preserves_identity_delivery_and_refuses_service_downgrade(engine,database,identities):
    from conftest import ROOT,run
    import sys,subprocess
    i=identities;_,loc,id,shipment=shipped(engine,database,i)
    env={**database.env,'DATABASE_URL':database.migration_url}
    run(sys.executable,'infra/migrate.py','downgrade','0014_finance_corrections',cwd=ROOT,env=env)
    run(sys.executable,'infra/migrate.py','upgrade','head',cwd=ROOT,env=env)
    with client(engine,database,i.user,i.a) as c:
        assert ok(c.get('/api/v1/delivery/shipments/'+shipment['id']))==shipment
        w=new_work(c,i,id)
        blocked=subprocess.run([sys.executable,'infra/migrate.py','downgrade','0014_finance_corrections'],cwd=ROOT,env=env,text=True,capture_output=True)
        assert blocked.returncode!=0 and 'service history prevents downgrade' in blocked.stderr
        assert get(c,'/works/'+w['id'])==w

def test_multi_line_rma_partial_returns_and_supplier_charge(engine,database,identities):
    from test_inventory import setup_purchase
    i=identities;_,loc,id,_=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=changed_work(c,i,id,loc)
        # A second physical replacement produces a second old part, preserving both slots' history.
        old=next(x for x in w['installations'] if not x['removed_at'])
        w=ok(cmd(c,'/works/'+w['id']+'/reserve',v(w,sku_id=old['sku_id'],quantity=1)))
        reserve=next(x for x in w['reservations'] if x['consumed']==0)
        w=ok(cmd(c,'/works/'+w['id']+'/issue',v(w,reservation_id=reserve['id'],quantity=1)))
        issue=next(x for x in w['issues'] if x['unused'])
        w=ok(cmd(c,'/works/'+w['id']+'/replace',v(w,old_installation_id=old['id'],issue_id=issue['id'],old_destination='quarantine',location_id=loc['id'],compatibility_basis='第二次人工核验',manual_compatibility_confirmed=True)))
        _,co,_=setup_purchase(c,i)
        r=ok(cmd(c,'/rmas',{'work_id':w['id'],'expected_version':w['version'],'number':'MULTI','supplier_id':co['supplier_id'],'manager_id':str(i.user),'supplier_number':'受理','fault':'故障','expected_on':'2026-10-01','authorization_basis':'委托维修','old_part_ids':[x['id'] for x in w['old_parts']]}))
        r=ok(cmd(c,'/rmas/'+r['id']+'/send',v(r)));assert r['outside_quantity']==2
        for n in range(2):
            line=r['lines'][n];r=ok(cmd(c,'/rmas/'+r['id']+'/return',v(r,line_id=line['id'],quantity=1,kind='repair',location_id=loc['id'],performed_at='2026-09-11T00:00:00Z',result='部分返回')))
            assert r['outside_quantity']==1-n
        assert r['pending_quantity']==2
        w=get(c,'/works/'+w['id']);charge=ok(cmd(c,'/works/'+w['id']+'/charge',v(w,kind='supplier_repair',rma_id=r['id'],amount='20.01',basis_ref='供应商维修账单',number='AP-SERVICE')))
        assert next(x for x in ok(c.get('/api/v1/finance/sources')) if x['id']==charge['id'])['direction']=='payable'
        assert get(c,'/reconciliation')['matches']

def test_serial_replacement_rma_new_sn_and_own_spare_requires_cost_basis(engine,database,identities):
    from test_assembly import prepared
    from test_assembly_correction import issued_work,finish
    from test_inventory import post,setup_purchase
    i=identities;o,loc,body=prepared(engine,database,i,mode='sn')
    with client(engine,database,i.user,i.a) as c:
        d=ok(finish(c,issued_work(c,body),loc['id'],serial='SERVICE-DEVICE'))['devices'][0];passing(c,d['id']);send(c,make_ship(c,o,[d['id']]))
        host=o['content']['commercial']['host'];csv='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'+f'SPARE-1,{host["number"]},{loc["id"]},qualified,own,1,SVC-NEW,,35.01,confirmed,CNY,2026-01-01,虚构备件\n'
        preview=ok(post(c,'/opening/preview',{'csv':csv}));ok(post(c,'/opening/'+preview['id']+'/commit',{'expected_version':1,'confirmed':True}))
        w=changed_work(c,i,d['id'],loc);assert w['material_cost']=='35.01'
        old=w['old_parts'][0];assert old['serial']=='H1'
        _,co,_=setup_purchase(c,i)
        r=ok(cmd(c,'/rmas',{'work_id':w['id'],'expected_version':w['version'],'number':'SERIAL-RMA','supplier_id':co['supplier_id'],'manager_id':str(i.user),'supplier_number':'新SN替换','fault':'故障','expected_on':'2026-10-01','authorization_basis':'客户明确授权','old_part_ids':[old['id']]}))
        r=ok(cmd(c,'/rmas/'+r['id']+'/send',v(r)))
        rb=v(r,line_id=r['lines'][0]['id'],quantity=1,kind='replacement',serial='SVC-REPLACED',location_id=loc['id'],performed_at='2026-09-11T00:00:00Z',result='供应商换新')
        key=str(uuid4());r=ok(cmd(c,'/rmas/'+r['id']+'/return',rb,key));assert ok(cmd(c,'/rmas/'+r['id']+'/return',rb,key))==r
        rr=r['lines'][0]['returns'][0];ib=v(r,return_id=rr['id'],passed=True,disposition='own_spare',ownership_basis='虚构客户转移所有权确认，明确成本依据')
        assert cmd(c,'/rmas/'+r['id']+'/inspect',ib).status_code==422
        r=ok(cmd(c,'/rmas/'+r['id']+'/inspect',{**ib,'unit_cost':'12.34'}))
        stock=ok(c.get('/api/v1/inventory/stock'))['items'];new=next(x for x in stock if x['serial_raw']=='SVC-REPLACED');assert new['ownership']=='own' and new['state']=='qualified' and new['unit_cost']=='12.34'
        assert get(c,'/works/'+w['id'])['old_parts'][0]['serial']=='H1'
        assert get(c,'/reconciliation')['matches']

def test_hold_disposition_and_cancelled_rma_reopen(engine,database,identities):
    from test_inventory import setup_purchase
    i=identities;_,loc,id,_=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=changed_work(c,i,id,loc);_,co,_=setup_purchase(c,i)
        r=ok(cmd(c,'/rmas',{'work_id':w['id'],'expected_version':w['version'],'number':'HOLD-RMA','supplier_id':co['supplier_id'],'manager_id':str(i.user),'supplier_number':'受理','fault':'故障','expected_on':'2026-10-01','authorization_basis':'客户授权','old_part_ids':[w['old_parts'][0]['id']]}))
        r=ok(cmd(c,'/rmas/'+r['id']+'/cancel',v(r)));r=ok(cmd(c,'/rmas/'+r['id']+'/reopen',v(r)));r=ok(cmd(c,'/rmas/'+r['id']+'/send',v(r)))
        r=ok(cmd(c,'/rmas/'+r['id']+'/return',v(r,line_id=r['lines'][0]['id'],quantity=1,kind='repair',location_id=loc['id'],performed_at='2026-09-11T00:00:00Z',result='未修复')))
        returned=r['lines'][0]['returns'][0];r=ok(cmd(c,'/rmas/'+r['id']+'/inspect',v(r,return_id=returned['id'],passed=False,disposition='hold',ownership_basis='返修未通过继续隔离')))
        w=get(c,'/works/'+w['id']);assert w['old_parts'][0]['current_custody']=='hold'
        w=ok(cmd(c,'/works/'+w['id']+'/dispose',v(w,old_part_id=None,return_id=returned['id'],disposition='customer',basis='客户同意原状领回')))
        assert w['old_parts'][0]['current_custody']=='customer' and get(c,'/reconciliation')['matches']

def test_people_options_only_current_tenant_memberships(engine,database,identities):
    from sqlalchemy import text
    i=identities;extra=uuid4()
    with i.owner.begin() as db:
        db.execute(text("INSERT INTO identity_users(id,issuer,subject,display_name) VALUES (:id,'fixture',:s,'仅 A 售后人员')"),{'id':extra,'s':str(extra)})
        db.execute(text("INSERT INTO memberships VALUES (:a,:u,'member',true)"),{'a':i.a,'u':extra})
    with client(engine,database,i.other,i.b) as c:assert str(extra) not in {x['id'] for x in get(c,'/context')['people']}

def test_shared_reservations_block_assembly_and_inventory(engine,database,identities):
    from test_assembly import post as ac,confirm
    from test_inventory import post as ic
    i=identities;o,loc,id,_=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=new_work(c,i,id);sku=w['installations'][0]['sku_id']
        w=ok(cmd(c,'/works/'+w['id']+'/reserve',v(w,sku_id=sku,quantity=2)))
        dev=ok(c.get('/api/v1/assembly/devices/'+id));aw=ok(ac(c,'/works',{'order_id':o['id'],'product_sku_id':dev['product']['id'],'manager_id':str(i.user),'planned_on':'2026-09-11'}))
        aw=confirm(c,aw)
        assert ac(c,'/works/'+aw['id']+'/reserve',{'expected_version':aw['version'],'confirmed':True,'requirement_id':aw['requirements'][0]['id'],'quantity':1,'duration_hours':24}).status_code==409
        w=ok(cmd(c,'/works/'+w['id']+'/release',v(w)))
        assert ac(c,'/works/'+aw['id']+'/reserve',{'expected_version':aw['version'],'confirmed':True,'requirement_id':aw['requirements'][0]['id'],'quantity':1,'duration_hours':24}).status_code==200


def test_diagnosis_change_and_reopen_require_fresh_test(engine,database,identities):
    i=identities;_,loc,id,_=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=new_work(c,i,id)
        diagnosis={'manager_id':str(i.user),'diagnosis':'初步诊断','solution':'人工处理','warranty':'pending'}
        w=ok(cmd(c,'/works/'+w['id']+'/diagnose',v(w,**diagnosis)))
        w=ok(cmd(c,'/works/'+w['id']+'/test',v(w,performed_at='2026-09-11T00:00:00Z',items=[{'name':'通电','result':'pass'}])))
        assert w['test_valid']
        w=ok(cmd(c,'/works/'+w['id']+'/diagnose',v(w,**{**diagnosis,'solution':'重新处理'})))
        assert not w['test_valid'] and len(w['tests'])==1

def test_unknown_cost_and_customer_quarantine_never_become_usable_spares(engine,database,identities):
    from test_inventory import post
    i=identities;o,loc,id,_=shipped(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        host=o['content']['commercial']['host']
        header='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'
        csv=header+f'UNKNOWN,{host["number"]},{loc["id"]},qualified,own,1,,UNKNOWN,,unknown,CNY,2026-01-01,未知成本\n'+f'CUSTOMER,{host["number"]},{loc["id"]},qualified,customer,5,,CUST,,unknown,CNY,2026-01-01,客户代管\n'+f'QUARANTINE,{host["number"]},{loc["id"]},quarantine,own,5,,Q,1.00,confirmed,CNY,2026-01-01,隔离\n'
        preview=ok(post(c,'/opening/preview',{'csv':csv}));assert preview['valid'];ok(post(c,'/opening/'+preview['id']+'/commit',{'expected_version':1,'confirmed':True}))
        w=new_work(c,i,id)
        assert cmd(c,'/works/'+w['id']+'/reserve',v(w,sku_id=host['id'],quantity=4)).status_code==409
        w=ok(cmd(c,'/works/'+w['id']+'/reserve',v(w,sku_id=host['id'],quantity=3)))
        stock=ok(c.get('/api/v1/inventory/stock'))['items'];unknown=next(x for x in stock if x['batch']=='UNKNOWN')
        reserved=next(x for x in w['reservations'] if x['layer_id']==unknown['layer_id'])
        error=cmd(c,'/works/'+w['id']+'/issue',v(w,reservation_id=reserved['id'],quantity=1))
        assert error.status_code==422 and error.json()['code']=='UNKNOWN_COST'
        assert get(c,'/works/'+w['id'])['issues']==[] and get(c,'/reconciliation')['matches']
