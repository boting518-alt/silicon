"""Transactional customer aggregate; no contract-derived identity or business mocks."""
import hashlib
import json
from uuid import uuid4
from sqlalchemy import text
from silicon.identity.access import Denied, audit
from silicon.crm.models import CustomerDetail

BASE='SELECT c.*,u.display_name AS owner_name,(SELECT count(*) FROM crm_contacts p WHERE p.customer_id=c.id) AS contact_count,(SELECT count(*) FROM crm_projects p WHERE p.customer_id=c.id) AS project_count FROM crm_customers c JOIN identity_users u ON u.id=c.owner_id'


def visible(access):
    return " AND c.owner_id=:actor" if access.data_scope=='own' else ''


def detail(db,access,customer_id,*,lock=False):
    row=db.execute(text(BASE+' WHERE c.id=:id'+visible(access)+(' FOR UPDATE OF c' if lock else '')),
                   {'id':customer_id,'actor':access.actor_id}).mappings().first()
    if row is None: raise Denied(404,'NOT_FOUND')
    result=dict(row)
    args={'id':customer_id}
    for field,table in [('contacts','crm_contacts'),('projects','crm_projects'),('sites','crm_sites'),('responsibilities','crm_responsibilities'),('role_history','crm_role_history')]:
        order='role' if field=='responsibilities' else 'id'
        result[field]=[dict(r) for r in db.execute(text(f'SELECT * FROM {table} WHERE customer_id=:id ORDER BY {order}'),args).mappings()]
    for project in result['projects']:
        project['people']=[dict(r) for r in db.execute(text('SELECT contact_id,role FROM crm_project_people WHERE project_id=:id ORDER BY role,contact_id'),{'id':project['id']}).mappings()]
    # Output models never accept internal table fields as input; select only public aggregate keys.
    for field,keys in [('contacts',('id','name','title','phone','email')),('projects',('id','name','notes','people')),('sites',('id','name','address')),('responsibilities',('role','user_id'))]:
        result[field]=[{k:r[k] for k in keys} for r in result[field]]
    return CustomerDetail.model_validate(result)


def listing(db,access,q,page,page_size):
    clause=" WHERE (c.name ILIKE :q OR c.number ILIKE :q OR c.city ILIKE :q OR EXISTS (SELECT 1 FROM crm_contacts p WHERE p.customer_id=c.id AND p.name ILIKE :q))"+visible(access)
    args={'q':'%'+q+'%','actor':access.actor_id,'limit':page_size,'offset':(page-1)*page_size}
    total=db.scalar(text('SELECT count(*) FROM crm_customers c'+clause),args)
    rows=db.execute(text(BASE+clause+' ORDER BY c.created_at DESC,c.id LIMIT :limit OFFSET :offset'),args).mappings().all()
    stats=db.execute(text('WITH selected AS (SELECT c.id,c.province FROM crm_customers c'+clause+''')
        SELECT (SELECT count(*) FROM crm_contacts WHERE customer_id IN (SELECT id FROM selected)) AS contact_total,
               (SELECT count(*) FROM crm_projects WHERE customer_id IN (SELECT id FROM selected)) AS project_total,
               (SELECT count(DISTINCT province) FROM selected WHERE province<>'') AS province_total'''),args).mappings().one()
    return {'items':list(rows),'total':total,'page':page,'page_size':page_size,**stats}


def save(db,access,body,key,request_id,customer_id=None):
    if not key or len(key)>128: raise Denied(422,'IDEMPOTENCY_KEY_REQUIRED')
    operation='customer.create' if customer_id is None else 'customer.update:'+str(customer_id)
    raw=body.model_dump(mode='json')
    fingerprint=hashlib.sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    args={'tenant':access.tenant_id,'actor':access.actor_id,'operation':operation,'key':key}
    # Serialize this exact tenant/actor/operation/key, including an initially absent command row.
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:domain,0))'),
               {'domain':f'{access.tenant_id}:{access.actor_id}:{operation}:{key}'})
    prior=db.execute(text('SELECT request_hash,response FROM crm_commands WHERE tenant_id=:tenant AND actor_id=:actor AND operation=:operation AND key=:key'),args).mappings().first()
    if customer_id is not None:
        current=detail(db,access,customer_id,lock=True)
    if prior:
        if prior['request_hash']!=fingerprint:raise Denied(409,'IDEMPOTENCY_CONFLICT')
        return CustomerDetail.model_validate(prior['response'])
    if customer_id is not None and current.version!=body.expected_version:raise Denied(409,'VERSION_CONFLICT')
    customer_id=customer_id or uuid4()
    duplicate=db.scalar(text('SELECT id FROM crm_customers WHERE number=:number AND id<>:id'),{'number':body.number,'id':customer_id})
    if duplicate:raise Denied(409,'CUSTOMER_NUMBER_EXISTS')
    scalars={k:raw[k] for k in ('number','name','province','city','industry','level','stage','notes')}
    scalars.update(tenant=access.tenant_id,id=customer_id,actor=access.actor_id)
    if operation=='customer.create':
        db.execute(text('''INSERT INTO crm_customers(tenant_id,id,number,name,province,city,industry,level,stage,notes,owner_id)
            VALUES (:tenant,:id,:number,:name,:province,:city,:industry,:level,:stage,:notes,:actor)'''),scalars)
    else:
        db.execute(text('''UPDATE crm_customers SET number=:number,name=:name,province=:province,city=:city,
            industry=:industry,level=:level,stage=:stage,notes=:notes,version=version+1,updated_at=now() WHERE id=:id'''),scalars)
    relations(db,access,customer_id,body)
    result=detail(db,access,customer_id)
    db.execute(text('''INSERT INTO crm_commands(tenant_id,actor_id,operation,key,request_hash,response)
        VALUES (:tenant,:actor,:operation,:key,:hash,CAST(:response AS jsonb))'''),
        {**args,'hash':fingerprint,'response':result.model_dump_json()})
    audit(db,access.actor_id,access.tenant_id,'customer.create' if operation=='customer.create' else 'customer.update',customer_id,'allowed',request_id)
    return result


def relations(db,access,customer_id,body):
    args={'tenant':access.tenant_id,'customer':customer_id}
    # Existing contact/project IDs owned by another customer cannot be appropriated.
    for field,table in [('contacts','crm_contacts'),('projects','crm_projects'),('sites','crm_sites')]:
        ids=[x.id for x in getattr(body,field)]
        if ids and db.scalar(text(f'SELECT count(*) FROM {table} WHERE id=ANY(:ids) AND customer_id<>:customer'),{'ids':ids,'customer':customer_id}):
            raise Denied(422,'INVALID_RELATIONSHIP')
    members={}
    # Use the narrow lock function rather than granting the app membership UPDATE rights.
    for owner in body.responsibilities:
        if not db.execute(text('SELECT * FROM lock_membership(:actor,:tenant)'),{'actor':owner.user_id,'tenant':access.tenant_id}).first():
            raise Denied(422,'INVALID_RESPONSIBILITY')
        members[owner.user_id]=db.scalar(text('SELECT display_name FROM identity_users WHERE id=:id'),{'id':owner.user_id})
    for table in ('crm_project_people','crm_responsibilities','crm_projects','crm_contacts','crm_sites'):
        db.execute(text(f'DELETE FROM {table} WHERE customer_id=:customer'),args)
    assignments={}
    contacts={x.id:x for x in body.contacts}
    for contact in body.contacts:
        db.execute(text('''INSERT INTO crm_contacts(tenant_id,customer_id,id,name,title,phone,email)
            VALUES (:tenant,:customer,:id,:name,:title,:phone,:email)'''),{**args,**contact.model_dump()})
    for project in body.projects:
        db.execute(text('INSERT INTO crm_projects(tenant_id,customer_id,id,name,notes) VALUES (:tenant,:customer,:id,:name,:notes)'),
                   {**args,**project.model_dump(exclude={'people'})})
        for person in project.people:
            db.execute(text('INSERT INTO crm_project_people VALUES (:tenant,:customer,:project,:contact,:role)'),
                       {**args,'project':project.id,'contact':person.contact_id,'role':person.role})
            assignments[('customer',project.id,person.role,person.contact_id)]=(contacts[person.contact_id].name,project.name)
    for site in body.sites:
        db.execute(text('INSERT INTO crm_sites(tenant_id,customer_id,id,name,address) VALUES (:tenant,:customer,:id,:name,:address)'),{**args,**site.model_dump()})
    for owner in body.responsibilities:
        db.execute(text('INSERT INTO crm_responsibilities VALUES (:tenant,:customer,:role,:user_id)'),{**args,**owner.model_dump()})
        assignments[('internal',None,owner.role,owner.user_id)]=(members[owner.user_id],'')
    active=db.execute(text('SELECT * FROM crm_role_history WHERE customer_id=:customer AND valid_until IS NULL'),args).mappings().all()
    for row in active:
        signature=(row['party'],row['project_id'],row['role'],row['person_id'])
        if signature in assignments:
            assignments.pop(signature)
        else:
            db.execute(text('UPDATE crm_role_history SET valid_until=now() WHERE id=:id'),{'id':row['id']})
    for (party,project,role,person),(name,project_name) in assignments.items():
        db.execute(text('''INSERT INTO crm_role_history(tenant_id,id,customer_id,party,project_id,role,person_id,person_name,project_name,changed_by)
            VALUES (:tenant,:id,:customer,:party,:project,:role,:person,:name,:project_name,:actor)'''),
            {**args,'id':uuid4(),'party':party,'project':project,'role':role,'person':person,'name':name,'project_name':project_name,'actor':access.actor_id})
