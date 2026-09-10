"""Identity shares -> existing catalog/quote guard -> CRM; no reverse locks.
All contract commands share quote's tenant guard with source withdrawal.
"""
from datetime import date,timedelta
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import text
from silicon.catalog import service as c
from silicon.publication import service as pub
from silicon.quotes import service as q
from silicon.identity.access import Denied,audit
from .models import Fields,Workspace,File,Signed,Order

def today():return date.today()
def signed_id(db,id):return db.scalar(text('SELECT id FROM signed_contracts WHERE contract_id=:id'),{'id':id})
def source(db,a,id):return pub.contract(db,a,id)
def workrow(db,id):return db.execute(text('SELECT * FROM contract_workspaces WHERE id=:id'),{'id':id}).mappings().first()
def public_fields(a,value):
    value=value.model_copy(deep=True)
    if 'contract.contact' not in a.permissions:
        value.project_lead.contact=''
        for x in value.key_contacts:x.contact=''
    return value

def initial(src):
    return Fields(name=src.content.config.name,buyer={'name':src.content.customer.name})
def files(db,id):return [File(**{k:r[k] for k in File.model_fields}) for r in db.execute(text("SELECT * FROM contract_files WHERE contract_id=:id AND state<>'deleted' ORDER BY created_at,id"),{'id':id}).mappings()]
def checks(db,a,src,fields,items,people):
    issues=[]
    if not all([fields.number,fields.name,fields.buyer.name,fields.buyer.address,fields.buyer.representative,fields.seller.name,fields.seller.address,fields.seller.representative,fields.project_lead.name]) or not fields.key_contacts or any(not x.name for x in fields.key_contacts):issues.append('PARTIES_INCOMPLETE')
    for role in ['sales','support']:
        person=getattr(fields,role)
        if not person.user_id or not person.name:issues.append('RESPONSIBILITY_REQUIRED')
        elif person.user_id not in people:issues.append('RESPONSIBILITY_INACTIVE')
    if fields.signing_date is None or fields.signing_date>today():issues.append('SIGNING_DATE_INVALID')
    if not fields.delivery_date and not fields.delivery_note.strip():issues.append('DELIVERY_REQUIRED')
    amount=Decimal(src.content.calculation.total or '-1')
    if amount<=0:issues.append('ZERO_CONTRACT_POLICY_UNCONFIGURED')
    if not fields.payments or sum((x.amount for x in fields.payments),Decimal(0))!=amount:issues.append('PAYMENTS_UNBALANCED')
    if src.source_state!='issued':issues.append('SOURCE_NOT_ACTIVE')
    if not any(x.category=='proof' and x.state=='linked' for x in items):issues.append('PROOF_REQUIRED')
    # Development flag is immutable; formal registration rechecks explicit policy.
    if not src.content.development:
        try:
            p=pub.policy(db)
            if p.mode!='formal':issues.append('FORMAL_POLICY_REQUIRED')
        except Denied:issues.append('FORMAL_POLICY_REQUIRED')
    return sorted(set(issues))
def frozen(src,fields,items):
    payments=[]
    for x in fields.payments:
        data=x.model_dump(mode='json')
        if x.trigger=='signing' and fields.signing_date:data['resolved_due_date']=(fields.signing_date+timedelta(days=x.offset_days)).isoformat()
        else:data['resolved_due_date']=x.due_date.isoformat() if x.due_date else None
        data['fulfillment_state']='planned' if data['resolved_due_date'] else 'awaiting_trigger'
        payments.append(data)
    return {'fields':fields.model_dump(mode='json'),'commercial':src.content.model_dump(mode='json'),'source_id':str(src.quote_version_id),'source_hash':src.source_hash,
            'attachments':[x.model_dump(mode='json') for x in items if x.state=='linked' and not x.supplemental],'payments':payments,'development':src.content.development,'registration_kind':'offline_fact_registration'}
def detail(db,a,id,people):
    src=source(db,a,id);row=workrow(db,id);fields=Fields.model_validate(row['fields']) if row else initial(src);items=files(db,id)
    snapshot=frozen(src,fields,items);problems=checks(db,a,src,fields,items,people);sid=signed_id(db,id)
    history=[]
    for r in db.execute(text('SELECT version,fields,actor_id,created_at FROM contract_editions WHERE contract_id=:id ORDER BY version'),{'id':id}).mappings():
        history.append({**r,'fields':public_fields(a,Fields.model_validate(r['fields'])).model_dump(mode='json')})
    # Source publication can include CRM phone/email; apply same field boundary.
    if 'contract.contact' not in a.permissions:
        src=src.model_copy(deep=True)
        for x in src.content.customer.contacts:x.phone='';x.email=''
    return Workspace(id=id,version=row['version'] if row else 0,state='signed' if sid else 'draft',fields=public_fields(a,fields),source=src,files=items,checks=problems,ready=not problems and not sid,
        content_hash=q.digest(snapshot),signed_id=sid,order_id=db.scalar(text('SELECT id FROM sales_orders WHERE contract_version_id=:id'),{'id':sid}) if sid else None,history=history)
def editable(db,id,version):
    if signed_id(db,id):raise Denied(409,'CONTRACT_ALREADY_SIGNED')
    row=workrow(db,id)
    if (row['version'] if row else 0)!=version:raise Denied(409,'VERSION_CONFLICT')
    return row

def save(db,a,id,body,people):
    src=source(db,a,id);row=editable(db,id,body.expected_version);value=body.fields.model_copy(deep=True)
    if value.project_lead.contact or any(x.contact for x in value.key_contacts):a.require('contract.contact')
    old=Fields.model_validate(row['fields']) if row else initial(src)
    # Keep historical assigned names unless identity actually changes.
    for role in ['sales','support']:
        entry=getattr(value,role);prior=getattr(old,role)
        if entry.user_id!=prior.user_id:
            if entry.user_id and entry.user_id not in people:raise Denied(422,'RESPONSIBILITY_INACTIVE')
            entry.name=db.scalar(text('SELECT display_name FROM identity_users WHERE id=:id'),{'id':entry.user_id}) if entry.user_id else ''
        else:entry.name=prior.name
    if len({x.id for x in value.payments})!=len(value.payments):raise Denied(422,'DUPLICATE_PAYMENT')
    v=body.expected_version+1
    values={'version':v,'number':value.number or None,'fields':value.model_dump_json(),'sales_id':value.sales.user_id,'support_id':value.support.user_id}
    if row:c.update(db,'contract_workspaces',id,values)
    else:c.insert(db,'contract_workspaces',{'tenant_id':a.tenant_id,'id':id,**values})
    db.execute(text('DELETE FROM contract_payments WHERE contract_id=:id'),{'id':id})
    for pos,p in enumerate(value.payments):c.insert(db,'contract_payments',dict(tenant_id=a.tenant_id,contract_id=id,id=p.id,position=pos,amount=p.amount,body=p.model_dump_json()))
    c.insert(db,'contract_editions',dict(tenant_id=a.tenant_id,id=uuid4(),contract_id=id,version=v,fields=value.model_dump_json(),actor_id=a.actor_id))
    return id

def bump(db,a,id,row):
    if not row:raise Denied(409,'SAVE_CONTRACT_FIRST')
    c.update(db,'contract_workspaces',id,{'version':row['version']+1})
def file_row(db,a,id):
    row=c.row(db,'contract_files',id);source(db,a,row['contract_id'])
    if row['state']=='deleted':raise Denied(404,'NOT_FOUND')
    return row

def upload(db,a,id,metadata,expected):
    source(db,a,id);row=workrow(db,id)
    if (row['version'] if row else 0)!=expected:raise Denied(409,'VERSION_CONFLICT')
    metadata={**metadata,'supplemental':bool(signed_id(db,id))}
    fid=uuid4();c.insert(db,'contract_files',dict(tenant_id=a.tenant_id,id=fid,contract_id=id,uploaded_by=a.actor_id,state='pending',**metadata));return fid

def associate(db,a,id,file_id,body,remove=False):
    source(db,a,id);row=workrow(db,id);f=file_row(db,a,file_id)
    if (row['version'] if row else 0)!=body.expected_version:raise Denied(409,'VERSION_CONFLICT')
    if signed_id(db,id) and not f['supplemental']:raise Denied(409,'CONTRACT_ALREADY_SIGNED')
    if str(f['contract_id'])!=str(id):raise Denied(404,'NOT_FOUND')
    if db.scalar(text('SELECT 1 FROM signed_files WHERE file_id=:id'),{'id':file_id}):raise Denied(409,'SIGNED_FILE_IMMUTABLE')
    if f['state']=='linked' and not remove:raise Denied(409,'ALREADY_LINKED')
    c.update(db,'contract_files',file_id,{'state':'deleted' if remove else 'linked'})
    if not signed_id(db,id):bump(db,a,id,row)
    return id

def sign(db,a,id,body,people):
    src=source(db,a,id);sid=signed_id(db,id)
    if sid:
        row=c.row(db,'signed_contracts',sid)
        if row['version']!=body.expected_version or row['content_hash']!=body.content_hash:raise Denied(409,'CONTRACT_ALREADY_SIGNED')
        return sid
    row=editable(db,id,body.expected_version)
    fields=Fields.model_validate(row['fields']) if row else initial(src);items=files(db,id)
    problems=checks(db,a,src,fields,items,people)
    if problems:raise Denied(422,problems[0])
    content=frozen(src,fields,items);digest=q.digest(content)
    if digest!=body.content_hash:raise Denied(409,'CONFIRMATION_STALE')
    sid=uuid4();c.insert(db,'signed_contracts',dict(tenant_id=a.tenant_id,id=sid,contract_id=id,number=fields.number,version=body.expected_version,content_hash=digest,content=pub.encode(content),quote_version_id=src.quote_version_id,registered_by=a.actor_id))
    for item in items:
        if item.state=='linked':c.insert(db,'signed_files',dict(tenant_id=a.tenant_id,contract_version_id=sid,file_id=item.id))
    c.insert(db,'sales_orders',dict(tenant_id=a.tenant_id,id=uuid4(),contract_version_id=sid,quote_version_id=src.quote_version_id,number='SO-'+fields.number,amount=Decimal(src.content.calculation.total),currency='CNY',state='pending_fulfillment',content=pub.encode(content)))
    return sid

def redacted(a,content):
    import copy
    value=copy.deepcopy(content)
    if 'contract.contact' not in a.permissions:
        value['fields']['project_lead']['contact']=''
        for x in value['fields']['key_contacts']:x['contact']=''
        for x in value['commercial']['customer']['contacts']:x['phone']='';x['email']=''
    return value

def signed(db,a,id):
    r=c.row(db,'signed_contracts',id);source(db,a,r['contract_id'])
    return Signed(**{k:r[k] for k in Signed.model_fields if k not in ('content','order_id')},content=redacted(a,r['content']),order_id=db.scalar(text('SELECT id FROM sales_orders WHERE contract_version_id=:id'),{'id':id}))
def order(db,a,id):
    r=c.row(db,'sales_orders',id);signed(db,a,r['contract_version_id'])
    return Order(**{k:r[k] for k in Order.model_fields if k!='content'},content=redacted(a,r['content']))

def command(db,a,op,key,body,request,perform,render):
    if not key or len(key)>100:raise Denied(422,'IDEMPOTENCY_KEY_REQUIRED')
    args=dict(t=a.tenant_id,a=a.actor_id,o=op,k=key);digest=q.digest(body)
    old=db.execute(text('SELECT * FROM contract_commands WHERE tenant_id=:t AND actor_id=:a AND operation=:o AND key=:k'),args).mappings().first()
    if old:
        if old['request_hash']!=digest:raise Denied(409,'IDEMPOTENCY_CONFLICT')
        return render(old['response_id'])
    id=perform();result=render(id)
    db.execute(text('INSERT INTO contract_commands VALUES (:t,:a,:o,:k,:h,:id)'),{**args,'h':digest,'id':id});audit(db,a.actor_id,a.tenant_id,op,id,'allowed',request);return result
