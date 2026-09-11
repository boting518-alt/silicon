"""Append-only operating finance facts. ADR-016 defines the shared lock order.
No bank actions, inventory valuation, or statutory revenue recognition occur here.
"""
import hashlib,json
from datetime import datetime,timezone
from decimal import Decimal
from uuid import uuid4,UUID
from zoneinfo import ZoneInfo
from sqlalchemy import text
from silicon.identity.access import Denied,audit
from silicon.catalog import service as cat
from silicon.quotes import service as quotes
from silicon.inventory import service as inv

D=Decimal
money=lambda n:format(D(n),'.2f')
row=inv.row
rows=inv.rows
insert=inv.insert

def guard(db,a,write):
    quotes.guard(db,a,False)
    # CRM owns these rows; acquire them before inventory to match quote/CRM order.
    db.execute(text('SELECT id FROM crm_customers ORDER BY id FOR SHARE')).all()
    inv.guard(db,a,False)
    fn='pg_advisory_xact_lock' if write else 'pg_advisory_xact_lock_shared'
    db.execute(text(f'SELECT {fn}(hashtextextended(:k,0))'),{'k':'finance:'+str(a.tenant_id)})

def command(db,a,op,key,body,request_id,perform):
    if not key or len(key)>128:raise Denied(422,'IDEMPOTENCY_KEY_REQUIRED')
    digest=hashlib.sha256(json.dumps(inv.serial(body),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    args={'t':a.tenant_id,'u':a.actor_id,'o':op,'k':key}
    old=db.execute(text('SELECT * FROM fin_commands WHERE tenant_id=:t AND actor_id=:u AND operation=:o AND key=:k'),args).mappings().first()
    if old:
        if old['request_hash']!=digest:raise Denied(409,'IDEMPOTENCY_CONFLICT')
        return old['response']
    result=inv.serial(perform())
    db.execute(text('INSERT INTO fin_commands VALUES (:t,:u,:o,:k,:h,CAST(:r AS jsonb))'),{**args,'h':digest,'r':json.dumps(result)})
    audit(db,a.actor_id,a.tenant_id,op,result.get('id',op) if isinstance(result,dict) else op,'allowed',request_id)
    return result

def party(db,a,direction,id):
    p=row(db,'crm_customers' if direction=='receivable' else 'inv_suppliers',id)
    if direction=='receivable':visible=a.owns(p['owner_id'])
    else:visible=a.data_scope=='all' or any(a.owns(x['manager_id']) for x in rows(db,'inv_contracts','supplier_id',id))
    if not visible:raise Denied(404,'NOT_FOUND')
    return p

def source(db,a,direction,id):
    if direction=='receivable':
        co=row(db,'signed_contracts',id);content=co['content'];party_id=UUID(content['commercial']['config']['customer_id'])
        orders=rows(db,'sales_orders','contract_version_id',id)
        base=D(content['commercial']['calculation']['total']);nodes=content['payments'];basis='frozen sales commercial total; tax policy unchanged'
        version=co['version']
    else:
        co=row(db,'inv_contracts',id)
        if co['state']!='active':raise Denied(409,'FIN_SOURCE_INACTIVE')
        if not a.owns(co['manager_id']):raise Denied(404,'NOT_FOUND')
        party_id=co['supplier_id'];lines=rows(db,'inv_contract_lines','contract_id',id);amend=rows(db,'inv_amendments','contract_id',id)
        base=sum((l['unit_price']*(l['quantity']+sum(x['extra_quantity'] for x in amend if x['line_id']==l['id'])) for l in lines),D(0))
        orders=[x for x in rows(db,'inv_orders','contract_id',id) if x['state']=='confirmed'];nodes=[];basis=', '.join(sorted({l['tax_basis'] for l in lines}));version=co['version']+len(amend)
    p=party(db,a,direction,party_id)
    adj=[x for x in rows(db,'fin_source_adjustments','source_id',id) if x['direction']==direction]
    return {'id':id,'direction':direction,'party_id':party_id,'party_name':p['name'],'number':co['number'],'amount':money(base+sum((x['amount'] for x in adj),D(0))),
            'base_amount':money(base),'version':version+len(adj),'order_ids':[x['id'] for x in orders],'nodes':nodes,'tax_basis':basis}

def sources(db,a):
    result=[]
    for direction,table in [('receivable','signed_contracts'),('payable','inv_contracts')]:
        for x in rows(db,table):
            try:result.append(source(db,a,direction,x['id']))
            except Denied as e:
                if e.code not in ('NOT_FOUND','FIN_SOURCE_INACTIVE'):raise
    return result

def party_fields(direction,id):return {'customer_id' if direction=='receivable' else 'supplier_id':id}
def source_fields(direction,id):return {'sales_contract_id' if direction=='receivable' else 'purchase_contract_id':id}
def reversed_fact(db,kind,id):return bool(db.scalar(text(f'SELECT 1 FROM fin_reversals WHERE {kind}_id=:id'),{'id':id}))
def allocations(db,parent,id):return [{**x,'amount':money(x['amount']),'reversed':reversed_fact(db,'allocation',x['id'])} for x in rows(db,'fin_allocations',parent,id)]
def total(values):return sum((D(x['amount']) for x in values),D(0))
def bump(db,table,v):cat.update(db,table,v['id'],{'version':v['version']+1})
def confirmable(v,b):
    cat.expected(v,b.expected_version)
    if v['state']!='draft':raise Denied(409,'FIN_NOT_DRAFT')
def now():return datetime.now(timezone.utc)
def occurred(at):
    if at>now():raise Denied(422,'FIN_FUTURE_FACT')

def plan(db,a,id):
    v=row(db,'fin_plans',id);s=source(db,a,v['direction'],v['source_id'])
    adjustments=rows(db,'fin_adjustments','plan_id',id);releases=rows(db,'fin_releases','plan_id',id);alloc=allocations(db,'plan_id',id)
    originals={x['id']:x for x in adjustments}
    corrections=[{**x,'amount':money(-originals[x['adjustment_id']]['amount'])} for x in rows(db,'fin_adjustment_corrections','plan_id',id)]
    adj=total(adjustments)+total(corrections);effective=v['amount']+adj if v['state']=='confirmed' else D(0);used=total(x for x in alloc if not x['reversed'])
    released=bool(releases) or (not v['retention'] and not v['release_condition'] and v['due_date'] is not None)
    due=releases[0]['due_date'] if releases else v['due_date'] if released else None
    return {**v,'party_name':s['party_name'],'amount':money(v['amount']),'effective':money(effective),'adjustment':money(adj),'allocated':money(used),'remaining':money(effective-used),
            'due_date':due,'released':released,'overdue':bool(due and due<now().astimezone(ZoneInfo('Asia/Shanghai')).date() and effective>used),
            'adjustments':[{**x,'amount':money(x['amount'])} for x in adjustments],'corrections':corrections,'releases':releases,'allocations':alloc}

def cash(db,a,id):
    v=row(db,'fin_cash',id);p=party(db,a,v['direction'],v['party_id']);alloc=allocations(db,'cash_id',id)
    for l in alloc:plan(db,a,l['plan_id']) # Recheck visibility of all response relationships, including historical ones.
    used=total(x for x in alloc if not x['reversed']);refund=total(x for x in rows(db,'fin_refunds','cash_id',id) if x['state']=='confirmed' and not reversed_fact(db,'refund',x['id']))
    rev=reversed_fact(db,'cash',id);effective=v['amount'] if v['state']=='confirmed' and not rev else D(0)
    return {**v,'party_name':p['name'],'amount':money(v['amount']),'allocated':money(used),'refunded':money(refund),'available':money(effective-used-refund),'reversed':rev,'allocations':alloc}

def refund(db,a,id):
    v=row(db,'fin_refunds',id);cash(db,a,v['cash_id'])
    return {**v,'amount':money(v['amount']),'reversed':reversed_fact(db,'refund',id)}

def invoice(db,a,id):
    v=row(db,'fin_invoices',id);party(db,a,v['direction'],v['party_id']);lines=rows(db,'fin_invoice_lines','invoice_id',id)
    for l in lines:source(db,a,v['direction'],l['source_id'])
    return {**v,'amount':money(v['amount']),'net_amount':money(v['net_amount']) if v['net_amount'] is not None else None,'tax_amount':money(v['tax_amount']) if v['tax_amount'] is not None else None,
            'tax_state':'manually_registered' if v['tax_amount'] is not None else 'unconfirmed','reversed':reversed_fact(db,'invoice',id),'lines':[{**l,'amount':money(l['amount'])} for l in lines]}

def listing(db,a,kind):
    table,fn={'plans':('fin_plans',plan),'cash':('fin_cash',cash),'refunds':('fin_refunds',refund),'invoices':('fin_invoices',invoice)}[kind];result=[]
    for x in rows(db,table):
        try:result.append(fn(db,a,x['id']))
        except Denied as e:
            if e.code!='NOT_FOUND':raise
    return result

def occupied(db,id):
    # Negative reductions never free the original contract allowance for duplicate plans.
    return db.scalar(text("SELECT coalesce(sum(amount),0) FROM fin_plans WHERE source_id=:id AND state='confirmed'"),{'id':id})+db.scalar(text('SELECT coalesce(sum(greatest(a.amount,0)),0) FROM fin_adjustments a JOIN fin_plans p ON p.id=a.plan_id AND p.tenant_id=a.tenant_id WHERE p.source_id=:id'),{'id':id})

def create_plan(db,a,b):
    s=source(db,a,b.direction,b.source_id)
    if b.order_id and b.order_id not in s['order_ids']:raise Denied(404,'NOT_FOUND')
    if b.due_date is None and not b.release_condition.strip():raise Denied(422,'FIN_DUE_OR_CONDITION_REQUIRED')
    if b.retention and not (b.due_date or b.release_condition.strip()):raise Denied(422,'FIN_RELEASE_CONDITION_REQUIRED')
    values=b.model_dump(exclude={'source_id','order_id'})
    id=uuid4();insert(db,a,'fin_plans',{'id':id,**values,**party_fields(b.direction,s['party_id']),**source_fields(b.direction,b.source_id),
            'order_id' if b.direction=='receivable' else 'purchase_order_id':b.order_id})
    return plan(db,a,id)

def import_plans(db,a,b):
    from .models import PlanInput
    s=source(db,a,'receivable',b.source_id);result=[]
    for n in s['nodes']:
        body=PlanInput(direction='receivable',source_id=b.source_id,node='contract-node:'+n['id'],amount=n['amount'],due_date=n.get('resolved_due_date'),release_condition='' if n.get('resolved_due_date') else n['trigger'],notes=n['name'])
        result.append(create_plan(db,a,body))
    if not result:raise Denied(422,'FIN_NO_FROZEN_NODES')
    return result

def confirm_plan(db,a,id,b):
    v=plan(db,a,id);confirmable(v,b);s=source(db,a,v['direction'],v['source_id'])
    if occupied(db,v['source_id'])+D(v['amount'])>D(s['amount']):raise Denied(409,'FIN_SOURCE_CAP_EXCEEDED')
    cat.update(db,'fin_plans',id,{'state':'confirmed','version':v['version']+1});return plan(db,a,id)

def create_cash(db,a,b):
    party(db,a,b.direction,b.party_id);occurred(b.occurred_at)
    id=uuid4();insert(db,a,'fin_cash',{'id':id,**b.model_dump(exclude={'party_id'}),**party_fields(b.direction,b.party_id),'actor_id':a.actor_id});return cash(db,a,id)

def confirm_cash(db,a,id,b):
    v=cash(db,a,id);confirmable(v,b);occurred(v['occurred_at'])
    cat.update(db,'fin_cash',id,{'state':'confirmed','version':v['version']+1});return cash(db,a,id)

def allocate(db,a,id,b):
    v=cash(db,a,id);cat.expected(v,b.expected_version)
    if v['state']!='confirmed' or v['reversed']:raise Denied(409,'FIN_CASH_INACTIVE')
    if len({x.plan_id for x in b.lines})!=len(b.lines):raise Denied(422,'FIN_DUPLICATE_TARGET')
    if sum((x.amount for x in b.lines),D(0))>D(v['available']):raise Denied(409,'FIN_AVAILABLE_EXCEEDED')
    checked=[]
    for l in b.lines:
        p=plan(db,a,l.plan_id);cat.expected(p,l.expected_version)
        if (p['direction'],p['party_id'])!=(v['direction'],v['party_id']):raise Denied(422,'FIN_PARTY_DIRECTION_MISMATCH')
        if p['state']!='confirmed' or not p['released']:raise Denied(409,'FIN_PLAN_NOT_SETTLEABLE')
        if l.amount>D(p['remaining']):raise Denied(409,'FIN_REMAINING_EXCEEDED')
        checked.append((l,p))
    for l,p in checked:
        insert(db,a,'fin_allocations',{'id':uuid4(),'cash_id':id,'plan_id':l.plan_id,'direction':v['direction'],'party_id':v['party_id'],'amount':l.amount,'actor_id':a.actor_id});bump(db,'fin_plans',p)
    bump(db,'fin_cash',v);return cash(db,a,id)

def reverse_allocation(db,a,id,b):
    l=row(db,'fin_allocations',id);v=cash(db,a,l['cash_id']);p=plan(db,a,l['plan_id']);cat.expected(v,b.expected_version)
    if reversed_fact(db,'allocation',id):raise Denied(409,'FIN_ALREADY_REVERSED')
    insert(db,a,'fin_reversals',{'id':uuid4(),'allocation_id':id,'reason':b.reason,'actor_id':a.actor_id});bump(db,'fin_cash',v);bump(db,'fin_plans',p);return cash(db,a,v['id'])

def adjust(db,a,id,b):
    v=plan(db,a,id);cat.expected(v,b.expected_version)
    if v['state']!='confirmed' or not b.amount:raise Denied(422,'FIN_ADJUSTMENT_INVALID')
    if D(v['effective'])+b.amount<D(v['allocated']):raise Denied(409,'FIN_DEALLOCATE_FIRST')
    if b.amount>0 and occupied(db,v['source_id'])+b.amount>D(source(db,a,v['direction'],v['source_id'])['amount']):raise Denied(409,'FIN_SOURCE_CAP_EXCEEDED')
    if b.return_id:
        r=row(db,'del_returns',b.return_id);l=row(db,'del_lines',r['line_id']);o=row(db,'sales_orders',l['order_id'])
        if b.amount>=0 or v['direction']!='receivable' or o['contract_version_id']!=v['source_id']:raise Denied(422,'FIN_RETURN_SOURCE_MISMATCH')
    insert(db,a,'fin_adjustments',{'id':uuid4(),'plan_id':id,'amount':b.amount,'reason':b.reason,'basis_ref':b.basis_ref,'return_id':b.return_id,'actor_id':a.actor_id});bump(db,'fin_plans',v);return plan(db,a,id)

def correction_original(db,a,id,adjustment_id):
    plan(db,a,id)
    original=row(db,'fin_adjustments',adjustment_id)
    if original['plan_id']!=id:raise Denied(404,'NOT_FOUND')
    return original

def correct_adjustment(db,a,id,b):
    v=plan(db,a,id);cat.expected(v,b.expected_version)
    original=correction_original(db,a,id,b.adjustment_id)
    if v['state']!='confirmed' or original['amount']>=0:raise Denied(422,'FIN_CORRECTION_REQUIRES_REDUCTION')
    if rows(db,'fin_adjustment_corrections','adjustment_id',b.adjustment_id):raise Denied(409,'FIN_ADJUSTMENT_ALREADY_CORRECTED')
    effective=D(v['effective'])-original['amount']
    if effective<max(D(0),D(v['allocated'])):raise Denied(409,'FIN_DEALLOCATE_FIRST')
    # The original negative amount never freed allowance. Restoring it consumes no new allowance.
    insert(db,a,'fin_adjustment_corrections',{'id':uuid4(),'plan_id':id,'adjustment_id':b.adjustment_id,'reason':b.reason,'basis_ref':b.basis_ref,'actor_id':a.actor_id})
    bump(db,'fin_plans',v);return plan(db,a,id)

def release(db,a,id,b):
    v=plan(db,a,id);cat.expected(v,b.expected_version)
    if v['state']!='confirmed' or v['released']:raise Denied(409,'FIN_RELEASE_NOT_REQUIRED')
    insert(db,a,'fin_releases',{'id':uuid4(),'plan_id':id,'due_date':b.due_date,'reason':b.reason,'actor_id':a.actor_id});bump(db,'fin_plans',v);return plan(db,a,id)

def create_refund(db,a,b):
    v=cash(db,a,b.cash_id);occurred(b.occurred_at)
    if v['state']!='confirmed' or v['reversed']:raise Denied(409,'FIN_CASH_INACTIVE')
    id=uuid4();insert(db,a,'fin_refunds',{'id':id,**b.model_dump(),'actor_id':a.actor_id});return refund(db,a,id)

def confirm_refund(db,a,id,b):
    v=refund(db,a,id);confirmable(v,b);c=cash(db,a,v['cash_id']);cat.expected(c,b.cash_version)
    if c['state']!='confirmed' or c['reversed']:raise Denied(409,'FIN_CASH_INACTIVE')
    if D(v['amount'])>D(c['available']):raise Denied(409,'FIN_REFUND_EXCEEDED')
    occurred(v['occurred_at']);cat.update(db,'fin_refunds',id,{'state':'confirmed','version':v['version']+1});bump(db,'fin_cash',c);return refund(db,a,id)

def reverse_cash(db,a,id,b):
    v=cash(db,a,id);cat.expected(v,b.expected_version)
    if v['state']!='confirmed' or v['reversed']:raise Denied(409,'FIN_CASH_INACTIVE')
    if D(v['allocated']) or D(v['refunded']):raise Denied(409,'FIN_DOWNSTREAM_DEPENDENCY')
    insert(db,a,'fin_reversals',{'id':uuid4(),'cash_id':id,'reason':b.reason,'actor_id':a.actor_id});bump(db,'fin_cash',v);return cash(db,a,id)

def reverse_refund(db,a,id,b):
    v=refund(db,a,id);cat.expected(v,b.expected_version);c=cash(db,a,v['cash_id'])
    if v['state']!='confirmed' or v['reversed']:raise Denied(409,'FIN_REFUND_INACTIVE')
    insert(db,a,'fin_reversals',{'id':uuid4(),'refund_id':id,'reason':b.reason,'actor_id':a.actor_id});bump(db,'fin_refunds',v);bump(db,'fin_cash',c);return refund(db,a,id)

def cancel(db,a,kind,id,b):
    table,fn={'plans':('fin_plans',plan),'cash':('fin_cash',cash),'refunds':('fin_refunds',refund),'invoices':('fin_invoices',invoice)}[kind]
    v=fn(db,a,id);confirmable(v,b);cat.update(db,table,id,{'state':'cancelled','version':v['version']+1});return fn(db,a,id)

def source_adjustment(db,a,b):
    s=source(db,a,b.direction,b.source_id);cat.expected(s,b.expected_version)
    if not b.amount or D(s['amount'])+b.amount<max(occupied(db,b.source_id),invoiced(db,b.direction,b.source_id)):raise Denied(409,'FIN_SOURCE_CAP_BELOW_FACTS')
    insert(db,a,'fin_source_adjustments',{'id':uuid4(),'direction':b.direction,**source_fields(b.direction,b.source_id),'amount':b.amount,'basis_ref':b.basis_ref,'reason':b.reason,'actor_id':a.actor_id})
    return source(db,a,b.direction,b.source_id)

def invoiced(db,direction,id,original=None):
    result=D(0)
    for l in rows(db,'fin_invoice_lines','source_id',id):
        v=row(db,'fin_invoices',l['invoice_id'])
        if v['direction']!=direction or v['state']!='confirmed' or reversed_fact(db,'invoice',v['id']):continue
        if original:
            if v['original_id']==original:result+=l['amount']
        else:result+=l['amount']*(-1 if v['original_id'] else 1)
    return result

def create_invoice(db,a,b):
    party(db,a,b.direction,b.party_id)
    if b.issued_on>now().astimezone(ZoneInfo('Asia/Shanghai')).date():raise Denied(422,'FIN_FUTURE_FACT')
    if len({x.source_id for x in b.lines})!=len(b.lines) or sum((x.amount for x in b.lines),D(0))!=b.amount:raise Denied(422,'FIN_INVOICE_LINES_INVALID')
    if (b.net_amount is None)!=(b.tax_amount is None) or (b.net_amount is not None and b.net_amount+b.tax_amount!=b.amount):raise Denied(422,'FIN_TAX_SUM_INVALID')
    for l in b.lines:
        s=source(db,a,b.direction,l.source_id)
        if s['party_id']!=b.party_id:raise Denied(422,'FIN_PARTY_DIRECTION_MISMATCH')
    if b.original_id:
        original=invoice(db,a,b.original_id)
        if original['party_id']!=b.party_id or original['direction']!=b.direction or original['original_id']:raise Denied(422,'FIN_INVOICE_ORIGINAL_INVALID')
    id=uuid4();insert(db,a,'fin_invoices',{'id':id,**b.model_dump(exclude={'party_id','lines'}),**party_fields(b.direction,b.party_id)})
    for l in b.lines:insert(db,a,'fin_invoice_lines',{'id':uuid4(),'invoice_id':id,'direction':b.direction,**source_fields(b.direction,l.source_id),'amount':l.amount})
    return invoice(db,a,id)

def confirm_invoice(db,a,id,b):
    v=invoice(db,a,id);confirmable(v,b)
    original=invoice(db,a,v['original_id']) if v['original_id'] else None
    if original and (original['state']!='confirmed' or original['reversed']):raise Denied(409,'FIN_INVOICE_ORIGINAL_INACTIVE')
    for l in v['lines']:
        s=source(db,a,v['direction'],l['source_id'])
        if original:
            allowed=sum((D(x['amount']) for x in original['lines'] if x['source_id']==l['source_id']),D(0))-invoiced(db,v['direction'],l['source_id'],original['id'])
        else:allowed=D(s['amount'])-invoiced(db,v['direction'],l['source_id'])
        if D(l['amount'])>allowed:raise Denied(409,'FIN_INVOICE_CAP_EXCEEDED')
    cat.update(db,'fin_invoices',id,{'state':'confirmed','version':v['version']+1});return invoice(db,a,id)

def reverse_invoice(db,a,id,b):
    v=invoice(db,a,id);cat.expected(v,b.expected_version)
    if v['state']!='confirmed' or v['reversed']:raise Denied(409,'FIN_INVOICE_INACTIVE')
    if any(x['state']=='confirmed' and not reversed_fact(db,'invoice',x['id']) for x in rows(db,'fin_invoices','original_id',id)):raise Denied(409,'FIN_DOWNSTREAM_DEPENDENCY')
    if v['original_id']:
        for l in v['lines']:
            if invoiced(db,v['direction'],l['source_id'])+D(l['amount'])>D(source(db,a,v['direction'],l['source_id'])['amount']):raise Denied(409,'FIN_INVOICE_CAP_EXCEEDED')
    insert(db,a,'fin_reversals',{'id':uuid4(),'invoice_id':id,'reason':b.reason,'actor_id':a.actor_id});bump(db,'fin_invoices',v);return invoice(db,a,id)

def summary(db,a):
    plans=listing(db,a,'plans');funds=listing(db,a,'cash');refunds=listing(db,a,'refunds');out={}
    for direction,side,verb in [('receivable','receivable','received'),('payable','payable','paid')]:
        selected=[x for x in funds if x['direction']==direction and x['state']=='confirmed' and not x['reversed']]
        out[side]=money(sum((D(x['remaining']) for x in plans if x['direction']==direction),D(0)))
        out['overdue_'+side]=money(sum((D(x['remaining']) for x in plans if x['direction']==direction and x['overdue']),D(0)))
        out[verb]=money(total(selected));out['advance_'+verb]=money(sum((D(x['available']) for x in selected if x['purpose']=='advance'),D(0)))
        out['unallocated_'+verb]=money(sum((D(x['available']) for x in selected if x['purpose']=='unallocated'),D(0)))
        ids={x['id'] for x in selected};out['customer_refunds' if direction=='receivable' else 'supplier_refunds']=money(total(x for x in refunds if x['cash_id'] in ids and x['state']=='confirmed' and not x['reversed']))
    out['net_cash_flow']=money(D(out['received'])-D(out['paid'])-D(out['customer_refunds'])+D(out['supplier_refunds']));out['as_of']=now();return out

def source_summary(db,a,direction,id):
    return {'source':source(db,a,direction,id),'plans':[x for x in listing(db,a,'plans') if x['direction']==direction and x['source_id']==id],'invoiced':money(invoiced(db,direction,id))}

def reconciliation(db,a):
    differences=[]
    for p in listing(db,a,'plans'):
        if D(p['effective'])!= (D(p['amount'])+D(p['adjustment']) if p['state']=='confirmed' else 0) or D(p['remaining'])!=D(p['effective'])-D(p['allocated']) or D(p['remaining'])<0:differences.append('plan:'+str(p['id']))
    for c in listing(db,a,'cash'):
        expected=D(c['amount']) if c['state']=='confirmed' and not c['reversed'] else D(0)
        if expected!=D(c['allocated'])+D(c['refunded'])+D(c['available']) or D(c['available'])<0:differences.append('cash:'+str(c['id']))
    for v in listing(db,a,'invoices'):
        if total(v['lines'])!=D(v['amount']):differences.append('invoice:'+str(v['id']))
    return {'matches':not differences,'differences':differences,'summary':summary(db,a)}
