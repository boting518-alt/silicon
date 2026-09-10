"""Quote authority: session -> catalog shared -> quote guard -> customer share.

No CRM writer takes catalog/quote guards, and quote paths acquire no further
membership locks after the customer lock. Operator discount changes must take
quote exclusive guard. No reservation/redemption exists in this task.
"""
from datetime import datetime,timezone
from decimal import Decimal,ROUND_HALF_UP
import hashlib,json
from uuid import uuid4
from sqlalchemy import text
from silicon.catalog import service as catalog
from silicon.catalog.models import TechnicalLine,Check
from silicon.crm import service as crm
from silicon.identity.access import Denied,audit
from .models import QuoteInput,QuoteDetail,Calculation,PricedLine,DiscountRef

CENT=Decimal('.01');LIMIT=Decimal('9999999999999999.99')
def money(value):
    value=value.quantize(CENT,rounding=ROUND_HALF_UP)
    if value<0 or value>LIMIT:raise Denied(422,'AMOUNT_OUT_OF_RANGE')
    return value

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def code_hash(tenant,code):return hashlib.sha256((str(tenant)+':'+code.strip().upper()).encode()).hexdigest()

def guard(db,access,write=False):
    catalog.guard(db,access,False)
    fn='pg_advisory_xact_lock' if write else 'pg_advisory_xact_lock_shared'
    db.execute(text(f'SELECT {fn}(hashtextextended(:key,0))'),{'key':'quotes:'+str(access.tenant_id)})

def customer(db,access,body):
    access.require('crm.read')
    result=crm.detail(db,access,body.customer_id)
    if body.project_id not in {p.id for p in result.projects}:raise Denied(422,'INVALID_PROJECT')
    return result

def resolve_discount(db,access,code):
    access.require('quote.discount')
    row=db.execute(text('SELECT * FROM quote_discounts WHERE code_hash=:hash'),{'hash':code_hash(access.tenant_id,code)}).mappings().first()
    now=datetime.now(timezone.utc)
    if not row or not row['enabled'] or not row['valid_from']<=now<row['valid_to']:raise Denied(422,'DISCOUNT_UNAVAILABLE')
    return DiscountRef(id=row['id'],name=row['name'],version=row['version'])

def evaluate(db,access,body,*,applying=False):
    customer(db,access,body)
    if applying and body.discount_id:access.require('quote.discount')
    now=datetime.now(timezone.utc)
    base=catalog.bom(db,body.bom_id)
    if base.state!='published':raise Denied(422,'PUBLISHED_BOM_REQUIRED')
    snapshot=base.snapshot
    excluded=set(body.excluded_sku_ids)
    existing={x.sku.id for x in snapshot.technical_lines}
    if not excluded<=existing or snapshot.subject.id in excluded:raise Denied(422,'INVALID_EXCLUSION')
    # Excluding a nested package also excludes its internal rows only when explicitly
    # named; flattened row selections are visible and never imply a price credit.
    technical=[x for x in snapshot.technical_lines if x.sku.id not in excluded]
    for item in body.additions:
        if item.sku_id==snapshot.subject.id:raise Denied(422,'DUPLICATE_SUBJECT')
        # Existing included items must first be explicitly removed to replace them.
        if item.sku_id in {x.sku.id for x in technical}:raise Denied(422,'DUPLICATE_COMPONENT')
        technical.append(TechnicalLine(sku=catalog.sku(db,item.sku_id),quantity=item.quantity,required=True,charge_mode='separate'))
    # Transaction-time sale validity checks all selected snapshot SKUs, including
    # nested included parts, without rewriting any published snapshot.
    current={id:catalog.sku(db,id) for id in {snapshot.subject.id,*[x.sku.id for x in technical]}}
    preview=[x.model_copy(update={'sku':current[x.sku.id]}) for x in technical]
    issues=catalog.checks(preview,snapshot.rule)
    def issue(code,status,message):issues.append(Check(code=code,status=status,message=message))
    for item in current.values():
        if not item.enabled:issue('DISABLED_SKU','BLOCK',item.number+' 已停用，不能作为当前可售配置')
    if current[snapshot.subject.id].category!='host':issue('HOST_CATEGORY','BLOCK','主体当前类别不是主机')
    selected_categories={current[snapshot.subject.id].category}|{x.sku.category for x in preview if x.required}
    required_categories={'host','cpu','memory','psu','system_disk'}|{x.sku.category for x in snapshot.technical_lines if x.required}
    for category in sorted(required_categories):
        if category not in selected_categories:issue('MISSING_'+category,'BLOCK','开发完整性要求缺少 '+category+'；不是供应商认证规则')
    commercial={snapshot.subject.id:1}
    for item in technical:
        if item.charge_mode=='separate':commercial[item.sku.id]=commercial.get(item.sku.id,0)+item.quantity
    lines=[];complete=True;unit_total=Decimal(0)
    for id,quantity in commercial.items():
        source=catalog.current_price(db,id,body.scope,body.tax_included,now)
        value=money(Decimal(source['amount'])*quantity) if source['status']=='KNOWN' else None
        if value is None:
            complete=False;issue('PRICE_'+source['status'],'BLOCK',current[id].number+' 当前价格不可用：'+source['status'])
        else:unit_total+=value
        lines.append(PricedLine(sku_id=id,name=current[id].name,quantity=quantity,unit_price=source['amount'],line_amount=format(value,'.2f') if value is not None else None,source=source))
    subtotal=money(unit_total*body.quantity) if complete else None
    discount=None;basis=None;amount=Decimal(0);valid_discount=True
    if body.discount_id:
        policy=catalog.row(db,'quote_discounts',body.discount_id)
        discount=DiscountRef(id=policy['id'],name=policy['name'],version=policy['version']);basis=policy['basis_points']
        valid_discount=(policy['enabled'] and policy['valid_from']<=now<policy['valid_to'] and policy['scope']==body.scope and policy['tax_included']==body.tax_included)
        if subtotal is not None and subtotal<policy['minimum']:valid_discount=False
        if not valid_discount:issue('DISCOUNT_UNAVAILABLE','BLOCK','折扣停用、过期、范围/口径不符或未达到最低金额；请移除或重新选择')
        elif subtotal is not None:amount=min(money(subtotal*Decimal(basis)/Decimal(10000)),policy['maximum_discount'],subtotal)
    total=money(subtotal-amount) if subtotal is not None and valid_discount else None
    issue('SALE_POLICY','UNKNOWN','真实销售/发布政策未配置；这里只保存草稿，不是最终报价，不预占或核销折扣')
    values=dict(calculated_at=now,config_hash=digest(body.model_dump(mode='json')),fingerprint='',priced_lines=lines,technical_lines=preview,checks=issues,
                subtotal=format(subtotal,'.2f') if subtotal is not None else None,discount_amount=format(amount,'.2f') if total is not None else None,total=format(total,'.2f') if total is not None else None,
                amount_complete=total is not None,sale_ready=False,tax_included=body.tax_included,discount=discount,discount_basis_points=basis)
    result=Calculation(**values)
    stable=result.model_dump(mode='json',exclude={'calculated_at','fingerprint'})
    for item in stable['priced_lines']:item['source'].pop('as_of')
    result.fingerprint=digest(stable)
    return result

def configuration(db,row):
    return QuoteInput(**{k:row[k] for k in QuoteInput.model_fields if k not in ('additions','excluded_sku_ids')},
        additions=list(db.execute(text('SELECT sku_id,quantity FROM quote_selections WHERE draft_id=:id ORDER BY sku_id'),{'id':row['id']}).mappings()),
        excluded_sku_ids=list(db.scalars(text('SELECT sku_id FROM quote_exclusions WHERE draft_id=:id ORDER BY sku_id'),{'id':row['id']})))

def detail(db,access,id):
    row=catalog.row(db,'quote_drafts',id);body=configuration(db,row)
    current=evaluate(db,access,body)
    saved=Calculation.model_validate(row['calculation'])
    return QuoteDetail(id=id,version=row['version'],config=body,saved_calculation=saved,current_calculation=current,needs_reprice=current.fingerprint!=saved.fingerprint)

def listing(db,access):
    access.require('crm.read')
    return list(db.execute(text('''SELECT q.id,q.name,q.customer_id,q.version FROM quote_drafts q JOIN crm_customers c ON c.id=q.customer_id
      WHERE (:all OR c.owner_id=:actor) ORDER BY q.name,q.id LIMIT 100'''),{'all':access.data_scope=='all','actor':access.actor_id}).mappings())

def save(db,access,body,key,request_id,id=None):
    if not key or len(key)>128:raise Denied(422,'IDEMPOTENCY_KEY_REQUIRED')
    # Recheck current and proposed customer visibility before replaying any response.
    if id:
        current=catalog.row(db,'quote_drafts',id)
        customer(db,access,configuration(db,current))
    customer(db,access,body)
    if body.discount_id:access.require('quote.discount')
    operation='quote.update:'+str(id) if id else 'quote.create'
    args=dict(t=access.tenant_id,a=access.actor_id,o=operation,k=key)
    hashed=digest(body.model_dump(mode='json'))
    prior=db.execute(text('SELECT request_hash,response FROM quote_commands WHERE tenant_id=:t AND actor_id=:a AND operation=:o AND key=:k'),args).mappings().first()
    if prior:
        if prior['request_hash']!=hashed:raise Denied(409,'IDEMPOTENCY_CONFLICT')
        return QuoteDetail.model_validate(prior['response'])
    if id:catalog.expected(current,body.expected_version)
    config=QuoteInput.model_validate(body.model_dump(exclude={'expected_version'}))
    # Canonical ordering prevents a reload from marking equivalent selections stale.
    config.additions.sort(key=lambda x:str(x.sku_id));config.excluded_sku_ids.sort(key=str)
    calculated=evaluate(db,access,config,applying=True)
    values=config.model_dump(exclude={'additions','excluded_sku_ids'})
    if id:
        catalog.update(db,'quote_drafts',id,{**values,'version':body.expected_version+1,'calculation':calculated.model_dump_json()})
        for table in ('quote_selections','quote_exclusions'):db.execute(text(f'DELETE FROM {table} WHERE draft_id=:id'),{'id':id})
    else:
        id=uuid4();catalog.insert(db,'quote_drafts',dict(tenant_id=access.tenant_id,id=id,owner_id=access.actor_id,**values,calculation=calculated.model_dump_json()))
    for item in config.additions:catalog.insert(db,'quote_selections',dict(tenant_id=access.tenant_id,draft_id=id,**item.model_dump()))
    for sku_id in config.excluded_sku_ids:catalog.insert(db,'quote_exclusions',dict(tenant_id=access.tenant_id,draft_id=id,sku_id=sku_id))
    result=detail(db,access,id)
    db.execute(text('INSERT INTO quote_commands VALUES (:t,:a,:o,:k,:hash,CAST(:response AS jsonb))'),{**args,'hash':hashed,'response':result.model_dump_json()})
    audit(db,access.actor_id,access.tenant_id,operation,id,'allowed',request_id)
    return result
