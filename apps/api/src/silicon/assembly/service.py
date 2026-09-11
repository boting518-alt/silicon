"""Identity -> catalog -> quotes -> inventory; no later identity/CRM locks."""
from uuid import uuid4
import json
from sqlalchemy import text
from silicon.identity.access import Denied
from silicon.inventory import service as inv
from silicon.quotes import service as quotes

def guard(db,a,write):
    quotes.guard(db,a,False)
    inv.guard(db,a,write)
def orders(db):
    return [{'id':x['id'],'number':x['number'],'quantity':x['content']['commercial']['config']['quantity'],'host':x['content']['commercial']['host']} for x in inv.rows(db,'sales_orders')]
def mapping(db,order):
    frozen=order['content']['commercial'];host=frozen['host'];issues=[];requirements=[];included=[]
    lines=[{'sku':host,'quantity':1,'charge_mode':'separate'},*[x for x in frozen['calculation']['technical_lines'] if x['sku']['id']!=host['id']]]
    seen=set()
    for x in lines:
        if x['charge_mode']=='included':included.append(x);continue
        sku=x['sku'];id=sku['id']
        if id in seen:issues.append('DUPLICATE_SKU:'+id);continue
        seen.add(id)
        if not db.scalar(text('SELECT 1 FROM inv_tracking WHERE id=:id'),{'id':id}):issues.append('TRACKING_REQUIRED:'+id);continue
        if x['quantity']<=0:issues.append('INVALID_QUANTITY:'+id);continue
        requirements.append({'sku_id':id,'quantity':x['quantity'],'position':sku['category']+':'+sku['number']})
    return {'requirements':requirements,'included':included,'issues':issues}
def detail(db,id):
    w=inv.row(db,'asm_works',id);w['requirements']=inv.rows(db,'asm_requirements','work_id',id);w['included']=w['mapping']['included'];w['checks']=w['mapping']['issues'];w.pop('mapping');enrich(db,w);return w
def create(db,a,b):
    order=inv.row(db,'sales_orders',b.order_id)
    allocated=db.scalar(text("SELECT count(*) FROM asm_works WHERE order_id=:id AND state<>'cancelled'"),{'id':b.order_id})
    if allocated>=order['content']['commercial']['config']['quantity']:raise Denied(409,'ORDER_CAPACITY_EXCEEDED')
    sku=inv.row(db,'catalog_skus',b.product_sku_id);track=inv.row(db,'inv_tracking',b.product_sku_id)
    if sku['category']!='host' or not sku['enabled'] or track['mode']!='sn':raise Denied(422,'PRODUCT_SN_HOST_REQUIRED')
    if not db.scalar(text('SELECT 1 FROM memberships WHERE user_id=:id AND active'),{'id':b.manager_id}):raise Denied(422,'MANAGER_INACTIVE')
    m=mapping(db,order);id=uuid4();loc=uuid4()
    inv.insert(db,a,'inv_locations',{'id':loc,'warehouse':'装配在制','name':str(id)})
    values={**b.model_dump(),'id':id,'state':'draft','version':1,'wip_location_id':loc}
    inv.insert(db,a,'asm_works',{**values,'mapping':json.dumps(m)})
    for r in m['requirements']:inv.insert(db,a,'asm_requirements',{'id':uuid4(),'work_id':id,**r})
    return detail(db,id)

from datetime import datetime,timezone,timedelta

def bump(db,id):db.execute(text('UPDATE asm_works SET version=version+1 WHERE id=:id'),{'id':id})
def event(db,a,id,action,reason):inv.insert(db,a,'asm_events',{'id':uuid4(),'work_id':id,'action':action,'reason':reason,'actor_id':a.actor_id})
def active(db,layer,location=None):
    return sum(db.scalar(text("SELECT coalesce(sum(quantity-consumed-released),0) FROM "+table+" WHERE layer_id=:l AND expires_at>clock_timestamp()"+(' AND location_id=:p' if location else '')),{'l':layer,'p':location}) for table in ('asm_reservations','svc_reservations'))
def expire(db,a):
    rows=list(db.execute(text('SELECT * FROM asm_reservations WHERE expires_at<=clock_timestamp() AND quantity>consumed+released')).mappings())
    for r in rows:
        db.execute(text('UPDATE asm_reservations SET released=quantity-consumed WHERE id=:id'),{'id':r['id']})
        event(db,a,r['work_id'],'reservation.expired','服务端UTC到期释放')
    for id in {r['work_id'] for r in rows}:bump(db,id)
    return len(rows)
def enrich(db,w):
    w['reservations']=inv.rows(db,'asm_reservations','work_id',w['id'])
    now=datetime.now(timezone.utc)
    for req in w['requirements']:
        rs=[r for r in w['reservations'] if r['requirement_id']==req['id']]
        req['reserved']=sum(r['quantity']-r['consumed']-r['released'] for r in rs if r['expires_at']>now)
        req['issued']=issued(db,req['id'])
        req['missing']=max(0,req['quantity']-req['reserved']-req['issued'])
    w['history']=inv.rows(db,'asm_events','work_id',w['id'])
    w['issues']=inv.rows(db,'asm_issues','work_id',w['id'])
    w['devices']=inv.rows(db,'asm_devices','work_id',w['id'])
    w['completions']=completions(db,w['id'])
    for d in w['devices']:
        latest=next(x for x in reversed(w['completions']) if x['device_id']==d['id'])
        d['movement_id']=latest['movement_id']
    w['wip_cost']=format(sum((x['quantity']*x['unit_cost'] for x in wip(db,w)),Decimal(0)),'.2f')
def ready(db,a,id,b):
    w=detail(db,id);inv.c.expected(w,b.expected_version)
    if w['state']!='draft':raise Denied(409,'WORK_STATE')
    m=mapping(db,inv.row(db,'sales_orders',w['order_id']))
    if m['issues']:raise Denied(422,'MAPPING_INCOMPLETE')
    # Refresh missing draft tracking mappings only before confirming any demand.
    existing={str(r['sku_id']) for r in w['requirements']}
    for r in m['requirements']:
        if str(r['sku_id']) not in existing:inv.insert(db,a,'asm_requirements',{'id':uuid4(),'work_id':id,**r})
    db.execute(text("UPDATE asm_works SET state='ready',mapping=CAST(:m AS jsonb),version=version+1 WHERE id=:id"),{'m':json.dumps(m),'id':id})
    event(db,a,id,'ready',b.reason);return detail(db,id)
def reserve(db,a,id,b,request_id):
    w=detail(db,id);inv.c.expected(w,b.expected_version)
    # Validate the caller version before our own housekeeping increments it.
    # Both remain under the same inventory transaction lock.
    expire(db,a);w=detail(db,id)
    if w['state'] not in ('ready','in_progress'):raise Denied(409,'WORK_STATE')
    now=datetime.now(timezone.utc)
    expires_at=b.expires_at if b.expires_at is not None else now+timedelta(hours=b.duration_hours)
    if expires_at<=now:raise Denied(422,'RESERVATION_EXPIRED')
    req=next((r for r in w['requirements'] if r['id']==b.requirement_id),None)
    if not req:raise Denied(404,'NOT_FOUND')
    if b.quantity>req['missing']:raise Denied(409,'DEMAND_EXCEEDED')
    sources=db.execute(text("""SELECT l.*,b.location_id,b.quantity AS balance FROM inv_layers l JOIN inv_balances b ON b.layer_id=l.id AND b.tenant_id=l.tenant_id WHERE l.sku_id=:sku AND l.ownership='own' AND b.state='qualified' AND b.quantity>0 ORDER BY l.created_at,l.id,b.location_id"""),{'sku':req['sku_id']}).mappings()
    left=b.quantity
    for source in sources:
        n=min(left,source['balance']-active(db,source['id'],source['location_id']))
        if n<=0:continue
        inv.insert(db,a,'asm_reservations',{'id':uuid4(),'work_id':id,'requirement_id':req['id'],'layer_id':source['id'],'location_id':source['location_id'],'quantity':n,'expires_at':expires_at})
        left-=n
        if not left:break
    if left:raise Denied(409,'INSUFFICIENT_AVAILABLE_STOCK')
    job=uuid4()
    db.execute(text("INSERT INTO jobs(id,kind,dedupe_key,tenant_id,actor_id,request_id,available_at) VALUES (:id,'assembly.expire',:key,:t,:a,:r,:at)"),{'id':job,'key':'assembly.expire:'+str(job),'t':a.tenant_id,'a':a.actor_id,'r':request_id,'at':expires_at})
    event(db,a,id,'reserved',b.reason);bump(db,id);return detail(db,id)
def release(db,a,id,b,cancel=False):
    w=detail(db,id);inv.c.expected(w,b.expected_version)
    if w['state'] in ('completed','cancelled') or (cancel and w['state']=='in_progress'):raise Denied(409,'WORK_STATE')
    db.execute(text('UPDATE asm_reservations SET released=quantity-consumed WHERE work_id=:id AND quantity>consumed+released'),{'id':id})
    if cancel:db.execute(text("UPDATE asm_works SET state='cancelled' WHERE id=:id"),{'id':id})
    bump(db,id);event(db,a,id,'cancelled' if cancel else 'released',b.reason);return detail(db,id)

from decimal import Decimal
from datetime import date

def issued(db,requirement):
    return db.scalar(text("""SELECT coalesce(sum(l.quantity),0) FROM asm_issue_lines l JOIN asm_issues i ON i.tenant_id=l.tenant_id AND i.id=l.issue_id JOIN asm_reservations r ON r.tenant_id=l.tenant_id AND r.id=l.reservation_id WHERE r.requirement_id=:r AND NOT EXISTS(SELECT 1 FROM inv_movements m WHERE m.reverse_of=i.movement_id)"""),{'r':requirement})
def wip(db,w):
    return list(db.execute(text("SELECT b.*,l.unit_cost,l.unit_id,l.sku_id,l.cost_status FROM inv_balances b JOIN inv_layers l ON l.id=b.layer_id AND l.tenant_id=b.tenant_id WHERE b.location_id=:id AND b.state='wip' AND b.quantity>0"),{'id':w['wip_location_id']}).mappings())
def issue(db,a,id,b,request_id):
    # Expiry is checked after acquiring the common lock; never consume an expired row.
    w=detail(db,id);inv.c.expected(w,b.expected_version)
    if w['state'] not in ('ready','in_progress'):raise Denied(409,'WORK_STATE')
    if len({x.reservation_id for x in b.lines})!=len(b.lines):raise Denied(422,'DUPLICATE_RESERVATION')
    m=inv.movement(db,a,'assembly_issue',b.reason,request_id,date.today());iid=uuid4()
    inv.insert(db,a,'asm_issues',{'id':iid,'work_id':id,'movement_id':m})
    entries={}
    for x in b.lines:
        r=inv.row(db,'asm_reservations',x.reservation_id)
        if r['work_id']!=id:raise Denied(404,'NOT_FOUND')
        if r['expires_at']<=datetime.now(timezone.utc):raise Denied(409,'RESERVATION_EXPIRED')
        if x.quantity>r['quantity']-r['consumed']-r['released']:raise Denied(409,'RESERVATION_EXCEEDED')
        l=inv.row(db,'inv_layers',r['layer_id'])
        if l['unit_cost'] is None:raise Denied(422,'UNKNOWN_COST:'+str(l['id']))
        inv.insert(db,a,'asm_issue_lines',{'id':uuid4(),'issue_id':iid,'reservation_id':r['id'],'quantity':x.quantity})
        db.execute(text('UPDATE asm_reservations SET consumed=consumed+:q WHERE id=:id'),{'q':x.quantity,'id':r['id']})
        for loc,state,n in [(r['location_id'],'qualified',-x.quantity),(w['wip_location_id'],'wip',x.quantity)]:
            key=(r['layer_id'],loc,state);entries[key]=entries.get(key,0)+n
    for (layer,loc,state),n in entries.items():inv.entry(db,a,m,layer,loc,state,n)
    for layer in {x[0] for x in entries}:db.execute(text('UPDATE inv_layers SET version=version+1 WHERE id=:id'),{'id':layer})
    db.execute(text("UPDATE asm_works SET state='in_progress',version=version+1 WHERE id=:id"),{'id':id});event(db,a,id,'issued',b.reason)
    return detail(db,id)
def completions(db,work_id):
    return [dict(x) for x in db.execute(text('SELECT * FROM asm_completions WHERE work_id=:w ORDER BY completed_at,id'),{'w':work_id}).mappings()]

def correction_source(db,w,b,sn):
    history=completions(db,w['id'])
    existing=list(db.execute(text('SELECT * FROM inv_units WHERE sku_id=:s AND serial_normal=:sn'),{'s':w['product_sku_id'],'sn':sn}).mappings())
    if b.correction_of is None:
        if existing:raise Denied(409,'SERIAL_ALREADY_EXISTS')
        if history:raise Denied(409,'CORRECTION_SOURCE_REQUIRED')
        return None
    source=inv.row(db,'asm_completions',b.correction_of)
    if source['work_id']!=w['id']:raise Denied(409,'CORRECTION_SOURCE_MISMATCH')
    device=inv.row(db,'asm_devices',source['device_id'])
    if len(existing)!=1 or existing[0]['id']!=device['inventory_unit_id']:raise Denied(409,'CORRECTION_SOURCE_MISMATCH')
    if not source['reversed_by'] or not db.scalar(text('SELECT 1 FROM inv_movements WHERE id=:r AND reverse_of=:m'),{'r':source['reversed_by'],'m':source['movement_id']}):raise Denied(409,'COMPLETION_NOT_REVERSED')
    if not history or history[-1]['id']!=source['id']:raise Denied(409,'CORRECTION_SOURCE_NOT_LATEST')
    unit=existing[0]
    layers=inv.rows(db,'inv_layers','unit_id',unit['id'])
    for layer in layers:
        if db.scalar(text('SELECT 1 FROM inv_balances WHERE layer_id=:l AND quantity<>0'),{'l':layer['id']}) or active(db,layer['id']):raise Denied(409,'CORRECTION_DEPENDENCY')
        if db.scalar(text("SELECT 1 FROM inv_entries e JOIN inv_movements m ON m.id=e.movement_id AND m.tenant_id=e.tenant_id WHERE e.layer_id=:l AND m.kind<>'reverse' AND NOT EXISTS(SELECT 1 FROM inv_movements r WHERE r.reverse_of=m.id)"),{'l':layer['id']}):raise Denied(409,'CORRECTION_DEPENDENCY')
    if db.scalar(text('SELECT 1 FROM asm_installations WHERE unit_id=:u AND removed_at IS NULL'),{'u':unit['id']}):raise Denied(409,'CORRECTION_DEPENDENCY')
    return device,unit

def complete(db,a,id,b,request_id):
    w=detail(db,id);inv.c.expected(w,b.expected_version)
    if w['state']!='in_progress':raise Denied(409,'WORK_STATE')
    if w['checks'] or not w['requirements'] or any(r['issued']!=r['quantity'] for r in w['requirements']):raise Denied(409,'MATERIALS_INCOMPLETE')
    parts=wip(db,w)
    if sum(x['quantity'] for x in parts)!=sum(r['quantity'] for r in w['requirements']):raise Denied(409,'WIP_MISMATCH')
    if any(x['unit_cost'] is None for x in parts):raise Denied(422,'UNKNOWN_COST')
    loc=inv.row(db,'inv_locations',b.location_id)
    if db.scalar(text('SELECT 1 FROM asm_works WHERE wip_location_id=:id'),{'id':loc['id']}):raise Denied(422,'FINISHED_LOCATION_REQUIRED')
    product=inv.c.sku(db,w['product_sku_id']).model_dump(mode='json')
    if not product['enabled'] or product['category']!='host' or inv.row(db,'inv_tracking',w['product_sku_id'])['mode']!='sn':raise Denied(422,'PRODUCT_SN_HOST_REQUIRED')
    sn=inv.normal_sn(b.serial)
    correcting=correction_source(db,w,b,sn)
    amount=sum((x['quantity']*x['unit_cost'] for x in parts),Decimal(0))
    m=inv.movement(db,a,'assembly_complete',b.reason,request_id,date.today())
    for x in parts:inv.entry(db,a,m,x['layer_id'],w['wip_location_id'],'wip',-x['quantity'])
    cost={'unit_cost':amount,'deductible_tax':None,'cost_basis':'仅实际领料成本合计','tax_basis':'unconfirmed','cost_status':'provisional' if any(x['cost_status']=='provisional' for x in parts) else 'confirmed'}
    sku=inv.row(db,'catalog_skus',w['product_sku_id'])
    if correcting:sku['manufacturer_id']=correcting[1]['manufacturer_id']
    layer=inv.create_layer(db,a,m,sku,1,'sn',correcting[1]['serial_raw'] if correcting else b.serial,'',b.location_id,'pending',cost,assembly_correction=correcting[0]['id'] if correcting else None)
    finished=inv.row(db,'inv_layers',layer);did=correcting[0]['id'] if correcting else uuid4();cid=uuid4()
    if not correcting:inv.insert(db,a,'asm_devices',{'id':did,'work_id':id,'inventory_unit_id':finished['unit_id'],'layer_id':layer,'movement_id':m,'number':'DEV-'+str(did),'product':json.dumps(product)})
    elif finished['unit_id']!=correcting[1]['id']:raise Denied(409,'CORRECTION_SOURCE_MISMATCH')
    inv.insert(db,a,'asm_completions',{'id':cid,'device_id':did,'work_id':id,'layer_id':layer,'movement_id':m,'correction_of':b.correction_of})
    for x in parts:
        req=next(r for r in w['requirements'] if r['sku_id']==x['sku_id'])
        inv.insert(db,a,'asm_installations',{'id':uuid4(),'device_id':did,'completion_id':cid,'layer_id':x['layer_id'],'unit_id':x['unit_id'],'quantity':x['quantity'],'position':req['position']})
    db.execute(text("UPDATE asm_works SET state='completed',version=version+1 WHERE id=:id"),{'id':id});event(db,a,id,'completed',b.reason)
    return detail(db,id)
def reverse(db,a,id,b,request_id):
    w=detail(db,id);inv.c.expected(w,b.expected_version);m=inv.movement_detail(db,b.movement_id)
    issue=db.execute(text('SELECT * FROM asm_issues WHERE work_id=:w AND movement_id=:m'),{'w':id,'m':b.movement_id}).mappings().first()
    device=db.execute(text('SELECT * FROM asm_completions WHERE work_id=:w AND movement_id=:m'),{'w':id,'m':b.movement_id}).mappings().first()
    if not issue and not device:raise Denied(404,'NOT_FOUND')
    if db.scalar(text('SELECT 1 FROM inv_movements WHERE reverse_of=:id'),{'id':m['id']}):raise Denied(409,'ALREADY_REVERSED')
    if device and db.scalar(text('SELECT 1 FROM del_lines WHERE device_id=:id AND movement_id IS NOT NULL'),{'id':device['device_id']}):raise Denied(409,'DELIVERY_DEPENDENCY')
    if issue and w['state']=='completed':raise Denied(409,'MOVEMENT_DEPENDENCY')
    # Check each positive destination is intact; later live movements must reverse first.
    for e in m['entries']:
        if active(db,e['layer_id']):raise Denied(409,'ACTIVE_RESERVATION')
        later=db.scalar(text("SELECT x.id FROM inv_movements x JOIN inv_entries e ON e.tenant_id=x.tenant_id AND e.movement_id=x.id WHERE e.layer_id=:l AND x.created_at>:at AND x.kind<>'reverse' AND NOT EXISTS(SELECT 1 FROM inv_movements r WHERE r.reverse_of=x.id) LIMIT 1"),{'l':e['layer_id'],'at':m['created_at']})
        if later:raise Denied(409,'MOVEMENT_DEPENDENCY:'+str(later))
    rid=inv.movement(db,a,'reverse',b.reason,request_id,date.today(),reverse=m['id'])
    for e in m['entries']:inv.entry(db,a,rid,e['layer_id'],e['location_id'],e['state'],-e['quantity'])
    if device:
        db.execute(text('UPDATE asm_completions SET reversed_by=:r WHERE id=:id'),{'r':rid,'id':device['id']})
        db.execute(text('UPDATE asm_installations SET removed_at=clock_timestamp(),correction_id=:r WHERE completion_id=:d'),{'r':rid,'d':device['id']})
    for layer in {e['layer_id'] for e in m['entries']}:db.execute(text('UPDATE inv_layers SET version=version+1 WHERE id=:id'),{'id':layer})
    db.execute(text("UPDATE asm_works SET state='in_progress',version=version+1 WHERE id=:id"),{'id':id});event(db,a,id,'reversed',b.reason)
    return detail(db,id)
def device(db,id):
    d=inv.row(db,'asm_devices',id);w=inv.row(db,'asm_works',d['work_id']);order=inv.row(db,'sales_orders',w['order_id']);commercial=order['content']['commercial'];customer=commercial['customer']
    history=[x for x in completions(db,w['id']) if x['device_id']==d['id']];current=history[-1]
    d['completions']=history;d['completion_id']=current['id']
    for field in ('layer_id','movement_id','completed_at'):d[field]=current[field]
    unit=inv.row(db,'inv_units',d['inventory_unit_id']);d['serial']=unit['serial_raw'];d['order_id']=order['id'];d['order_number']=order['number'];d['contract_id']=order['contract_version_id'];d['contract_number']=order['content']['fields']['number'];d['quote_version_id']=order['quote_version_id'];d['customer_name']=customer['name'];d['customer_id']=customer['id'];d['project_id']=commercial['config']['project_id']
    d['reversed']=bool(db.scalar(text('SELECT 1 FROM inv_movements WHERE reverse_of=:id'),{'id':d['movement_id']}))
    d['inventory']=[dict(x) for x in db.execute(text('SELECT location_id,state,quantity FROM inv_balances WHERE layer_id=:id AND quantity>0'),{'id':d['layer_id']}).mappings()]
    d['cost']='0.00' if d['reversed'] else str(inv.row(db,'inv_layers',d['layer_id'])['unit_cost']);d['cost_scope']='仅实际领料成本';d['delivery_state']='not_started'
    d['installations']=inv.rows(db,'asm_installations','device_id',id)
    for x in d['installations']:
        layer=inv.row(db,'inv_layers',x['layer_id']);sku=inv.row(db,'catalog_skus',layer['sku_id'])
        x['sku_id']=sku['id'];x['sku_number']=sku['number'];x['source_movement']=layer['source_movement'];x['source_line']=layer['source_line'];x['serial']=inv.row(db,'inv_units',x['unit_id'])['serial_raw'] if x['unit_id'] else None
        x['batch']=db.scalar(text('SELECT batch FROM inv_lots WHERE layer_id=:id'),{'id':layer['id']})
    return d

def public(a,value):
    if isinstance(value,list):return [public(a,x) for x in value]
    if isinstance(value,dict):return {k:public(a,v) for k,v in value.items() if not (k in ('wip_cost','cost','issued_cost','finished_cost') and 'inventory.cost' not in a.permissions)}
    return value

def edit(db,a,id,b):
    w=detail(db,id);inv.c.expected(w,b.expected_version)
    if w['state']!='draft':raise Denied(409,'WORK_STATE')
    sku=inv.row(db,'catalog_skus',b.product_sku_id);track=inv.row(db,'inv_tracking',b.product_sku_id)
    if sku['category']!='host' or not sku['enabled'] or track['mode']!='sn':raise Denied(422,'PRODUCT_SN_HOST_REQUIRED')
    if not db.scalar(text('SELECT 1 FROM memberships WHERE user_id=:id AND active'),{'id':b.manager_id}):raise Denied(422,'MANAGER_INACTIVE')
    inv.c.update(db,'asm_works',id,{**b.model_dump(exclude={'expected_version'}),'version':w['version']+1})
    event(db,a,id,'draft.saved','修改计划资料');return detail(db,id)
def reconciliation(db,id):
    w=detail(db,id)
    issued_cost=db.scalar(text("""SELECT coalesce(sum(x.quantity*l.unit_cost),0) FROM asm_issue_lines x JOIN asm_issues i ON i.id=x.issue_id AND i.tenant_id=x.tenant_id JOIN asm_reservations r ON r.id=x.reservation_id AND r.tenant_id=x.tenant_id JOIN inv_layers l ON l.id=r.layer_id AND l.tenant_id=r.tenant_id WHERE i.work_id=:id AND NOT EXISTS(SELECT 1 FROM inv_movements m WHERE m.reverse_of=i.movement_id)"""),{'id':id})
    outputs=list(db.execute(text('SELECT d.*,l.unit_cost FROM asm_completions d JOIN inv_layers l ON l.id=d.layer_id AND l.tenant_id=d.tenant_id WHERE d.work_id=:id AND NOT EXISTS(SELECT 1 FROM inv_movements m WHERE m.reverse_of=d.movement_id)'),{'id':id}).mappings())
    finished_cost=sum((d['unit_cost'] for d in outputs),Decimal(0));wip_cost=Decimal(w['wip_cost']);differences=[]
    if issued_cost!=finished_cost+wip_cost:differences.append('ISSUED_WIP_FINISHED_COST')
    projection=inv.reconciliation(db)
    related={r['layer_id'] for r in w['reservations']}|{d['layer_id'] for d in outputs}
    differences.extend('LAYER_PROJECTION:'+str(x['layer_id']) for x in projection['differences'] if x['layer_id'] in related)
    return {'work_id':id,'issued_quantity':sum(r['issued'] for r in w['requirements']),'wip_quantity':sum(x['quantity'] for x in wip(db,w)),'completed_quantity':len(outputs),'issued_cost':format(issued_cost,'.2f'),'wip_cost':format(wip_cost,'.2f'),'finished_cost':format(finished_cost,'.2f'),'matches':not differences,'differences':differences}
