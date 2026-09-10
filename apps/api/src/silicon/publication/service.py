"""All callers hold identity shares -> catalog share -> quote guard -> CRM share.

Commands share the quote guard with draft edits; immutable facts are never updated.
Replay stores identifiers, not authorization-sensitive cached responses.
"""
from datetime import datetime,timezone
import json
from uuid import uuid4
from sqlalchemy import text
from silicon.identity.access import Denied,audit,authorize
from silicon.catalog import service as c
from silicon.crm import service as crm
from silicon.quotes import service as q
from silicon.quotes.models import QuoteInput
from silicon.catalog.models import Check
from .models import Frozen,Party,Policy,Candidate,Published,Contract


def now():return datetime.now(timezone.utc)
def encode(value):return json.dumps(value,default=str,ensure_ascii=False)

def prelock(db,a):
    # Before domain locks: hold every currently active tenant participant's identity
    # shares, including submitter/approver. No membership locks after CRM access.
    result={}
    ids=db.scalars(text('SELECT user_id FROM memberships WHERE tenant_id=:t AND active ORDER BY user_id'),{'t':a.tenant_id}).all()
    for id in ids:
        try:result[id]=authorize(db,id,a.tenant_id)
        except Denied:continue # inactive identity is not a valid participant
    return result

def visible(db,a,content):
    a.require('crm.read')
    return crm.detail(db,a,content.config.customer_id)

def participant(people,id,permission,customer):
    a=people.get(id)
    if not a:raise Denied(409,'PARTICIPANT_ACCESS_CHANGED')
    a.require(permission)
    if not a.owns(customer.owner_id):raise Denied(409,'PARTICIPANT_ACCESS_CHANGED')

def policy(db):
    row=db.execute(text('SELECT * FROM publication_policies WHERE enabled')).mappings().first()
    if not row:raise Denied(422,'PUBLICATION_POLICY_REQUIRED')
    result=Policy(**{k:row[k] for k in Policy.model_fields})
    if result.discount_quota!='unlimited':raise Denied(422,'DISCOUNT_QUOTA_UNSUPPORTED')
    return result

def frozen(db,a,draft,until):
    until=until.astimezone(timezone.utc)
    p=policy(db)
    if until<=now():raise Denied(422,'QUOTE_EXPIRED')
    body=q.configuration(db,draft);customer=q.customer(db,a,body)
    calculated=q.evaluate(db,a,body)
    if not calculated.amount_complete or any(x.status=='BLOCK' for x in calculated.checks):raise Denied(422,'PUBLICATION_HARD_BLOCK')
    # Preserve all technical statuses. TASK-005's blanket sale_ready is not a gate.
    calculated.checks=[x.model_copy(update={'message':'发布政策已配置；仍须人工确认责任范围'}) if x.code=='SALE_POLICY' else x for x in calculated.checks]
    calculated.checks.append(Check(code='COST_UNKNOWN',status='UNKNOWN',message='成本、利润和贡献率未知，需人工承担本阶段风险'))
    calculated.checks.append(Check(code='CHARGES_UNKNOWN',status='UNKNOWN',message='税额拆分、运费、服务费未配置，不计作零元'))
    discount=None
    if body.discount_id:
        row=c.row(db,'quote_discounts',body.discount_id)
        discount={k:v for k,v in row.items() if k not in ('tenant_id','code_hash')}
        discount=json.loads(encode(discount))
    bom=c.bom(db,body.bom_id)
    return Frozen(config=body,calculation=calculated,host=c.sku(db,bom.snapshot.subject.id),bom=bom.snapshot,
       customer=Party(id=customer.id,number=customer.number,name=customer.name,contacts=customer.contacts,
          project=next(x for x in customer.projects if x.id==body.project_id),sites=customer.sites,responsibilities=customer.responsibilities,responsibility_names={str(x.user_id):db.scalar(text("SELECT display_name FROM identity_users WHERE id=:id"),{"id":x.user_id}) for x in customer.responsibilities}),
       policy=p,valid_until=until,discount_conditions=discount,
       unknown_fields=['cost','profit','contribution_rate','tax_amount','shipping','service_fee','seller_legal_details'],development=p.mode=='development')

def hash_content(content):
    value=content.model_dump(mode='json')
    value['calculation'].pop('calculated_at');value['calculation'].pop('fingerprint')
    for line in value['calculation']['priced_lines']:line['source'].pop('as_of',None)
    return q.digest(value)

def candidate_row(db,a,id):
    row=c.row(db,'publication_candidates',id);content=Frozen.model_validate(row['content']);visible(db,a,content)
    return row,content

def decision(db,id):
    return db.execute(text('SELECT * FROM publication_decisions WHERE candidate_id=:id'),{'id':id}).mappings().first()

def fresh(db,a,row,people):
    draft=c.row(db,'quote_drafts',row['draft_id'])
    if draft['version']!=row['draft_version'] or draft['approval_candidate_id']!=row['id']:raise Denied(409,'APPROVAL_INVALIDATED')
    new=frozen(db,a,draft,row['valid_until'])
    if hash_content(new)!=row['content_hash']:raise Denied(409,'APPROVAL_INVALIDATED')
    customer=visible(db,a,new)
    participant(people,row['submitter_id'],'quote.submit',customer)
    dec=decision(db,row['id'])
    if dec:participant(people,dec['actor_id'],'quote.approve',customer)
    return new

def candidate(db,a,id,people):
    row,content=candidate_row(db,a,id);dec=decision(db,id)
    issued=db.scalar(text('SELECT id FROM quote_versions WHERE candidate_id=:id'),{'id':id})
    state='published' if issued else ('approved' if dec['approved'] else 'rejected') if dec else 'pending'
    if not issued:
        try:fresh(db,a,row,people)
        except Denied:state='invalidated'
    internal='quote.approve' in a.permissions
    return Candidate(id=id,draft_id=row['draft_id'],draft_version=row['draft_version'],submitter_id=row['submitter_id'],content_hash=row['content_hash'],content=content,state=state,
       decision_id=dec['id'] if dec else None,approver_id=dec['actor_id'] if dec else None,
       note=dec['note'] if dec and internal else None,confirmations=dec['confirmations'] if dec and internal else None,
       source_version_id=c.row(db,'quote_drafts',row['draft_id'])['source_version_id'])

def require_unpublished(db,id):
    if db.scalar(text("SELECT id FROM quote_versions WHERE draft_id=:id LIMIT 1"),{"id":id}):
        raise Denied(409,"PUBLISHED_DRAFT_REQUIRES_REVISION")

def submit(db,a,id,body):
    require_unpublished(db,id)
    draft=c.row(db,'quote_drafts',id);c.expected(draft,body.expected_version)
    content=frozen(db,a,draft,body.valid_until);new=uuid4()
    c.insert(db,'publication_candidates',dict(tenant_id=a.tenant_id,id=new,draft_id=id,draft_version=draft['version'],submitter_id=a.actor_id,
       policy_id=content.policy.id,content_hash=hash_content(content),content=content.model_dump_json(),valid_until=body.valid_until))
    c.update(db,'quote_drafts',id,dict(approval_candidate_id=new))
    return new

def decide(db,a,id,body,people):
    row,content=candidate_row(db,a,id)
    if row['draft_version']!=body.expected_version:raise Denied(409,'VERSION_CONFLICT')
    if row['submitter_id']==a.actor_id:raise Denied(403,'SELF_APPROVAL_FORBIDDEN')
    if decision(db,id):raise Denied(409,'APPROVAL_ALREADY_DECIDED')
    fresh(db,a,row,people)
    if not body.note.strip():raise Denied(422,'EXPLANATION_REQUIRED')
    if body.approved:
        risks={x.code for x in content.calculation.checks if x.status in ('WARN','UNKNOWN')}
        confirmed={x.code for x in body.confirmations if x.explanation.strip() and x.evidence.strip()}
        if risks and not content.policy.allow_risks:raise Denied(422,'RISK_POLICY_FORBIDS')
        if confirmed!=risks or len(body.confirmations)!=len(risks):raise Denied(422,'RISK_CONFIRMATION_REQUIRED')
    c.insert(db,'publication_decisions',dict(tenant_id=a.tenant_id,id=uuid4(),candidate_id=id,actor_id=a.actor_id,approved=body.approved,
         note=body.note,confirmations=encode([x.model_dump() for x in body.confirmations])))
    return id

def state(db,row):
    lifecycle=c.row(db,'quote_version_states',row['id'])
    status='withdrawn' if lifecycle['withdrawn'] else 'expired' if not row['issued_at']<=now()<row['valid_until'] else 'issued'
    return status,lifecycle['version']

def published(db,a,id):
    row=c.row(db,'quote_versions',id);content=Frozen.model_validate(row['content']);visible(db,a,content)
    status,version=state(db,row)
    return Published(**{k:row[k] for k in ('id','candidate_id','decision_id','number','revision','content_hash','issuer_id','issued_at','valid_until')},content=content,state=status,version=version)

def event(db,a,id,action,reason):
    c.insert(db,'publication_events',dict(tenant_id=a.tenant_id,id=uuid4(),quote_version_id=id,actor_id=a.actor_id,action=action,reason=reason))

def issue(db,a,id,body,people):
    row,content=candidate_row(db,a,id)
    if body.expected_version!=row['draft_version']:raise Denied(409,'VERSION_CONFLICT')
    dec=decision(db,id)
    if not dec or not dec['approved']:raise Denied(409,'APPROVAL_REQUIRED')
    # Even a different-key duplicate checks current participants, but returns the
    # existing immutable object, never another number or changed contents.
    existing=db.scalar(text('SELECT id FROM quote_versions WHERE candidate_id=:id'),{'id':id})
    if existing:
        customer=visible(db,a,content)
        participant(people,row['submitter_id'],'quote.submit',customer);participant(people,dec['actor_id'],'quote.approve',customer)
        return existing
    require_unpublished(db,row['draft_id'])
    fresh(db,a,row,people)
    origin=c.row(db,'quote_drafts',row['draft_id'])['source_version_id']
    if origin:
        root=c.row(db,'quote_versions',origin)['number'].split('-R')[0]
        revision=db.scalar(text("SELECT coalesce(max(revision),0)+1 FROM quote_versions WHERE number=:root OR number LIKE :pattern"),{'root':root,'pattern':root+'-R%'})
        number=f'{root}-R{revision}'
    else:
        serial=db.scalar(text("SELECT count(*)+1 FROM quote_versions WHERE revision=1"))
        revision=1;number=f'Q-{serial:06d}'
    new=uuid4()
    c.insert(db,'quote_versions',dict(tenant_id=a.tenant_id,id=new,candidate_id=id,draft_id=row['draft_id'],decision_id=dec['id'],
        number=number,revision=revision,content_hash=row['content_hash'],content=content.model_dump_json(),issuer_id=a.actor_id,issued_at=now(),valid_until=row['valid_until']))
    c.insert(db,'quote_version_states',dict(tenant_id=a.tenant_id,id=new));event(db,a,new,'issued','人工确认发布')
    return new

def withdraw(db,a,id,body):
    item=published(db,a,id)
    if item.version!=body.expected_version:raise Denied(409,'VERSION_CONFLICT')
    if item.state=='withdrawn':raise Denied(409,'ALREADY_WITHDRAWN')
    if not body.reason.strip():raise Denied(422,'EXPLANATION_REQUIRED')
    c.update(db,'quote_version_states',id,dict(version=item.version+1,withdrawn=True));event(db,a,id,'withdrawn',body.reason)
    return id

def contract(db,a,id):
    row=c.row(db,'contract_drafts',id);source=published(db,a,row['quote_version_id'])
    return Contract(id=id,quote_version_id=source.id,source_hash=row['source_hash'],content=Frozen.model_validate(row['content']),created_at=row['created_at'],source_state=source.state,
       missing_fields=['seller_legal_details','signing','payment_schedule','attachments'],source_number=source.number,decision_id=source.decision_id,issuer_id=source.issuer_id,issued_at=source.issued_at)

def convert(db,a,body):
    item=published(db,a,body.quote_version_id)
    if item.state!='issued':raise Denied(409,'SOURCE_NOT_ACTIVE')
    if item.version!=body.expected_version:raise Denied(409,'VERSION_CONFLICT')
    existing=db.scalar(text('SELECT id FROM contract_drafts WHERE quote_version_id=:id'),{'id':item.id})
    if existing:return existing
    id=uuid4();c.insert(db,'contract_drafts',dict(tenant_id=a.tenant_id,id=id,quote_version_id=item.id,source_hash=item.content_hash,content=item.content.model_dump_json(),created_by=a.actor_id))
    return id

def revise(db,a,id,body,key,request):
    item=published(db,a,id)
    if item.version!=body.expected_version:raise Denied(409,'VERSION_CONFLICT')
    config=item.content.config.model_copy(update={'name':item.content.config.name+' · 修订'})
    # Same complete operation scope as publication_commands; creation and source
    # association are one INSERT. Replays never rewrite a draft's source.
    new=q.save(db,a,config,key,request,source_version_id=id)
    return new.id

def command(db,a,op,key,body,request,perform,render):
    if not key or len(key)>100:raise Denied(422,'IDEMPOTENCY_KEY_REQUIRED')
    args=dict(t=a.tenant_id,a=a.actor_id,o=op,k=key)
    prior=db.execute(text('SELECT * FROM publication_commands WHERE tenant_id=:t AND actor_id=:a AND operation=:o AND key=:k'),args).mappings().first()
    hashed=q.digest(body.model_dump(mode='json'))
    if prior:
        if prior['request_hash']!=hashed:raise Denied(409,'IDEMPOTENCY_CONFLICT')
        return render(prior['response_id'])
    id=perform();result=render(id)
    db.execute(text('INSERT INTO publication_commands VALUES (:t,:a,:o,:k,:h,:id)'),{**args,'h':hashed,'id':id})
    audit(db,a.actor_id,a.tenant_id,op,id,'allowed',request)
    return result

def listing(db,a,table,render):
    # Visibility filtering before detail avoids revealing inaccessible identities.
    if table=='publication_candidates':sql='SELECT x.id FROM publication_candidates x JOIN quote_drafts q ON q.id=x.draft_id'
    elif table=='quote_versions':sql='SELECT x.id FROM quote_versions x JOIN quote_drafts q ON q.id=x.draft_id'
    else:sql='SELECT x.id FROM contract_drafts x JOIN quote_versions v ON v.id=x.quote_version_id JOIN quote_drafts q ON q.id=v.draft_id'
    sql+=' JOIN crm_customers c ON c.id=(x.content->\'config\'->>\'customer_id\')::uuid WHERE (:all OR c.owner_id=:actor) ORDER BY '+('x.issued_at' if table=='quote_versions' else 'x.created_at')+',x.id LIMIT 100'
    return [render(id) for id in db.scalars(text(sql),{'all':a.data_scope=='all','actor':a.actor_id})]
