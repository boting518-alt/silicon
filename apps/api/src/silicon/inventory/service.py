"""Session/membership -> catalog(shared) -> inventory tenant guard.
One shared read / exclusive write boundary keeps aggregates and ledger consistent.
Never acquire identity, quote or CRM locks after this guard.
"""
import json,hashlib
from uuid import uuid4,UUID
from sqlalchemy import text
from silicon.identity.access import Denied,audit
from silicon.catalog import service as c

def guard(db,a,write):
    c.guard(db,a,False)
    fn='pg_advisory_xact_lock' if write else 'pg_advisory_xact_lock_shared'
    db.execute(text(f'SELECT {fn}(hashtextextended(:k,0))'),{'k':'inventory:'+str(a.tenant_id)})
def serial(v):return json.loads(json.dumps(v,default=str))
def row(db,table,id):return c.row(db,table,id)
def insert(db,a,table,values):c.insert(db,table,{'tenant_id':a.tenant_id,**values})
def command(db,a,op,key,body,request_id,perform):
    if not key or len(key)>128:raise Denied(422,'IDEMPOTENCY_KEY_REQUIRED')
    digest=hashlib.sha256(json.dumps(serial(body),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    args={'t':a.tenant_id,'u':a.actor_id,'o':op,'k':key}
    old=db.execute(text('SELECT * FROM inv_commands WHERE tenant_id=:t AND actor_id=:u AND operation=:o AND key=:k'),args).mappings().first()
    if old:
        if old['request_hash']!=digest:raise Denied(409,'IDEMPOTENCY_CONFLICT')
        return old['response']
    result=serial(perform())
    db.execute(text('INSERT INTO inv_commands VALUES (:t,:u,:o,:k,:h,CAST(:r AS jsonb))'),{**args,'h':digest,'r':json.dumps(result)})
    audit(db,a.actor_id,a.tenant_id,op,result.get('id',op),'allowed',request_id)
    return result

def supplier(db,a,body,id=None):
    data=body.model_dump(exclude={'expected_version'})
    if not data['name'].strip():raise Denied(422,'NAME_REQUIRED')
    if id:
        old=row(db,'inv_suppliers',id);c.expected(old,body.expected_version)
        c.update(db,'inv_suppliers',id,{**data,'version':old['version']+1})
    else:
        if body.expected_version:raise Denied(409,'VERSION_CONFLICT')
        id=uuid4();insert(db,a,'inv_suppliers',{'id':id,**data,'version':1})
    return row(db,'inv_suppliers',id)

def rows(db,table,parent=None,id=None):
    return [dict(x) for x in db.execute(text(f'SELECT * FROM {table}'+(f' WHERE {parent}=:id' if parent else '')+' ORDER BY id'),{'id':id}).mappings()]
def tracking(db,a,id,body):
    sku=row(db,'catalog_skus',id)
    old=db.execute(text('SELECT * FROM inv_tracking WHERE id=:id'),{'id':id}).mappings().first()
    if old:
        c.expected(old,body.expected_version)
        # Additional inventory transaction check is applied when ledger tables exist.
        if db.scalar(text("SELECT to_regclass('public.inv_layers')")) and db.scalar(text('SELECT 1 FROM inv_layers WHERE sku_id=:id LIMIT 1'),{'id':id}):raise Denied(409,'TRACKING_FROZEN')
        c.update(db,'inv_tracking',id,{'mode':body.mode,'unit':body.unit,'version':old['version']+1})
    else:
        if body.expected_version:raise Denied(409,'VERSION_CONFLICT')
        insert(db,a,'inv_tracking',{'id':id,'mode':body.mode,'unit':body.unit,'version':1})
    return row(db,'inv_tracking',id)
def contract_detail(db,id):
    v=row(db,'inv_contracts',id);v['lines']=rows(db,'inv_contract_lines','contract_id',id);v['amendments']=rows(db,'inv_amendments','contract_id',id);v['version']+=len(v['amendments']);return v

def contract_save(db,a,body,id=None):
    supplier=row(db,'inv_suppliers',body.supplier_id)
    if not supplier['enabled']:raise Denied(422,'SUPPLIER_DISABLED')
    if not db.scalar(text('SELECT 1 FROM memberships WHERE user_id=:u AND active'),{'u':body.manager_id}):raise Denied(422,'MANAGER_INACTIVE')
    values=body.model_dump(exclude={'lines','expected_version'})
    if id:
        old=row(db,'inv_contracts',id);c.expected(old,body.expected_version)
        if old['state']!='draft':raise Denied(409,'FROZEN_CONTRACT')
        c.update(db,'inv_contracts',id,{**values,'version':old['version']+1});db.execute(text('DELETE FROM inv_contract_lines WHERE contract_id=:id'),{'id':id})
    else:
        if body.expected_version:raise Denied(409,'VERSION_CONFLICT')
        id=uuid4();insert(db,a,'inv_contracts',{'id':id,**values,'state':'draft','version':1})
    for line in body.lines:
        if not row(db,'catalog_skus',line.sku_id)['enabled']:raise Denied(422,'SKU_DISABLED')
        row(db,'inv_tracking',line.sku_id)
        insert(db,a,'inv_contract_lines',{'id':uuid4(),'contract_id':id,**line.model_dump()})
    return contract_detail(db,id)
def contract_activate(db,a,id,body):
    v=contract_detail(db,id);c.expected(v,body.expected_version)
    if not body.confirmed:raise Denied(422,'CONFIRM_REQUIRED')
    if v['state']!='draft':raise Denied(409,'FROZEN_CONTRACT')
    supplier=row(db,'inv_suppliers',v['supplier_id'])
    if not supplier['enabled']:raise Denied(422,'SUPPLIER_DISABLED')
    snapshot=serial({'supplier':supplier,'buyer':v['buyer'],'manager_id':v['manager_id'],'signing_date':v['signing_date'],'currency':'CNY','attachments':rows(db,'inv_attachments','contract_id',id),'lines':[{**l,'sku':c.sku(db,l['sku_id']).model_dump(mode='json')} for l in v['lines']]})
    db.execute(text("UPDATE inv_contracts SET state='active',version=version+1,snapshot=CAST(:s AS jsonb) WHERE id=:id"),{'s':json.dumps(snapshot),'id':id})
    return contract_detail(db,id)
def cancelled(db,line):return db.scalar(text('SELECT coalesce(sum(quantity),0) FROM inv_cancellations WHERE line_id=:id'),{'id':line})
def order_detail(db,id):
    v=row(db,'inv_orders',id);v['lines']=rows(db,'inv_order_lines','order_id',id)
    for l in v['lines']:
        source=row(db,'inv_contract_lines',l['contract_line_id']);l.update(sku_id=source['sku_id'],unit_price=source['unit_price'],tax_basis=source['tax_basis'],due_date=source['due_date'],cancelled=cancelled(db,l['id']),received=net_received(db,l['id']))
    return v

def order_create(db,a,body):
    contract=contract_detail(db,body.contract_id)
    if contract['state']!='active':raise Denied(409,'CONTRACT_NOT_ACTIVE')
    id=uuid4();insert(db,a,'inv_orders',{'id':id,'number':body.number,'contract_id':body.contract_id,'supplier_confirmation':body.supplier_confirmation,'state':'draft','version':1})
    for l in body.lines:
        src=row(db,'inv_contract_lines',l.contract_line_id)
        if src['contract_id']!=body.contract_id:raise Denied(404,'NOT_FOUND')
        allocated=db.scalar(text('SELECT coalesce(sum(quantity),0) FROM inv_order_lines WHERE contract_line_id=:id'),{'id':l.contract_line_id})
        released=db.scalar(text('SELECT coalesce(sum(x.quantity),0) FROM inv_cancellations x JOIN inv_order_lines l ON l.id=x.line_id AND l.tenant_id=x.tenant_id WHERE l.contract_line_id=:id'),{'id':l.contract_line_id})
        extra=db.scalar(text('SELECT coalesce(sum(extra_quantity),0) FROM inv_amendments WHERE line_id=:id'),{'id':src['id']})
        if allocated-released+l.quantity>src['quantity']+extra:raise Denied(409,'CONTRACT_CAPACITY_EXCEEDED')
        insert(db,a,'inv_order_lines',{'id':uuid4(),'order_id':id,**l.model_dump()})
    return order_detail(db,id)
def order_confirm(db,a,id,body):
    v=row(db,'inv_orders',id);c.expected(v,body.expected_version)
    if not body.confirmed:raise Denied(422,'CONFIRM_REQUIRED')
    if v['state']!='draft':raise Denied(409,'ORDER_ALREADY_CONFIRMED')
    c.update(db,'inv_orders',id,{'state':'confirmed','version':v['version']+1});return order_detail(db,id)
from decimal import Decimal
from datetime import date,datetime,timezone
import unicodedata

def cost_filter(a,value):
    if 'inventory.cost' in a.permissions:return value
    forbidden={'unit_price','unit_cost','deductible_tax','cost_status','cost_basis','known_cost','total_cost','unknown_quantity','cost_complete','amount','snapshot','ledger_cost','projected_cost','cost_projection'}
    if isinstance(value,list):return [cost_filter(a,x) for x in value]
    if isinstance(value,dict):return {k:cost_filter(a,v) for k,v in value.items() if k not in forbidden}
    return value

def location(db,a,b):
    id=uuid4();insert(db,a,'inv_locations',{'id':id,**b.model_dump()});return row(db,'inv_locations',id)
def receipt_detail(db,id):
    r=row(db,'inv_receipts',id);r['lines']=rows(db,'inv_receipt_lines','receipt_id',id)
    r['movement_id']=db.scalar(text('SELECT id FROM inv_movements WHERE receipt_id=:id'),{'id':id});return r

def normal_sn(s):
    v=unicodedata.normalize('NFC',s.strip())
    if not v or len(v)>120 or any(ord(x)<32 for x in v):raise Denied(422,'SERIAL_INVALID')
    return v

def receipt_create(db,a,b):
    o=row(db,'inv_orders',b.order_id);row(db,'inv_locations',b.location_id)
    if o['state']!='confirmed':raise Denied(409,'ORDER_NOT_CONFIRMED')
    if b.received_on>date.today():raise Denied(422,'FUTURE_RECEIPT')
    id=uuid4();insert(db,a,'inv_receipts',{'id':id,'order_id':b.order_id,'received_on':b.received_on,'location_id':b.location_id,'state':'draft','version':1})
    for l in b.lines:
        src=row(db,'inv_order_lines',l.order_line_id)
        if src['order_id']!=b.order_id:raise Denied(404,'NOT_FOUND')
        if l.cost_status!='unknown':
            a.require('inventory.cost')
            if l.unit_cost is None or not l.cost_basis.strip():raise Denied(422,'COST_BASIS_REQUIRED')
        elif l.unit_cost is not None or l.deductible_tax is not None:raise Denied(422,'UNKNOWN_COST_MUST_BE_NULL')
        values=l.model_dump();values['serials']=json.dumps(values['serials'])
        # JSON adaptation is explicit instead of driver-dependent dict coercion.
        db.execute(text('''INSERT INTO inv_receipt_lines(tenant_id,id,receipt_id,order_line_id,quantity,serials,batch,cost_status,unit_cost,deductible_tax,cost_basis)
          VALUES (:tenant,:id,:receipt,:order_line_id,:quantity,CAST(:serials AS jsonb),:batch,:cost_status,:unit_cost,:deductible_tax,:cost_basis)'''),{'tenant':a.tenant_id,'id':uuid4(),'receipt':id,**values})
    return receipt_detail(db,id)

def net_received(db,line):
    return db.scalar(text('''SELECT coalesce(sum(l.quantity),0) FROM inv_receipt_lines l JOIN inv_movements m ON m.receipt_id=l.receipt_id AND m.tenant_id=l.tenant_id WHERE l.order_line_id=:id AND NOT EXISTS(SELECT 1 FROM inv_movements r WHERE r.reverse_of=m.id)'''),{'id':line})
def movement(db,a,kind,reason,request_id,effective,receipt=None,reverse=None):
    id=uuid4();insert(db,a,'inv_movements',{'id':id,'kind':kind,'reason':reason,'actor_id':a.actor_id,'request_id':request_id,'effective_on':effective,'receipt_id':receipt,'reverse_of':reverse});return id

def entry(db,a,m,layer,loc,state,quantity):
    insert(db,a,'inv_entries',{'id':uuid4(),'movement_id':m,'layer_id':layer,'location_id':loc,'state':state,'quantity':quantity})
    args={'t':a.tenant_id,'l':layer,'p':loc,'s':state,'q':quantity}
    db.execute(text("INSERT INTO inv_balances VALUES (:t,:l,:p,:s,0) ON CONFLICT DO NOTHING"),args)
    db.execute(text("UPDATE inv_balances SET quantity=quantity+:q WHERE tenant_id=:t AND layer_id=:l AND location_id=:p AND state=:s"),args)

def create_layer(db,a,m,sku,quantity,tracking,serial,batch,location,state,cost,source_line=None,ownership='own',assembly_correction=None):
    unit=None
    if tracking=='sn':
        normal=normal_sn(serial)
        old=db.execute(text('SELECT * FROM inv_units WHERE sku_id=:s AND manufacturer_id=:m AND serial_normal=:n'),{'s':sku['id'],'m':sku['manufacturer_id'],'n':normal}).mappings().first()
        if old:
            unit=old['id']
            device=db.scalar(text('SELECT id FROM asm_devices WHERE inventory_unit_id=:u'),{'u':unit})
            if device and device!=assembly_correction:raise Denied(409,'ASSEMBLY_CORRECTION_REQUIRED')
            if db.scalar(text('SELECT 1 FROM asm_installations WHERE unit_id=:u AND removed_at IS NULL'),{'u':unit}):raise Denied(409,'COMPONENT_INSTALLED')
            if db.scalar(text('SELECT coalesce(sum(b.quantity),0) FROM inv_balances b JOIN inv_layers l ON l.id=b.layer_id AND l.tenant_id=b.tenant_id WHERE l.unit_id=:u'),{'u':unit}):raise Denied(409,'SERIAL_ALREADY_IN_STOCK')
        else:
            unit=uuid4();insert(db,a,'inv_units',{'id':unit,'sku_id':sku['id'],'manufacturer_id':sku['manufacturer_id'],'serial_raw':serial,'serial_normal':normal})
        if quantity!=1:raise Denied(422,'SERIAL_QUANTITY_ONE')
    id=uuid4();insert(db,a,'inv_layers',{'id':id,'unit_id':unit,'sku_id':sku['id'],'source_movement':m,'source_line':source_line,'quantity':quantity,'ownership':ownership,'currency':'CNY','tax_basis':cost['tax_basis'],'cost_status':cost['cost_status'],'unit_cost':cost['unit_cost'],'deductible_tax':cost['deductible_tax'],'cost_basis':cost['cost_basis']})
    if tracking!='sn':
        if not batch.strip():raise Denied(422,'BATCH_REQUIRED')
        insert(db,a,'inv_lots',{'id':uuid4(),'layer_id':id,'batch':batch})
    entry(db,a,m,id,location,state,quantity)
    return id

def receipt_post(db,a,id,b,request_id):
    r=receipt_detail(db,id);c.expected(r,b.expected_version)
    policy=db.execute(text('SELECT * FROM inv_opening_policy')).mappings().first()
    if policy and (policy['opened'] or r['received_on']<=policy['cutoff']):raise Denied(409,'OPENING_BOUNDARY')
    if not b.confirmed:raise Denied(422,'CONFIRM_REQUIRED')
    if r['state']!='draft':raise Denied(409,'RECEIPT_ALREADY_POSTED')
    m=movement(db,a,'receipt','采购收货',request_id,r['received_on'],receipt=id)
    for l in r['lines']:
        ol=row(db,'inv_order_lines',l['order_line_id']);cl=row(db,'inv_contract_lines',ol['contract_line_id']);sku=row(db,'catalog_skus',cl['sku_id']);tr=row(db,'inv_tracking',sku['id'])
        # Exclude this new movement from prior net receipts (not yet materialized layers).
        prior=db.scalar(text('''SELECT coalesce(sum(l.quantity),0) FROM inv_receipt_lines l JOIN inv_movements m ON m.receipt_id=l.receipt_id AND m.tenant_id=l.tenant_id WHERE l.order_line_id=:id AND m.id<>:m AND NOT EXISTS(SELECT 1 FROM inv_movements x WHERE x.reverse_of=m.id)'''),{'id':ol['id'],'m':m})
        if prior+cancelled(db,ol['id'])+l['quantity']>ol['quantity']:raise Denied(409,'RECEIPT_EXCEEDS_REMAINING')
        if not sku['enabled']:raise Denied(422,'SKU_DISABLED')
        l['tax_basis']=cl['tax_basis']
        if tr['mode']=='sn':
            if len(l['serials'])!=l['quantity'] or len({normal_sn(x) for x in l['serials']})!=l['quantity']:raise Denied(422,'SERIALS_REQUIRED_UNIQUE')
            for sn in l['serials']:create_layer(db,a,m,sku,1,'sn',sn,'',r['location_id'],'pending',l,l['id'])
        else:
            if l['serials']:raise Denied(422,'BATCH_HAS_NO_SERIALS')
            create_layer(db,a,m,sku,l['quantity'],'batch','',l['batch'],r['location_id'],'pending',l,l['id'])
    c.update(db,'inv_receipts',id,{'state':'posted','version':r['version']+1})
    return receipt_detail(db,id)

def transfer(db,a,b,request_id):
    l=row(db,'inv_layers',b.layer_id);c.expected(l,b.expected_version)
    if db.scalar(text('SELECT 1 FROM asm_works WHERE wip_location_id=:p OR wip_location_id=:s'),{'p':b.target_location_id,'s':b.source_location_id}):raise Denied(409,'ASSEMBLY_LOCATION_PROTECTED')
    if b.source_state!=b.target_state and db.scalar(text('SELECT 1 FROM asm_completions WHERE layer_id=:l'),{'l':b.layer_id}):raise Denied(409,'DEVICE_TESTING_NOT_ENABLED')
    row(db,'inv_locations',b.source_location_id);row(db,'inv_locations',b.target_location_id)
    if not b.confirmed:raise Denied(422,'CONFIRM_REQUIRED')
    if (b.source_location_id,b.source_state)==(b.target_location_id,b.target_state):raise Denied(422,'NO_MOVEMENT')
    inspection=b.source_state!=b.target_state
    a.require('inventory.inspect' if inspection else 'inventory.move')
    if inspection and (b.source_state!='pending' or b.target_state not in ('qualified','quarantine') or b.source_location_id!=b.target_location_id):raise Denied(422,'INSPECTION_TRANSITION_INVALID')
    quantity=db.scalar(text('SELECT quantity FROM inv_balances WHERE layer_id=:l AND location_id=:p AND state=:s'),{'l':b.layer_id,'p':b.source_location_id,'s':b.source_state}) or 0
    if quantity<b.quantity:raise Denied(409,'INSUFFICIENT_STOCK')
    from silicon.assembly.service import active
    if active(db,b.layer_id,b.source_location_id):raise Denied(409,'ACTIVE_RESERVATION')
    m=movement(db,a,'inspection' if inspection else 'transfer',b.reason,request_id,date.today())
    entry(db,a,m,b.layer_id,b.source_location_id,b.source_state,-b.quantity);entry(db,a,m,b.layer_id,b.target_location_id,b.target_state,b.quantity)
    c.update(db,'inv_layers',b.layer_id,{'version':l['version']+1})
    return movement_detail(db,m)

def movement_detail(db,id):
    m=row(db,'inv_movements',id);m['entries']=rows(db,'inv_entries','movement_id',id);return m

def reverse(db,a,id,b,request_id):
    m=movement_detail(db,id)
    if m['kind'].startswith('delivery_'):raise Denied(409,'USE_DELIVERY_CORRECTION')
    if m['kind'].startswith('assembly_'):raise Denied(409,'USE_ASSEMBLY_REVERSAL')
    if b.expected_version != 1:raise Denied(409,'VERSION_CONFLICT')
    if not b.confirmed or not b.reason.strip():raise Denied(422,'CONFIRM_REASON_REQUIRED')
    if m['kind']=='reverse' or db.scalar(text('SELECT 1 FROM inv_movements WHERE reverse_of=:id'),{'id':id}):raise Denied(409,'ALREADY_REVERSED')
    for e in m['entries']:
        from silicon.assembly.service import active
        if active(db,e['layer_id']):raise Denied(409,'ACTIVE_RESERVATION')
        # Every later unreversed movement involving the layer must be reversed first.
        later=db.scalar(text('''SELECT x.id FROM inv_movements x JOIN inv_entries e ON e.movement_id=x.id AND e.tenant_id=x.tenant_id WHERE e.layer_id=:l AND x.created_at>:at AND x.kind<>'reverse' AND NOT EXISTS(SELECT 1 FROM inv_movements r WHERE r.reverse_of=x.id) LIMIT 1'''),{'l':e['layer_id'],'at':m['created_at']})
        if later:raise Denied(409,'MOVEMENT_DEPENDENCY')
    rid=movement(db,a,'reverse',b.reason,request_id,date.today(),reverse=id)
    for e in m['entries']:
        entry(db,a,rid,e['layer_id'],e['location_id'],e['state'],-e['quantity'])
    for layer in {e['layer_id'] for e in m['entries']}:
        l=row(db,'inv_layers',layer);c.update(db,'inv_layers',layer,{'version':l['version']+1})
    return movement_detail(db,rid)

def stock(db,as_of=None):
    at=as_of or datetime.now(timezone.utc)
    items=[dict(x) for x in db.execute(text('''SELECT l.*,e.location_id,e.state,sum(e.quantity)::int AS balance,u.serial_raw,u.id AS unit_id,o.batch,p.warehouse,p.name AS location_name,s.number,s.name
      FROM inv_entries e JOIN inv_movements m ON m.id=e.movement_id AND m.tenant_id=e.tenant_id JOIN inv_layers l ON l.id=e.layer_id AND l.tenant_id=e.tenant_id
      JOIN inv_locations p ON p.id=e.location_id AND p.tenant_id=e.tenant_id JOIN catalog_skus s ON s.id=l.sku_id AND s.tenant_id=l.tenant_id
      LEFT JOIN inv_units u ON u.id=l.unit_id AND u.tenant_id=l.tenant_id LEFT JOIN inv_lots o ON o.layer_id=l.id AND o.tenant_id=l.tenant_id
      WHERE m.created_at<=:at AND m.effective_on<=CAST(:at AS date) GROUP BY l.tenant_id,l.id,e.location_id,e.state,u.serial_raw,u.id,o.batch,p.warehouse,p.name,s.number,s.name HAVING sum(e.quantity)<>0 ORDER BY l.created_at,l.id,e.location_id,e.state'''),{'at':at}).mappings()]
    known=Decimal(0);unknown=0;available=0
    for x in items:
        x['layer_id']=x.pop('id')
        x['stage']='wip' if x['state']=='wip' else ('finished' if db.scalar(text('SELECT 1 FROM asm_completions WHERE layer_id=:id'),{'id':x['layer_id']}) else 'material')
        if x['ownership']=='own':
            if x['unit_cost'] is None:unknown+=x['balance']
            else:known+=x['unit_cost']*x['balance']
            if x['state']=='qualified':
                from silicon.assembly.service import active
                x['reserved_quantity']=active(db,x['layer_id'],x['location_id']) if as_of is None else None
                available+=x['balance']-(x['reserved_quantity'] or 0)
    return {'items':items,'available_quantity':available,'unit':'piece','reservation_state':'current' if as_of is None else 'historical_reservations_not_projected','known_cost':format(known,'.2f'),'unknown_quantity':unknown,'cost_complete':unknown==0,'total_cost':format(known,'.2f') if not unknown else None,'as_of':at}
import csv,io
CSV_COLUMNS=['external_id','sku','location_id','state','ownership','quantity','serial','batch','unit_cost','cost_status','currency','opening_date','basis']

def opening_config(db,a,b):
    old=db.execute(text('SELECT * FROM inv_opening_policy')).mappings().first()
    if old:
        c.expected(old,b.expected_version)
        if old['cutoff']!=b.cutoff:raise Denied(409,'CUTOFF_FROZEN')
        # A reopen is explicit and audited, never permits imports after first receipt.
        if b.open and db.scalar(text("SELECT 1 FROM inv_movements WHERE kind='receipt' LIMIT 1")):raise Denied(409,'BUSINESS_ALREADY_POSTED')
        db.execute(text('UPDATE inv_opening_policy SET opened=:o,version=version+1,reason=:r'),{'o':b.open,'r':b.reason})
    else:
        if b.expected_version or b.cutoff>date.today():raise Denied(422,'OPENING_CUTOFF_INVALID')
        if db.scalar(text('SELECT 1 FROM inv_movements LIMIT 1')):raise Denied(409,'BUSINESS_ALREADY_POSTED')
        insert(db,a,'inv_opening_policy',{'cutoff':b.cutoff,'opened':b.open,'version':1,'reason':b.reason})
    return dict(db.execute(text('SELECT * FROM inv_opening_policy')).mappings().one())
def parse_csv(db,data):
    try:
        reader=csv.DictReader(io.StringIO(data));assert reader.fieldnames==CSV_COLUMNS
        lines=list(reader);assert 0<len(lines)<=1000
        assert all(None not in x and all(v is not None for v in x.values()) for x in lines)
    except Exception:raise Denied(422,'CSV_FORMAT_INVALID') from None
    errors=[];clean=[];seen=set();sn_seen=set()
    policy=db.execute(text('SELECT * FROM inv_opening_policy')).mappings().first()
    for n,x in enumerate(lines,2):
        try:
            if None in x or any(v is None for v in x.values()):raise ValueError()
            x={k:v.strip() for k,v in x.items()};external=x['external_id']
            if not external or len(external)>120 or external in seen:raise ValueError('EXTERNAL_ID_DUPLICATE')
            seen.add(external)
            sku=db.execute(text('SELECT * FROM catalog_skus WHERE number=:n'),{'n':x['sku']}).mappings().first()
            if not sku:raise ValueError('SKU_UNKNOWN')
            tracking=row(db,'inv_tracking',sku['id']);loc=row(db,'inv_locations',UUID(x['location_id']))
            quantity=int(x['quantity'])
            if quantity<=0 or quantity>1000000 or str(quantity)!=x['quantity']:raise ValueError('QUANTITY_INVALID')
            if x['state'] not in ('pending','qualified','quarantine') or x['ownership'] not in ('own','customer') or x['currency']!='CNY':raise ValueError('STATE_CURRENCY_INVALID')
            opening=date.fromisoformat(x['opening_date'])
            if not policy or opening!=policy['cutoff']:raise ValueError('CUTOFF_MISMATCH')
            cost=None if not x['unit_cost'] else Decimal(x['unit_cost'])
            if x['cost_status'] not in ('unknown','provisional','confirmed') or (x['cost_status']=='unknown')!=(cost is None):raise ValueError('COST_INVALID')
            if cost is not None and (not cost.is_finite() or cost<0 or cost.as_tuple().exponent<-2 or cost>=Decimal('1e16')):raise ValueError('COST_INVALID')
            if not x['basis']:raise ValueError('BASIS_REQUIRED')
            if tracking['mode']=='sn':
                if quantity!=1:raise ValueError('SERIAL_QUANTITY_ONE')
                sn=normal_sn(x['serial']);identity=(str(sku['id']),sn)
                if identity in sn_seen or db.scalar(text('SELECT 1 FROM inv_units WHERE sku_id=:s AND serial_normal=:n'),{'s':sku['id'],'n':sn}):raise ValueError('SERIAL_DUPLICATE')
                sn_seen.add(identity)
            elif not x['batch'] or x['serial']:raise ValueError('BATCH_REQUIRED')
            if db.scalar(text('SELECT 1 FROM inv_import_rows WHERE external_id=:x'),{'x':external}):raise ValueError('EXTERNAL_ID_POSTED')
            clean.append({**x,'sku_id':str(sku['id']),'quantity':quantity,'unit_cost':str(cost) if cost is not None else None,'tracking':tracking['mode']})
        except (ValueError,Denied,ArithmeticError) as ex:errors.append({'row':n,'code':str(ex) if isinstance(ex,ValueError) and str(ex) else 'ROW_INVALID'})
    # Hash canonical raw rows, before validation; changing row order cannot bypass replay.
    canonical=sorted([{k:(v.strip() if isinstance(v,str) else v) for k,v in x.items()} for x in lines],key=lambda x:str(x.get('external_id','')))
    digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'valid':not errors,'rows':clean,'errors':errors,'content_hash':digest}

def preview_import(db,a,b,store):
    v=parse_csv(db,b.csv)
    old=db.execute(text('SELECT * FROM inv_imports WHERE content_hash=:h'),{'h':v['content_hash']}).mappings().first()
    if old and old['state']=='posted':return {**dict(old),'valid':old['validation']['valid'],'errors':old['validation']['errors']}
    policy=db.execute(text('SELECT * FROM inv_opening_policy')).mappings().first()
    if not policy or not policy['opened']:raise Denied(409,'OPENING_CLOSED')
    if old:return {**dict(old),'valid':old['validation']['valid'],'errors':old['validation']['errors']}
    metadata=store.put_validated('opening.csv',b.csv.encode(),'text/csv')
    try:
        id=uuid4();db.execute(text("INSERT INTO inv_imports(tenant_id,id,content_hash,storage_id,name,media_type,size,sha256,validation,state,version,actor_id) VALUES (:t,:id,:h,:storage_id,:name,:media_type,:size,:sha256,CAST(:v AS jsonb),'preview',1,:a)"),{'t':a.tenant_id,'id':id,'h':v['content_hash'],'v':json.dumps(v),'a':a.actor_id,**metadata})
    finally:store.release()
    return {'id':id,'version':1,'state':'preview',**v}
def commit_import(db,a,id,b,request_id,store):
    old=row(db,'inv_imports',id)
    # Semantic replay across new command keys, independent of mutable policy/SN checks.
    if old['state']=='posted':return {'id':id,'movement_id':old['movement_id'],'state':'posted'}
    c.expected(old,b.expected_version)
    if not b.confirmed:raise Denied(422,'CONFIRM_REQUIRED')
    policy=db.execute(text('SELECT * FROM inv_opening_policy')).mappings().first()
    if not policy or not policy['opened']:raise Denied(409,'OPENING_CLOSED')
    v=parse_csv(db,store.read(old).decode())
    if not v['valid']:raise Denied(422,'IMPORT_ROWS_INVALID')
    m=movement(db,a,'opening','期初原子导入',request_id,policy['cutoff'])
    for x in v['rows']:
        sku=row(db,'catalog_skus',x['sku_id'])
        cost={'cost_status':x['cost_status'],'unit_cost':Decimal(x['unit_cost']) if x['unit_cost'] is not None else None,'deductible_tax':None,'cost_basis':x['basis'],'tax_basis':'unconfirmed'}
        layer=create_layer(db,a,m,sku,x['quantity'],x['tracking'],x['serial'],x['batch'],x['location_id'],x['state'],cost,ownership=x['ownership'])
        insert(db,a,'inv_import_rows',{'id':uuid4(),'import_id':id,'external_id':x['external_id'],'layer_id':layer})
    db.execute(text("UPDATE inv_imports SET state='posted',version=version+1,movement_id=:m WHERE id=:id"),{'id':id,'m':m})
    return {'id':id,'movement_id':m,'state':'posted'}

def cancel_order(db,a,id,b):
    order=row(db,'inv_orders',id);c.expected(order,b.expected_version)
    line=row(db,'inv_order_lines',b.line_id)
    if line['order_id']!=id:raise Denied(404,'NOT_FOUND')
    if not b.confirmed:raise Denied(422,'CONFIRM_REQUIRED')
    if cancelled(db,line['id'])+net_received(db,line['id'])+b.quantity>line['quantity']:raise Denied(409,'CANCEL_EXCEEDS_REMAINING')
    insert(db,a,'inv_cancellations',{'id':uuid4(),'line_id':line['id'],'quantity':b.quantity,'reason':b.reason,'actor_id':a.actor_id})
    c.update(db,'inv_orders',id,{'version':order['version']+1});return order_detail(db,id)
def amend(db,a,id,b):
    contract=contract_detail(db,id);c.expected(contract,b.expected_version)
    if contract['state']!='active' or not b.confirmed:raise Denied(409,'ACTIVE_CONFIRM_REQUIRED')
    line=row(db,'inv_contract_lines',b.line_id)
    if line['contract_id']!=id:raise Denied(404,'NOT_FOUND')
    aid=uuid4();insert(db,a,'inv_amendments',{'id':aid,'contract_id':id,'line_id':b.line_id,'extra_quantity':b.extra_quantity,'reason':b.reason,'actor_id':a.actor_id})
    return row(db,'inv_amendments',aid)

def reconciliation(db,as_of=None):
    # Compare current quantity projection with all immutable entries, never with a
    # historical balance. Cost projection is balance * the immutable layer cost.
    values=[dict(x) for x in db.execute(text('''WITH ledger AS(SELECT tenant_id,layer_id,location_id,state,sum(quantity)::int quantity FROM inv_entries GROUP BY tenant_id,layer_id,location_id,state), compared AS(
      SELECT coalesce(l.tenant_id,b.tenant_id) tenant_id,coalesce(l.layer_id,b.layer_id) layer_id,coalesce(l.location_id,b.location_id) location_id,coalesce(l.state,b.state) state,coalesce(l.quantity,0) ledger_quantity,coalesce(b.quantity,0) projected_quantity
      FROM ledger l FULL JOIN inv_balances b USING(tenant_id,layer_id,location_id,state))
      SELECT c.*,v.unit_cost,v.ownership FROM compared c JOIN inv_layers v ON v.tenant_id=c.tenant_id AND v.id=c.layer_id''')).mappings()]
    ledger_cost=Decimal(0);projected_cost=Decimal(0);ledger_unknown=0;projected_unknown=0;differences=[]
    for x in values:
        unit=x.pop('unit_cost');own=x.pop('ownership')=='own';x.pop('tenant_id')
        x['ledger_cost']=format(unit*x['ledger_quantity'],'.2f') if own and unit is not None else None
        x['projected_cost']=format(unit*x['projected_quantity'],'.2f') if own and unit is not None else None
        if own:
            if unit is None:ledger_unknown+=x['ledger_quantity'];projected_unknown+=x['projected_quantity']
            else:ledger_cost+=unit*x['ledger_quantity'];projected_cost+=unit*x['projected_quantity']
        if x['ledger_quantity']!=x['projected_quantity']:differences.append(x)
    return {'stock':stock(db,as_of),'projection_matches':not differences,'differences':differences,'projection_as_of':'current',
            'cost_projection':{'ledger_known_cost':format(ledger_cost,'.2f'),'projected_known_cost':format(projected_cost,'.2f'),'ledger_unknown_quantity':ledger_unknown,'projected_unknown_quantity':projected_unknown,'complete':ledger_unknown==projected_unknown==0},
            'historical_stock_from':'immutable ledger; as_of recorded time and effective date'}

def summary(db,a):
    stock_value=stock(db);pending=sum(x['balance'] for x in stock_value['items'] if x['state']=='pending');quarantine=sum(x['balance'] for x in stock_value['items'] if x['state']=='quarantine')
    remaining=sum(x['quantity']-x['received']-x['cancelled'] for o in rows(db,'inv_orders') for x in order_detail(db,o['id'])['lines'])
    result={'pending_quantity':pending,'quarantine_quantity':quarantine,'remaining_quantity':remaining,'unit':'piece','payment_state':'not_implemented'}
    if 'inventory.cost' in a.permissions:
        amounts=[]
        for basis in ['included','excluded','unconfirmed']:
            purchase=Decimal(0);received=Decimal(0)
            for co in rows(db,'inv_contracts'):
                if co['state']!='active':continue
                for l in rows(db,'inv_contract_lines','contract_id',co['id']):
                    if l['tax_basis']!=basis:continue
                    extra=db.scalar(text('SELECT coalesce(sum(extra_quantity),0) FROM inv_amendments WHERE line_id=:id'),{'id':l['id']})
                    purchase+=(l['quantity']+extra)*l['unit_price']
            for o in rows(db,'inv_orders'):
                for l in order_detail(db,o['id'])['lines']:
                    if l['tax_basis']==basis:received+=l['received']*l['unit_price']
            amounts.append({'tax_basis':basis,'currency':'CNY','purchase_amount':format(purchase,'.2f'),'received_amount':format(received,'.2f')})
        result['amounts']=amounts
    return result
