"""After-sales actions reuse inventory, stable devices and financial source guards."""
from datetime import datetime,timezone,date,timedelta
from decimal import Decimal
from uuid import UUID,uuid4
import json
from sqlalchemy import text
from silicon.identity.access import Denied
from silicon.inventory import service as inv
from silicon.assembly import service as asm
from silicon.delivery import service as delivery
from silicon.finance import service as finance
D=Decimal
row=inv.row
rows=inv.rows
insert=inv.insert
money=finance.money

def balances_for(db,layer_id):
    return [dict(x) for x in db.execute(text('SELECT * FROM inv_balances WHERE layer_id=:id ORDER BY location_id,state'),{'id':layer_id}).mappings()]

def guard(db,a,write):
    asm.quotes.guard(db,a,False)
    db.execute(text('SELECT id FROM crm_customers ORDER BY id FOR SHARE')).all()
    inv.guard(db,a,write)

def device(db,a,id):
    d=delivery.device(db,id);customer=row(db,'crm_customers',d['customer_id'])
    if not a.owns(customer['owner_id']):raise Denied(404,'NOT_FOUND')
    return d

def source_line(d):
    valid=[x for x in d['deliveries'] if not x['returns'] and not x['reversed']]
    if not valid:raise Denied(409,'SERVICE_SHIPPED_SOURCE_REQUIRED')
    return valid[-1]

def manager(db,id):
    if not db.scalar(text('SELECT 1 FROM memberships WHERE user_id=:id AND active AND tenant_visible(tenant_id)'),{'id':id}):raise Denied(422,'MANAGER_INACTIVE')

def event(db,a,id,action,reason,details=None):
    insert(db,a,'svc_events',{'id':uuid4(),'work_id':id,'actor_id':a.actor_id,'action':action,'reason':reason,'details':json.dumps(inv.serial(details or {}))})

def bump(db,id,config=False):
    db.execute(text('UPDATE svc_works SET version=version+1'+(',config_version=config_version+1' if config else '')+' WHERE id=:id'),{'id':id})

def editable(w,b):
    inv.c.expected(w,b.expected_version)
    if w['state'] in ('closed','cancelled'):raise Denied(409,'SERVICE_WORK_CLOSED')

def scoped(db,a,id):
    w=row(db,'svc_works',id);d=device(db,a,w['device_id']);return w,d

def reversed_change(db,id):return bool(rows(db,'svc_change_reversals','change_id',id))

def issue_unused(db,i):
    used=0
    for x in rows(db,'svc_changes','issue_id',i['id']):
        if not reversed_change(db,x['id']):used+=row(db,'asm_installations',x['new_installation_id'])['quantity']
    return i['quantity']-sum(x['quantity'] for x in rows(db,'svc_spare_returns','issue_id',i['id']))-used

def detail(db,a,id):
    w,d=scoped(db,a,id)
    w.update({k:d[k] for k in ('serial','customer_id','customer_name','order_id','order_number','contract_id')})
    w['receipts']=rows(db,'svc_receipts','work_id',id);w['returns']=rows(db,'svc_returns','work_id',id)
    live=[x for x in w['receipts'] if not any(y['receipt_id']==x['id'] for y in w['returns'])]
    w['custody']='company' if live else 'customer'
    w['tests']=delivery.ordered(db,'svc_tests','work_id',id);latest=w['tests'][-1] if w['tests'] else None
    w['test_valid']=bool(latest and latest['config_version']==w['config_version'] and latest['result']=='pass')
    w['history']=delivery.ordered(db,'svc_events','work_id',id);w['reservations']=rows(db,'svc_reservations','work_id',id)
    w['issues']=rows(db,'svc_issues','work_id',id)
    for i in w['issues']:
        l=row(db,'inv_layers',i['layer_id']);i.update(unused=issue_unused(db,i),sku_id=l['sku_id'],serial=row(db,'inv_units',l['unit_id'])['serial_raw'] if l['unit_id'] else None)
    w['changes']=rows(db,'svc_changes','work_id',id)
    for c in w['changes']:c['reversed']=reversed_change(db,c['id'])
    w['old_parts']=rows(db,'svc_old_parts','work_id',id)
    for p in w['old_parts']:
        p['serial']=row(db,'inv_units',p['unit_id'])['serial_raw'] if p['unit_id'] else None
        p['reversed']=reversed_change(db,p['change_id']);p['disposition']=next(iter(rows(db,'svc_dispositions','old_part_id',p['id'])),None)
        p['current_custody']=old_custody(db,p)
    w['rmas']=[rma(db,a,x['id']) for x in rows(db,'svc_rmas','work_id',id)]
    w['installations']=d['installations']
    # Frozen completion installations are distinguished from service replacements.
    w['original_configuration']=[x for x in d['installations'] if not x.get('service_work_id')]
    if 'inventory.cost' in a.permissions:
        w['material_cost']=money(sum((row(db,'inv_layers',row(db,'svc_issues',x['issue_id'])['layer_id'])['unit_cost']*row(db,'asm_installations',x['new_installation_id'])['quantity'] for x in w['changes'] if not x['reversed']),D(0)))
    if 'service.cost' in a.permissions:
        w['costs']=rows(db,'svc_costs','work_id',id)
        for kind in ('labor','other'):w[kind+'_cost']=money(sum((x['amount'] for x in w['costs'] if x['kind']==kind),D(0)))
    return w

def public(a,value):
    if isinstance(value,list):return [public(a,x) for x in value]
    if isinstance(value,dict):return {k:public(a,v) for k,v in value.items() if not ((k in ('material_cost','unit_cost','cost') and 'inventory.cost' not in a.permissions) or (k in ('labor_cost','other_cost','costs') and 'service.cost' not in a.permissions))}
    return value

def create(db,a,b):
    d=device(db,a,b.device_id);line=source_line(d);manager(db,b.manager_id);delivery.when(b.reported_at)
    id=uuid4();loc=uuid4();insert(db,a,'inv_locations',{'id':loc,'warehouse':'售后领用暂存','name':str(id)});insert(db,a,'svc_works',{'id':id,**b.model_dump(),'line_id':line['id'],'parts_location_id':loc});event(db,a,id,'created','人工报修登记')
    return detail(db,a,id)

def receive(db,a,id,b):
    w=detail(db,a,id);editable(w,b);delivery.when(b.performed_at);row(db,'inv_locations',b.location_id)
    if w['mode']!='return' or w['custody']=='company':raise Denied(409,'SERVICE_CUSTODY_INVALID')
    insert(db,a,'svc_receipts',{'id':uuid4(),'work_id':id,'actor_id':a.actor_id,**b.model_dump(exclude={'expected_version','confirmed'})});bump(db,id);event(db,a,id,'received',b.reason)
    return detail(db,a,id)

def return_device(db,a,id,b):
    w=detail(db,a,id);editable(w,b);delivery.when(b.performed_at);r=row(db,'svc_receipts',b.receipt_id)
    if r['work_id']!=id:raise Denied(404,'NOT_FOUND')
    if w['custody']!='company' or not w['test_valid'] or w['state']!='resolved':raise Denied(409,'SERVICE_RETURN_NOT_READY')
    if b.performed_at<r['performed_at']:raise Denied(422,'SERVICE_TIME_ORDER')
    insert(db,a,'svc_returns',{'id':uuid4(),'work_id':id,'actor_id':a.actor_id,**b.model_dump(exclude={'expected_version','confirmed'})});bump(db,id);event(db,a,id,'returned',b.reason)
    return detail(db,a,id)

def diagnose(db,a,id,b):
    w=detail(db,a,id);editable(w,b);manager(db,b.manager_id)
    if b.warranty!='pending' and not b.warranty_basis.strip():raise Denied(422,'WARRANTY_BASIS_REQUIRED')
    inv.c.update(db,'svc_works',id,{**b.model_dump(exclude={'expected_version','confirmed','reason'}),'state':'working','version':w['version']+1,'config_version':w['config_version']+1})
    event(db,a,id,'diagnosed',b.reason,b.model_dump(exclude={'expected_version','confirmed'}));return detail(db,a,id)

def transition(db,a,id,b):
    w=detail(db,a,id);inv.c.expected(w,b.expected_version)
    allowed={'new':{'working','cancelled'},'working':{'waiting','verify','cancelled'},'waiting':{'working','verify','cancelled'},'verify':{'working','resolved'},'resolved':{'working','closed'},'closed':{'working'},'cancelled':set()}
    if b.state not in allowed[w['state']]:raise Denied(409,'SERVICE_STATE_TRANSITION')
    if w['state']=='closed':
        a.require('service.correct')
        if not b.reopen:raise Denied(409,'SERVICE_EXPLICIT_REOPEN_REQUIRED')
    if b.state=='resolved' and (not w['test_valid'] or not w['diagnosis'] or not w['solution'] or not b.customer_confirmation.strip()):raise Denied(409,'SERVICE_VERIFICATION_REQUIRED')
    if b.state in ('closed','cancelled'):
        if w['custody']=='company' or any(i['unused'] for i in w['issues']):raise Denied(409,'SERVICE_PHYSICAL_DEPENDENCY')
        if b.state=='cancelled' and (w['issues'] or w['changes'] or rows(db,'svc_costs','work_id',id) or rows(db,'svc_charges','work_id',id) or w['rmas']):raise Denied(409,'SERVICE_HISTORY_DEPENDENCY')
        if b.state=='closed':
            if not w['test_valid']:raise Denied(409,'SERVICE_VERIFICATION_REQUIRED')
            for p in w['old_parts']:
                if not p['reversed'] and p['destination']!='customer' and not p['disposition'] and not any(row(db,'svc_rmas',l['rma_id'])['state']!='cancelled' for l in rows(db,'svc_rma_lines','old_part_id',p['id'])):raise Denied(409,'SERVICE_OLD_PART_RESPONSIBILITY_REQUIRED')
        db.execute(text('UPDATE svc_reservations SET released=quantity-consumed WHERE work_id=:id'),{'id':id})
    inv.c.update(db,'svc_works',id,{'state':b.state,'version':w['version']+1,'config_version':w['config_version']+(1 if w['state']=='closed' else 0),'customer_confirmation':b.customer_confirmation if b.state=='resolved' else w['customer_confirmation']})
    event(db,a,id,'state.'+b.state,b.reason);return detail(db,a,id)

def test(db,a,id,b):
    w=detail(db,a,id);editable(w,b);delivery.when(b.performed_at)
    if w['mode']=='return' and w['custody']!='company':raise Denied(409,'SERVICE_RECEIVE_FIRST')
    if len({x.name for x in b.items})!=len(b.items):raise Denied(422,'DUPLICATE_TEST_ITEM')
    insert(db,a,'svc_tests',{'id':uuid4(),'work_id':id,'config_version':w['config_version'],'actor_id':a.actor_id,'reason':b.reason,'performed_at':b.performed_at,'items':json.dumps([x.model_dump() for x in b.items]),'report_ref':b.report_ref,'result':'fail' if any(x.result=='fail' for x in b.items) else 'pass'})
    bump(db,id);event(db,a,id,'tested',b.reason);return detail(db,a,id)

def rma(db,a,id):
    r=row(db,'svc_rmas',id);scoped(db,a,r['work_id']);r['lines']=rows(db,'svc_rma_lines','rma_id',id);outside=pending=0
    for l in r['lines']:
        l['returns']=rows(db,'svc_rma_returns','line_id',l['id']);l['remaining']=l['quantity']-sum(x['quantity'] for x in l['returns']);outside+=l['remaining'] if r['state'] in ('sent','processing','returned','completed') else 0
        for x in l['returns']:
            x['inspections']=rows(db,'svc_rma_inspections','return_id',x['id']);x['disposition']=next(iter(rows(db,'svc_dispositions','return_id',x['id'])),None);pending+=x['quantity'] if not x['inspections'] else 0
    r.update(outside_quantity=outside,pending_quantity=pending,overdue=bool(outside and r['expected_on']<date.today()));return r

def reserve(db,a,id,b):
    w=detail(db,a,id);editable(w,b);row(db,'inv_tracking',b.sku_id)
    if w['state'] not in ('new','working','waiting'):raise Denied(409,'SERVICE_STATE_TRANSITION')
    sources=db.execute(text("SELECT l.*,b.location_id,b.quantity AS balance FROM inv_layers l JOIN inv_balances b ON b.layer_id=l.id AND b.tenant_id=l.tenant_id WHERE l.sku_id=:s AND l.ownership='own' AND b.state='qualified' AND b.quantity>0 ORDER BY l.created_at,l.id,b.location_id"),{'s':b.sku_id}).mappings()
    left=b.quantity
    for x in sources:
        n=min(left,x['balance']-asm.active(db,x['id'],x['location_id']))
        if n<=0:continue
        insert(db,a,'svc_reservations',{'id':uuid4(),'work_id':id,'layer_id':x['id'],'location_id':x['location_id'],'quantity':n,'expires_at':datetime.now(timezone.utc)+timedelta(hours=b.hours)})
        left-=n
        if not left:break
    if left:raise Denied(409,'INSUFFICIENT_AVAILABLE_STOCK')
    bump(db,id);event(db,a,id,'reserved',b.reason);return detail(db,a,id)

def release(db,a,id,b):
    w=detail(db,a,id);editable(w,b)
    db.execute(text('UPDATE svc_reservations SET released=quantity-consumed WHERE work_id=:id'),{'id':id});bump(db,id);event(db,a,id,'released',b.reason);return detail(db,a,id)

def issue(db,a,id,b,request_id):
    w=detail(db,a,id);editable(w,b);r=row(db,'svc_reservations',b.reservation_id)
    if r['work_id']!=id:raise Denied(404,'NOT_FOUND')
    if w['state'] not in ('new','working','waiting') or r['expires_at']<=datetime.now(timezone.utc):raise Denied(409,'SERVICE_RESERVATION_INACTIVE')
    if b.quantity>r['quantity']-r['released']-r['consumed']:raise Denied(409,'RESERVATION_EXCEEDED')
    l=row(db,'inv_layers',r['layer_id'])
    if l['unit_cost'] is None:raise Denied(422,'UNKNOWN_COST')
    m=inv.movement(db,a,'service_issue',b.reason,request_id,date.today())
    inv.entry(db,a,m,l['id'],r['location_id'],'qualified',-b.quantity);inv.entry(db,a,m,l['id'],w['parts_location_id'],'service_issued',b.quantity)
    insert(db,a,'svc_issues',{'id':uuid4(),'work_id':id,'actor_id':a.actor_id,'reason':b.reason,'reservation_id':r['id'],'layer_id':l['id'],'location_id':r['location_id'],'quantity':b.quantity,'movement_id':m})
    db.execute(text('UPDATE svc_reservations SET consumed=consumed+:q WHERE id=:id'),{'q':b.quantity,'id':r['id']})
    db.execute(text('UPDATE inv_layers SET version=version+1 WHERE id=:id'),{'id':l['id']});bump(db,id);event(db,a,id,'issued',b.reason);return detail(db,a,id)

def spare_return(db,a,id,b,request_id):
    w=detail(db,a,id);editable(w,b);i=row(db,'svc_issues',b.issue_id)
    if i['work_id']!=id:raise Denied(404,'NOT_FOUND')
    if b.quantity>issue_unused(db,i):raise Denied(409,'SERVICE_UNUSED_EXCEEDED')
    m=inv.movement(db,a,'service_return',b.reason,request_id,date.today())
    inv.entry(db,a,m,i['layer_id'],w['parts_location_id'],'service_issued',-b.quantity);inv.entry(db,a,m,i['layer_id'],i['location_id'],'pending',b.quantity)
    insert(db,a,'svc_spare_returns',{'id':uuid4(),'work_id':id,'actor_id':a.actor_id,'reason':b.reason,'issue_id':i['id'],'quantity':b.quantity,'movement_id':m})
    db.execute(text('UPDATE inv_layers SET version=version+1 WHERE id=:id'),{'id':i['layer_id']});bump(db,id);event(db,a,id,'unused.returned',b.reason);return detail(db,a,id)

def replace(db,a,id,b,request_id):
    w=detail(db,a,id);editable(w,b)
    if w['mode']=='remote':raise Denied(409,'SERVICE_PHYSICAL_MODE_REQUIRED')
    if w['mode']=='return' and w['custody']!='company':raise Denied(409,'SERVICE_RECEIVE_FIRST')
    old=row(db,'asm_installations',b.old_installation_id);i=row(db,'svc_issues',b.issue_id)
    if old['device_id']!=w['device_id'] or i['work_id']!=id:raise Denied(404,'NOT_FOUND')
    if old['removed_at'] or old['quantity']>issue_unused(db,i):raise Denied(409,'SERVICE_INSTALLATION_CHANGED')
    original=row(db,'inv_layers',old['layer_id']);new=row(db,'inv_layers',i['layer_id']);sku=row(db,'catalog_skus',new['sku_id']);oldsku=row(db,'catalog_skus',original['sku_id'])
    if not sku['enabled'] or sku['category']!=oldsku['category']:raise Denied(422,'SERVICE_CATEGORY_MISMATCH')
    if new['unit_id'] and db.scalar(text('SELECT 1 FROM asm_installations WHERE unit_id=:u AND removed_at IS NULL'),{'u':new['unit_id']}):raise Denied(409,'COMPONENT_INSTALLED')
    row(db,'inv_locations',b.location_id)
    m=inv.movement(db,a,'service_replace',b.reason,request_id,date.today());change=uuid4();newid=uuid4()
    inv.entry(db,a,m,new['id'],w['parts_location_id'],'service_issued',-old['quantity'])
    db.execute(text('UPDATE asm_installations SET removed_at=clock_timestamp(),correction_id=:m WHERE id=:id'),{'m':m,'id':old['id']})
    insert(db,a,'asm_installations',{'id':newid,'device_id':w['device_id'],'completion_id':old['completion_id'],'layer_id':new['id'],'unit_id':new['unit_id'],'quantity':old['quantity'],'position':old['position'],'slot_id':old['slot_id'],'service_work_id':id})
    insert(db,a,'svc_changes',{'id':change,'work_id':id,'actor_id':a.actor_id,'reason':b.reason,'old_installation_id':old['id'],'new_installation_id':newid,'issue_id':i['id'],'movement_id':m,'compatibility_basis':b.compatibility_basis})
    layer=None
    if b.old_destination!='customer':
        tr=row(db,'inv_tracking',original['sku_id']);unit=row(db,'inv_units',old['unit_id']) if old['unit_id'] else None
        layer=inv.create_layer(db,a,m,oldsku,old['quantity'],tr['mode'],unit['serial_raw'] if unit else '',str(old['id']),b.location_id,'quarantine',{'unit_cost':None,'cost_status':'unknown','tax_basis':'unconfirmed','deductible_tax':None,'cost_basis':'客户旧件代管，非公司资产'},original['source_line'],ownership='customer')
    insert(db,a,'svc_old_parts',{'id':uuid4(),'work_id':id,'change_id':change,'layer_id':layer,'original_layer_id':original['id'],'unit_id':old['unit_id'],'quantity':old['quantity'],'destination':b.old_destination,'responsible_id':w['manager_id']})
    db.execute(text('UPDATE svc_works SET state=\'working\' WHERE id=:id'),{'id':id});bump(db,id,True);event(db,a,id,'replaced',b.reason,{'compatibility':'manual_UNKNOWN','basis':b.compatibility_basis});return detail(db,a,id)

def procurement_supplier(db,layer):
    if not layer['source_line']:return None
    line=row(db,'inv_receipt_lines',layer['source_line']);orderline=row(db,'inv_order_lines',line['order_line_id']);contractline=row(db,'inv_contract_lines',orderline['contract_line_id'])
    return row(db,'inv_contracts',contractline['contract_id'])['supplier_id']

def create_rma(db,a,b):
    w=detail(db,a,b.work_id);inv.c.expected(w,b.expected_version);manager(db,b.manager_id)
    supplier=row(db,'inv_suppliers',b.supplier_id)
    if not supplier['enabled']:raise Denied(422,'SUPPLIER_INACTIVE')
    if len(set(b.old_part_ids))!=len(b.old_part_ids):raise Denied(422,'DUPLICATE_PART')
    checked=[]
    for id in b.old_part_ids:
        p=row(db,'svc_old_parts',id)
        if p['work_id']!=w['id']:raise Denied(404,'NOT_FOUND')
        if p['layer_id'] is None or reversed_change(db,p['change_id']) or rows(db,'svc_dispositions','old_part_id',p['id']):raise Denied(409,'SERVICE_OLD_PART_UNAVAILABLE')
        supplier_id=procurement_supplier(db,row(db,'inv_layers',p['original_layer_id']))
        if supplier_id!=b.supplier_id:
            a.require('service.correct')
            if not b.authorization_basis.strip():raise Denied(422,'RMA_SUPPLIER_AUTHORIZATION_REQUIRED')
        checked.append(p)
    id=uuid4();insert(db,a,'svc_rmas',{'id':id,**b.model_dump(exclude={'expected_version','old_part_ids'})})
    for p in checked:insert(db,a,'svc_rma_lines',{'id':uuid4(),'rma_id':id,'old_part_id':p['id'],'quantity':p['quantity']})
    bump(db,w['id']);event(db,a,w['id'],'rma.created',b.fault,{'rma_id':id});return rma(db,a,id)

def rma_send(db,a,id,b,request_id):
    r=rma(db,a,id);inv.c.expected(r,b.expected_version)
    if r['state']!='draft':raise Denied(409,'RMA_STATE')
    m=inv.movement(db,a,'service_rma_send',b.reason,request_id,date.today())
    for x in r['lines']:
        p=row(db,'svc_old_parts',x['old_part_id'])
        if reversed_change(db,p['change_id']):raise Denied(409,'SERVICE_OLD_PART_UNAVAILABLE')
        balances=[v for v in balances_for(db,p['layer_id']) if v['state']=='quarantine' and v['quantity']>=x['quantity']]
        if len(balances)!=1:raise Denied(409,'RMA_PHYSICAL_HANDOVER_REQUIRED')
        v=balances[0];inv.entry(db,a,m,p['layer_id'],v['location_id'],'quarantine',-x['quantity']);inv.entry(db,a,m,p['layer_id'],v['location_id'],'supplier',x['quantity'])
    inv.c.update(db,'svc_rmas',id,{'state':'sent','version':r['version']+1});event(db,a,r['work_id'],'rma.sent',b.reason,{'rma_id':id,'movement_id':m});return rma(db,a,id)

def rma_cancel(db,a,id,b):
    r=rma(db,a,id);inv.c.expected(r,b.expected_version)
    if r['state']!='draft':raise Denied(409,'RMA_STATE')
    inv.c.update(db,'svc_rmas',id,{'state':'cancelled','version':r['version']+1});event(db,a,r['work_id'],'rma.cancelled',b.reason);return rma(db,a,id)

def rma_return(db,a,id,b,request_id):
    r=rma(db,a,id);inv.c.expected(r,b.expected_version);delivery.when(b.performed_at);row(db,'inv_locations',b.location_id)
    if r['state'] not in ('sent','processing'):raise Denied(409,'RMA_STATE')
    line=next((x for x in r['lines'] if x['id']==b.line_id),None)
    if not line:raise Denied(404,'NOT_FOUND')
    if b.quantity>line['remaining']:raise Denied(409,'RMA_RETURN_EXCEEDED')
    p=row(db,'svc_old_parts',line['old_part_id']);original=row(db,'inv_layers',p['layer_id']);m=inv.movement(db,a,'service_rma_return',b.reason,request_id,date.today())
    balance=next((x for x in balances_for(db,p['layer_id']) if x['state']=='supplier' and x['quantity']>=b.quantity),None)
    if not balance:raise Denied(409,'RMA_PHYSICAL_MISMATCH')
    inv.entry(db,a,m,p['layer_id'],balance['location_id'],'supplier',-b.quantity)
    layer=p['layer_id']
    if b.kind=='repair':
        if b.serial or b.batch:raise Denied(422,'RMA_REPAIR_REUSES_IDENTITY')
        inv.entry(db,a,m,layer,b.location_id,'pending',b.quantity)
    else:
        tr=row(db,'inv_tracking',original['sku_id']);sku=row(db,'catalog_skus',original['sku_id'])
        if tr['mode']=='sn' and (not b.serial or inv.normal_sn(b.serial)==row(db,'inv_units',p['unit_id'])['serial_normal']):raise Denied(422,'RMA_REPLACEMENT_NEW_SERIAL_REQUIRED')
        layer=inv.create_layer(db,a,m,sku,b.quantity,tr['mode'],b.serial,b.batch,b.location_id,'pending',{'unit_cost':None,'cost_status':'unknown','tax_basis':'unconfirmed','deductible_tax':None,'cost_basis':'供应商替换客户件，未转自有'},original['source_line'],ownership='customer')
    insert(db,a,'svc_rma_returns',{'id':uuid4(),'line_id':line['id'],'quantity':b.quantity,'kind':b.kind,'layer_id':layer,'movement_id':m,'performed_at':b.performed_at,'actor_id':a.actor_id,'reason':b.reason,'result':b.result})
    nextstate='returned' if sum(x['remaining'] for x in r['lines'])==b.quantity else 'sent'
    inv.c.update(db,'svc_rmas',id,{'state':nextstate,'version':r['version']+1});event(db,a,r['work_id'],'rma.returned',b.reason,{'rma_id':id,'line_id':line['id'],'kind':b.kind});return rma(db,a,id)

def rma_inspect(db,a,id,b,request_id):
    r=rma(db,a,id);inv.c.expected(r,b.expected_version);rr=row(db,'svc_rma_returns',b.return_id);line=row(db,'svc_rma_lines',rr['line_id'])
    if line['rma_id']!=id:raise Denied(404,'NOT_FOUND')
    if rows(db,'svc_rma_inspections','return_id',rr['id']):raise Denied(409,'RMA_ALREADY_INSPECTED')
    layer=row(db,'inv_layers',rr['layer_id']);balance=custody_balance(db,rr['movement_id'],layer['id'],'pending',rr['quantity'])
    if not balance:raise Denied(409,'RMA_PHYSICAL_MISMATCH')
    if b.disposition=='own_spare':
        a.require('inventory.cost');a.require('service.correct')
        if not b.passed or b.unit_cost is None or b.unit_cost<0:raise Denied(422,'RMA_OWNERSHIP_COST_REQUIRED')
    elif b.unit_cost is not None:raise Denied(422,'RMA_COST_NOT_APPLICABLE')
    if not b.passed and b.disposition not in ('hold','scrap'):raise Denied(409,'RMA_INSPECTION_FAILED')
    if b.disposition=='scrap':a.require('service.correct')
    m=inv.movement(db,a,'service_rma_inspect',b.reason,request_id,date.today());inv.entry(db,a,m,layer['id'],balance['location_id'],'pending',-rr['quantity']);new=None
    if b.disposition=='hold':inv.entry(db,a,m,layer['id'],balance['location_id'],'quarantine',rr['quantity'])
    if b.disposition=='own_spare':
        tr=row(db,'inv_tracking',layer['sku_id']);sku=row(db,'catalog_skus',layer['sku_id']);unit=row(db,'inv_units',layer['unit_id']) if layer['unit_id'] else None
        new=inv.create_layer(db,a,m,sku,rr['quantity'],tr['mode'],unit['serial_raw'] if unit else '',str(rr['id']),balance['location_id'],'qualified',{'unit_cost':b.unit_cost,'cost_status':'confirmed','tax_basis':'unconfirmed','deductible_tax':None,'cost_basis':b.ownership_basis},layer['source_line'],ownership='own')
    insert(db,a,'svc_rma_inspections',{'id':uuid4(),'return_id':rr['id'],'passed':b.passed,'disposition':b.disposition,'ownership_basis':b.ownership_basis,'new_layer_id':new,'movement_id':m,'actor_id':a.actor_id,'reason':b.reason})
    left=r['pending_quantity']-rr['quantity'];inv.c.update(db,'svc_rmas',id,{'version':r['version']+1,'state':'completed' if not left and not r['outside_quantity'] else r['state']});event(db,a,r['work_id'],'rma.inspected',b.reason,{'rma_id':id,'disposition':b.disposition});return rma(db,a,id)

def cost(db,a,id,b):
    w=detail(db,a,id);editable(w,b)
    if b.amount<0 or b.occurred_on>date.today():raise Denied(422,'SERVICE_COST_INVALID')
    if b.kind=='labor':
        if b.person_id is None or b.hours is None or b.hours<=0:raise Denied(422,'SERVICE_LABOR_BASIS_REQUIRED')
        manager(db,b.person_id)
    elif b.person_id is not None or b.hours is not None:raise Denied(422,'SERVICE_COST_INVALID')
    insert(db,a,'svc_costs',{'id':uuid4(),'work_id':id,'actor_id':a.actor_id,**b.model_dump(exclude={'expected_version','confirmed'})});bump(db,id);event(db,a,id,'cost.confirmed',b.reason);return detail(db,a,id)

def charge(db,a,id,b):
    w,d=scoped(db,a,id);inv.c.expected(w,b.expected_version)
    if w['state']=='cancelled':raise Denied(409,'SERVICE_WORK_CLOSED')
    direction='receivable' if b.kind=='customer_service' else 'payable';supplier=None
    if direction=='payable':
        if b.rma_id is None:raise Denied(422,'SERVICE_RMA_REQUIRED')
        r=rma(db,a,b.rma_id)
        if r['work_id']!=id:raise Denied(404,'NOT_FOUND')
        supplier=r['supplier_id']
    elif b.rma_id:raise Denied(422,'SERVICE_CHARGE_SOURCE_INVALID')
    cid=uuid4();insert(db,a,'svc_charges',{'id':cid,'work_id':id,'actor_id':a.actor_id,**b.model_dump(exclude={'expected_version','confirmed'}),'direction':direction,'customer_id':d['customer_id'] if direction=='receivable' else None,'supplier_id':supplier})
    bump(db,id);event(db,a,id,'charge.confirmed',b.reason,{'charge_id':cid});return row(db,'svc_charges',cid)

def reverse_change(db,a,id,b,request_id):
    w=detail(db,a,id);editable(w,b);c=row(db,'svc_changes',b.change_id)
    if c['work_id']!=id:raise Denied(404,'NOT_FOUND')
    if reversed_change(db,c['id']):raise Denied(409,'SERVICE_CHANGE_ALREADY_REVERSED')
    part=rows(db,'svc_old_parts','change_id',c['id'])[0];new=row(db,'asm_installations',c['new_installation_id']);old=row(db,'asm_installations',c['old_installation_id'])
    if new['removed_at'] or part['layer_id'] is None or rows(db,'svc_rma_lines','old_part_id',part['id']) or rows(db,'svc_dispositions','old_part_id',part['id']):raise Denied(409,'SERVICE_CHANGE_DEPENDENCY')
    if any(x['created_at']>c['created_at'] for x in [*w['returns'],*w['issues'],*w['changes'],*rows(db,'svc_spare_returns','work_id',id)]):raise Denied(409,'SERVICE_CHANGE_DEPENDENCY')
    m=inv.movement(db,a,'service_reverse',b.reason,request_id,date.today(),reverse=c['movement_id'])
    for e in inv.movement_detail(db,c['movement_id'])['entries']:
        if e['quantity']>0:
            available=db.scalar(text('SELECT quantity FROM inv_balances WHERE layer_id=:l AND location_id=:p AND state=:s'),{'l':e['layer_id'],'p':e['location_id'],'s':e['state']}) or 0
            if available!=e['quantity']:raise Denied(409,'SERVICE_CHANGE_DEPENDENCY')
        inv.entry(db,a,m,e['layer_id'],e['location_id'],e['state'],-e['quantity'])
    db.execute(text('UPDATE asm_installations SET removed_at=clock_timestamp(),correction_id=:m WHERE id=:id'),{'m':m,'id':new['id']})
    restored=uuid4();insert(db,a,'asm_installations',{'id':restored,'device_id':old['device_id'],'completion_id':old['completion_id'],'layer_id':old['layer_id'],'unit_id':old['unit_id'],'quantity':old['quantity'],'position':old['position'],'slot_id':old['slot_id'],'service_work_id':id})
    insert(db,a,'svc_change_reversals',{'id':uuid4(),'work_id':id,'actor_id':a.actor_id,'reason':b.reason,'change_id':c['id'],'movement_id':m,'restored_installation_id':restored})
    bump(db,id,True);inv.c.update(db,'svc_works',id,{'state':'working'});event(db,a,id,'replace.corrected',b.reason);return detail(db,a,id)

def reconciliation(db,a):
    differences=[]
    if inv.reconciliation(db)['differences']:differences.append('INVENTORY_PROJECTION')
    for w in rows(db,'svc_works'):
        try:w=detail(db,a,w['id'])
        except Denied as e:
            if e.code=='NOT_FOUND':continue
            raise
        expected={}
        for i in w['issues']:
            n=issue_unused(db,i)
            if n<0:differences.append('ISSUE:'+str(i['id']))
            expected[i['layer_id']]=expected.get(i['layer_id'],0)+n
        for layer,n in expected.items():
            actual=db.scalar(text("SELECT coalesce(sum(quantity),0) FROM inv_balances WHERE layer_id=:l AND location_id=:p AND state='service_issued'"),{'l':layer,'p':row(db,'svc_works',w['id'])['parts_location_id']})
            if n!=actual:differences.append('SERVICE_ISSUED:'+str(layer))
        for r in w['rmas']:
            for line in r['lines']:
                part=row(db,'svc_old_parts',line['old_part_id'])
                outside=db.scalar(text("SELECT coalesce(sum(quantity),0) FROM inv_balances WHERE layer_id=:l AND state='supplier'"),{'l':part['layer_id']})
                expected=line['remaining'] if r['state'] in ('sent','processing','returned','completed') else 0
                if outside!=expected:differences.append('RMA_OUTSIDE:'+str(line['id']))
    return {'matches':not differences,'differences':differences}


def command_access(db,a,id,b):
    """Recheck referenced objects and exceptional permissions before command replay."""
    scoped(db,a,id)
    if getattr(b,'reopen',False) or getattr(b,'disposition',None)=='scrap':a.require('service.correct')
    for field,table in [('receipt_id','svc_receipts'),('reservation_id','svc_reservations'),('issue_id','svc_issues'),('change_id','svc_changes')]:
        value=getattr(b,field,None)
        if value and row(db,table,value)['work_id']!=id:raise Denied(404,'NOT_FOUND')
    old=getattr(b,'old_installation_id',None)
    if old and row(db,'asm_installations',old)['device_id']!=row(db,'svc_works',id)['device_id']:raise Denied(404,'NOT_FOUND')

def rma_access(db,a,id,b):
    rma(db,a,id)
    if getattr(b,'disposition',None) in ('own_spare','scrap'):a.require('service.correct')
    if getattr(b,'disposition',None)=='own_spare':a.require('inventory.cost')
    line=getattr(b,'line_id',None)
    returned=getattr(b,'return_id',None)
    if returned:line=row(db,'svc_rma_returns',returned)['line_id']
    if line and row(db,'svc_rma_lines',line)['rma_id']!=id:raise Denied(404,'NOT_FOUND')


def custody_balance(db, movement_id, layer_id, state, quantity):
    """Consume only at the location recorded by this immutable custody fact.

    Caller holds the inventory domain exclusive command lock. Aggregate stock can exceed
    one return's entitlement; it cannot substitute stock at another location.
    Ambiguous/missing historical entries fail closed instead of guessing.
    """
    entries=[e for e in inv.movement_detail(db,movement_id)['entries']
             if e['layer_id']==layer_id and e['state']==state and e['quantity']>0]
    if len(entries)!=1 or entries[0]['quantity']!=quantity:return None
    return next((x for x in balances_for(db,layer_id)
                 if x['location_id']==entries[0]['location_id']
                 and x['state']==state and x['quantity']>=quantity),None)


def dispose(db,a,id,b,request_id):
    w,d=scoped(db,a,id);inv.c.expected(w,b.expected_version)
    if bool(b.old_part_id)==bool(b.return_id):raise Denied(422,'SERVICE_DISPOSITION_SOURCE_REQUIRED')
    if b.disposition=='scrap':a.require('service.correct')
    if b.old_part_id:
        p=row(db,'svc_old_parts',b.old_part_id)
        if p['work_id']!=id:raise Denied(404,'NOT_FOUND')
        if rows(db,'svc_dispositions','old_part_id',p['id']) or rows(db,'svc_rma_lines','old_part_id',p['id']) or reversed_change(db,p['change_id']):raise Denied(409,'SERVICE_PART_DEPENDENCY')
        layer=p['layer_id'];quantity=p['quantity'];custody_movement=row(db,'svc_changes',p['change_id'])['movement_id']
    else:
        rr=row(db,'svc_rma_returns',b.return_id);r=row(db,'svc_rmas',row(db,'svc_rma_lines',rr['line_id'])['rma_id'])
        if r['work_id']!=id:raise Denied(404,'NOT_FOUND')
        inspections=rows(db,'svc_rma_inspections','return_id',rr['id'])
        if not inspections or inspections[0]['disposition']!='hold' or rows(db,'svc_dispositions','return_id',rr['id']):raise Denied(409,'SERVICE_PART_DEPENDENCY')
        layer=rr['layer_id'];quantity=rr['quantity'];custody_movement=inspections[0]['movement_id']
    balance=custody_balance(db,custody_movement,layer,'quarantine',quantity)
    if not balance:raise Denied(409,'SERVICE_PART_DEPENDENCY')
    m=inv.movement(db,a,'service_rma_inspect',b.reason,request_id,date.today());inv.entry(db,a,m,layer,balance['location_id'],'quarantine',-quantity)
    insert(db,a,'svc_dispositions',{'id':uuid4(),'work_id':id,'actor_id':a.actor_id,'movement_id':m,**b.model_dump(exclude={'expected_version','confirmed'})})
    bump(db,id);event(db,a,id,'part.disposed',b.reason,{'disposition':b.disposition,'basis':b.basis});return detail(db,a,id)


def old_custody(db,p):
    if p['reversed']:return 'restored'
    if p['disposition']:return p['disposition']['disposition']
    if p['destination']=='customer':return 'customer'
    lines=rows(db,'svc_rma_lines','old_part_id',p['id'])
    if not lines:return 'quarantine'
    line=lines[0];r=row(db,'svc_rmas',line['rma_id'])
    returned=rows(db,'svc_rma_returns','line_id',line['id'])
    if sum(x['quantity'] for x in returned)<line['quantity']:return 'supplier' if r['state'] not in ('draft','cancelled') else 'quarantine'
    states=[]
    for rr in returned:
        disposed=rows(db,'svc_dispositions','return_id',rr['id']);inspected=rows(db,'svc_rma_inspections','return_id',rr['id'])
        states.append(disposed[0]['disposition'] if disposed else inspected[0]['disposition'] if inspected else 'pending')
    return states[0] if len(set(states))==1 else 'mixed'

def rma_reopen(db,a,id,b):
    r=rma(db,a,id);inv.c.expected(r,b.expected_version)
    if r['state']!='cancelled':raise Denied(409,'RMA_STATE')
    inv.c.update(db,'svc_rmas',id,{'state':'draft','version':r['version']+1});event(db,a,r['work_id'],'rma.reopened',b.reason,{'rma_id':id});return rma(db,a,id)
