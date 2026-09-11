"""Use assembly's shared-read/exclusive-write tenant transaction and stock ledger."""
from datetime import datetime,timezone,date
from decimal import Decimal
from uuid import uuid4
import json
from sqlalchemy import text
from silicon.identity.access import Denied
from silicon.inventory import service as inv
from silicon.assembly import service as asm

def ordered(db,table,column,id):
    return [dict(x) for x in db.execute(text(f'SELECT * FROM {table} WHERE {column}=:id ORDER BY created_at,id'),{'id':id}).mappings()]
def device(db,id):
    d=asm.device(db,id);l=inv.row(db,'inv_layers',d['layer_id']);d['version']=l['version']
    d['tests']=ordered(db,'del_tests','device_id',id)
    lines=inv.rows(db,'del_lines','device_id',id);d['deliveries']=[]
    active=False
    for x in lines:
        if not x['movement_id']:continue
        x['returns']=ordered(db,'del_returns','line_id',x['id']);x['acceptances']=ordered(db,'del_acceptances','line_id',x['id']);x['reversed']=bool(inv.rows(db,'del_reversals','shipment_id',x['shipment_id']))
        active|=not x['returns'] and not x['reversed'];d['deliveries'].append(x)
    latest=d['tests'][-1] if d['tests'] else None
    valid=latest and latest['completion_id']==d['completion_id'] and latest['layer_version']==l['version']
    d['eligibility']='shipped' if active else ('invalid' if d['reversed'] else (latest['result'] if valid else 'pending'))
    d['delivery_state']='shipped' if active else ('returned' if any(x['returns'] for x in d['deliveries']) else 'not_shipped')
    return d

def when(at):
    if at>datetime.now(timezone.utc):raise Denied(422,'FUTURE_EVENT')
def test(db,a,id,b):
    d=device(db,id);inv.c.expected(d,b.expected_version);when(b.performed_at)
    if d['completion_id']!=b.completion_id or d['reversed']:raise Denied(409,'COMPLETION_CHANGED')
    if d['eligibility']=='shipped' or sum(x['quantity'] for x in d['inventory'])!=1:raise Denied(409,'DEVICE_NOT_IN_STOCK')
    if any(x['state'] not in ('pending','quarantine','qualified') for x in d['inventory']):raise Denied(409,'DEVICE_STATE')
    if asm.active(db,d['layer_id']):raise Denied(409,'ACTIVE_RESERVATION')
    if len({x.name for x in b.items})!=len(b.items):raise Denied(422,'DUPLICATE_TEST_ITEM')
    # Version changes invalidate every older test, even if its execution time was backdated.
    db.execute(text('UPDATE inv_layers SET version=version+1 WHERE id=:id'),{'id':d['layer_id']})
    inv.insert(db,a,'del_tests',{'id':uuid4(),'device_id':id,'completion_id':b.completion_id,'layer_version':d['version']+1,'result':'fail' if any(x.result=='fail' for x in b.items) else 'pass','items':json.dumps([x.model_dump() for x in b.items]),'performed_at':b.performed_at,'actor_id':a.actor_id,'notes':b.notes,'report_ref':b.report_ref})
    return device(db,id)
def shipment(db,id):
    s=inv.row(db,'del_shipments',id);s['lines']=inv.rows(db,'del_lines','shipment_id',id);s['reversals']=inv.rows(db,'del_reversals','shipment_id',id)
    for x in s['lines']:
        d=asm.device(db,x['device_id']);x['serial']=d['serial'];x['number']=d['number'];x['cost']=inv.row(db,'inv_layers',x['layer_id'])['unit_cost']
        x['acceptances']=ordered(db,'del_acceptances','line_id',x['id']);x['returns']=ordered(db,'del_returns','line_id',x['id'])
        x['accepted']=bool(x['acceptances'] and x['acceptances'][-1]['accepted'])
    s['progress']=progress(db,s['order_id']);return s

def progress(db,id):
    o=inv.row(db,'sales_orders',id);lines=[x for x in inv.rows(db,'del_lines','order_id',id) if x['movement_id'] and not inv.rows(db,'del_reversals','shipment_id',x['shipment_id'])]
    returned=sum(bool(inv.rows(db,'del_returns','line_id',x['id'])) for x in lines)
    accepted=0;netaccepted=0;cost=Decimal(0)
    for x in lines:
        ar=ordered(db,'del_acceptances','line_id',x['id']);r=bool(inv.rows(db,'del_returns','line_id',x['id']))
        if ar and ar[-1]['accepted']:accepted+=1;netaccepted+=not r
        if not r:cost+=inv.row(db,'inv_layers',x['layer_id'])['unit_cost']
    quantity=o['content']['commercial']['config']['quantity']
    return {'order_id':id,'number':o['number'],'customer_name':o['content']['commercial']['customer']['name'],'quantity':quantity,'shipped':len(lines),'accepted':accepted,'returned':returned,'net_delivered':len(lines)-returned,'net_accepted':netaccepted,'remaining':quantity-len(lines)+returned,'cost':format(cost,'.2f')}
def create(db,a,b):
    inv.row(db,'sales_orders',b.order_id)
    if len(set(b.device_ids))!=len(b.device_ids):raise Denied(422,'DUPLICATE_DEVICE')
    id=uuid4();inv.insert(db,a,'del_shipments',{'id':id,**b.model_dump(exclude={'device_ids'})})
    for did in b.device_ids:
        d=device(db,did)
        if d['order_id']!=b.order_id:raise Denied(409,'ORDER_DEVICE_MISMATCH')
        inv.insert(db,a,'del_lines',{'id':uuid4(),'shipment_id':id,'order_id':b.order_id,'device_id':did,'completion_id':d['completion_id'],'layer_id':d['layer_id']})
    return shipment(db,id)
def confirm(db,a,id,b,request_id):
    s=shipment(db,id);inv.c.expected(s,b.expected_version)
    if s['state']!='draft':raise Denied(409,'SHIPMENT_STATE')
    if len(s['lines'])>s['progress']['remaining']:raise Denied(409,'ORDER_CAPACITY_EXCEEDED')
    m=inv.movement(db,a,'delivery_ship',b.reason,request_id,date.today())
    for x in s['lines']:
        d=device(db,x['device_id']);l=inv.row(db,'inv_layers',x['layer_id'])
        if d['order_id']!=s['order_id'] or d['completion_id']!=x['completion_id']:raise Denied(409,'COMPLETION_CHANGED')
        if d['eligibility']!='pass':raise Denied(409,'DEVICE_TEST_REQUIRED')
        if l['ownership']!='own' or l['unit_cost'] is None:raise Denied(409,'OWN_KNOWN_COST_REQUIRED')
        stock=d['inventory']
        if len(stock)!=1 or stock[0]['quantity']!=1 or stock[0]['state'] not in ('pending','qualified'):raise Denied(409,'DEVICE_NOT_IN_STOCK')
        if asm.active(db,l['id']):raise Denied(409,'ACTIVE_RESERVATION')
        loc=stock[0]['location_id']
        if db.scalar(text('SELECT 1 FROM asm_works WHERE wip_location_id=:id'),{'id':loc}):raise Denied(409,'DEVICE_LOCATION')
        inv.entry(db,a,m,l['id'],loc,stock[0]['state'],-1)
        db.execute(text('UPDATE inv_layers SET version=version+1 WHERE id=:id'),{'id':l['id']})
        inv.c.update(db,'del_lines',x['id'],{'location_id':loc,'test_id':d['tests'][-1]['id'],'movement_id':m})
    inv.c.update(db,'del_shipments',id,{'state':'confirmed','version':s['version']+1});return shipment(db,id)

def posted(db,id,b):
    s=shipment(db,id);inv.c.expected(s,b.expected_version)
    if s['state']!='confirmed' or s['reversals']:raise Denied(409,'SHIPMENT_NOT_ACTIVE')
    return s

def selected(s,ids):
    if len(set(ids))!=len(ids):raise Denied(422,'DUPLICATE_LINE')
    result=[]
    for id in ids:
        x=next((x for x in s['lines'] if x['id']==id),None)
        if not x:raise Denied(404,'NOT_FOUND')
        if x['returns']:raise Denied(409,'ALREADY_RETURNED')
        result.append(x)
    return result

def bump(db,id):db.execute(text('UPDATE del_shipments SET version=version+1 WHERE id=:id'),{'id':id})
def accept(db,a,id,b):
    s=posted(db,id,b);when(b.performed_at)
    for x in selected(s,b.line_ids):
        if x['accepted']:raise Denied(409,'ALREADY_ACCEPTED')
        inv.insert(db,a,'del_acceptances',{'id':uuid4(),'line_id':x['id'],'accepted':True,'corrects':x['acceptances'][-1]['id'] if x['acceptances'] else None,'performed_at':b.performed_at,'actor_id':a.actor_id,'confirmation':b.confirmation,'notes':b.notes,'evidence_ref':b.evidence_ref})
    bump(db,id);return shipment(db,id)
def correct_acceptance(db,a,id,b):
    s=posted(db,id,b);when(b.performed_at)
    record=inv.row(db,'del_acceptances',b.acceptance_id)
    x=selected(s,[record['line_id']])[0]
    if not x['accepted'] or x['acceptances'][-1]['id']!=b.acceptance_id:raise Denied(409,'ACCEPTANCE_NOT_CURRENT')
    inv.insert(db,a,'del_acceptances',{'id':uuid4(),'line_id':x['id'],'accepted':False,'corrects':b.acceptance_id,'performed_at':b.performed_at,'actor_id':a.actor_id,'confirmation':b.confirmation,'notes':b.reason,'evidence_ref':''})
    bump(db,id);return shipment(db,id)
def receive_return(db,a,id,b,request_id):
    s=posted(db,id,b);when(b.performed_at);inv.row(db,'inv_locations',b.location_id)
    if db.scalar(text('SELECT 1 FROM asm_works WHERE wip_location_id=:id'),{'id':b.location_id}):raise Denied(422,'FINISHED_LOCATION_REQUIRED')
    for x in selected(s,b.line_ids):
        # Original immutable issue entry is the cost and physical source; no current pricing.
        original=inv.movement_detail(db,x['movement_id'])
        entry=next(e for e in original['entries'] if e['layer_id']==x['layer_id'])
        if entry['quantity']!=-1:raise Denied(409,'SHIPMENT_LEDGER_MISMATCH')
        if db.scalar(text('SELECT 1 FROM inv_balances WHERE layer_id=:id AND quantity<>0'),{'id':x['layer_id']}):raise Denied(409,'DEVICE_ALREADY_IN_STOCK')
        m=inv.movement(db,a,'delivery_return',b.reason,request_id,date.today())
        inv.entry(db,a,m,x['layer_id'],b.location_id,'pending',1)
        db.execute(text('UPDATE inv_layers SET version=version+1 WHERE id=:id'),{'id':x['layer_id']})
        inv.insert(db,a,'del_returns',{'id':uuid4(),'line_id':x['id'],'location_id':b.location_id,'movement_id':m,'performed_at':b.performed_at,'actor_id':a.actor_id,'reason':b.reason})
    bump(db,id);return shipment(db,id)
def cancel(db,a,id,b):
    s=shipment(db,id);inv.c.expected(s,b.expected_version)
    if s['state']!='draft':raise Denied(409,'SHIPMENT_STATE')
    inv.c.update(db,'del_shipments',id,{'state':'cancelled','version':s['version']+1});return shipment(db,id)
def reverse(db,a,id,b,request_id):
    s=posted(db,id,b)
    if any(x['acceptances'] or x['returns'] for x in s['lines']):raise Denied(409,'DELIVERY_DOWNSTREAM_DEPENDENCY')
    original=s['lines'][0]['movement_id'];m=inv.movement(db,a,'delivery_reverse',b.reason,request_id,date.today(),reverse=original)
    for e in inv.movement_detail(db,original)['entries']:
        inv.entry(db,a,m,e['layer_id'],e['location_id'],'pending',1)
        db.execute(text('UPDATE inv_layers SET version=version+1 WHERE id=:id'),{'id':e['layer_id']})
    inv.insert(db,a,'del_reversals',{'id':uuid4(),'shipment_id':id,'movement_id':m,'actor_id':a.actor_id,'reason':b.reason});bump(db,id);return shipment(db,id)

def reconciliation(db):
    differences=[];orders=[progress(db,x['id']) for x in inv.rows(db,'sales_orders')]
    for o in orders:
        if min(o['remaining'],o['net_delivered'],o['net_accepted'])<0 or o['net_accepted']>o['net_delivered']:differences.append('ORDER_QUANTITY:'+str(o['order_id']))
    for x in inv.rows(db,'del_lines'):
        if not x['movement_id']:continue
        entries=inv.rows(db,'inv_entries','movement_id',x['movement_id'])
        if sum(e['quantity'] for e in entries if e['layer_id']==x['layer_id'])!=-1:differences.append('SHIPMENT_ENTRY:'+str(x['id']))
        for r in inv.rows(db,'del_returns','line_id',x['id']):
            entries=inv.rows(db,'inv_entries','movement_id',r['movement_id'])
            if len(entries)!=1 or entries[0]['layer_id']!=x['layer_id'] or entries[0]['quantity']!=1 or entries[0]['state']!='pending':differences.append('RETURN_ENTRY:'+str(r['id']))
    for x in inv.rows(db,'asm_devices'):
        d=device(db,x['id']);quantity=sum(v['quantity'] for v in d['inventory'])
        if d['eligibility']=='shipped' and quantity!=0:differences.append('SHIPPED_STOCK:'+str(x['id']))
    if inv.reconciliation(db)['differences']:differences.append('INVENTORY_PROJECTION')
    return {'matches':not differences,'differences':differences,'orders':orders}
