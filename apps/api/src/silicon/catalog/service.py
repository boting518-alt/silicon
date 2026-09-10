"""Catalog aggregates. Call only while holding the tenant catalog transaction guard.

One tenant guard precedes every aggregate access: shared for reads, exclusive for
commands. This deliberately trades write concurrency for a simple graph/price
serialization boundary; no catalog operation takes identity locks afterwards.
"""
import hashlib
import json
from uuid import uuid4
from sqlalchemy import text
from silicon.identity.access import Denied, audit
from .models import Sku, Specs, Rule, Bom, BomSnapshot, TechnicalLine, Check, PriceBook


def guard(db,access,write=False):
    function='pg_advisory_xact_lock' if write else 'pg_advisory_xact_lock_shared'
    db.execute(text(f'SELECT {function}(hashtextextended(:domain,0))'),{'domain':f'catalog:{access.tenant_id}'})


def row(db,table,id):
    value=db.execute(text(f'SELECT * FROM {table} WHERE id=:id'),{'id':id}).mappings().first()
    if value is None:raise Denied(404,'NOT_FOUND')
    return dict(value)


def insert(db,table,values):
    columns=','.join(values)
    params=','.join(':'+key for key in values)
    db.execute(text(f'INSERT INTO {table} ({columns}) VALUES ({params})'),values)


def update(db,table,id,values):
    assignments=','.join(f'{key}=:{key}' for key in values)
    db.execute(text(f'UPDATE {table} SET {assignments} WHERE id=:id'),{**values,'id':id})


def command(db,access,operation,key,body,request_id,perform):
    if not key or len(key)>128:raise Denied(422,'IDEMPOTENCY_KEY_REQUIRED')
    digest=hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    args=dict(tenant=access.tenant_id,actor=access.actor_id,operation=operation,key=key)
    prior=db.execute(text('SELECT request_hash,response FROM catalog_commands WHERE tenant_id=:tenant AND actor_id=:actor AND operation=:operation AND key=:key'),args).mappings().first()
    if prior:
        if prior['request_hash']!=digest:raise Denied(409,'IDEMPOTENCY_CONFLICT')
        return prior['response']
    result=perform()
    response=result.model_dump(mode='json')
    db.execute(text('INSERT INTO catalog_commands VALUES (:tenant,:actor,:operation,:key,:hash,CAST(:response AS jsonb))'),{**args,'hash':digest,'response':json.dumps(response)})
    audit(db,access.actor_id,access.tenant_id,operation,response['id'],'allowed',request_id)
    return response


def expected(current,version):
    if current['version']!=version:raise Denied(409,'VERSION_CONFLICT')


def draft(current,version):
    expected(current,version)
    if current['state']!='draft':raise Denied(409,'PUBLISHED_IMMUTABLE')


def sku(db,id):
    item=row(db,'catalog_skus',id)
    spec=db.execute(text('SELECT * FROM catalog_specs WHERE sku_id=:id'),{'id':id}).mappings().one()
    manufacturer=row(db,'catalog_manufacturers',item['manufacturer_id'])
    brand=row(db,'catalog_brands',item['brand_id'])
    return Sku(**{k:item[k] for k in ('id','number','name','category','enabled','version')},manufacturer=manufacturer['name'],brand=brand['name'],brand_kind=brand['kind'],specs=Specs(**{k:spec[k] for k in Specs.model_fields}))


def save_sku(db,access,body,id=None):
    if id:expected(row(db,'catalog_skus',id),body.expected_version)
    else:id=uuid4()
    identities={}
    for table,name in [('catalog_manufacturers',body.manufacturer),('catalog_brands',body.brand)]:
        found=db.execute(text(f'SELECT * FROM {table} WHERE name=:name'),{'name':name}).mappings().first()
        if found:
            if table=='catalog_brands' and found['kind']!=body.brand_kind:raise Denied(409,'BRAND_KIND_CONFLICT')
            identities[table]=found['id']
        else:
            identity=uuid4();identities[table]=identity
            values=dict(tenant_id=access.tenant_id,id=identity,name=name)
            if table=='catalog_brands':values['kind']=body.brand_kind
            insert(db,table,values)
    values=dict(number=body.number,name=body.name,category=body.category,enabled=body.enabled,manufacturer_id=identities['catalog_manufacturers'],brand_id=identities['catalog_brands'])
    if hasattr(body,'expected_version'):
        update(db,'catalog_skus',id,{**values,'version':body.expected_version+1})
        db.execute(text('UPDATE catalog_specs SET '+','.join(f'{k}=:{k}' for k in Specs.model_fields)+' WHERE sku_id=:id'),{**body.specs.model_dump(),'id':id})
    else:
        insert(db,'catalog_skus',dict(tenant_id=access.tenant_id,id=id,**values))
        insert(db,'catalog_specs',dict(tenant_id=access.tenant_id,sku_id=id,**body.specs.model_dump()))
    return sku(db,id)


def rule(db,id):
    item=row(db,'catalog_rules',id)
    return Rule(**{k:item[k] for k in Rule.model_fields})


def new_rule(db,access,body,from_id=None):
    family=uuid4()
    if from_id:family=rule(db,from_id).family_id
    revision=db.scalar(text('SELECT COALESCE(max(revision),0)+1 FROM catalog_rules WHERE family_id=:id'),{'id':family})
    id=uuid4();insert(db,'catalog_rules',dict(tenant_id=access.tenant_id,id=id,family_id=family,revision=revision,**body.model_dump()))
    return rule(db,id)


def checks(lines,platform):
    result=[]
    def add(code,status,message):result.append(Check(code=code,status=status,message=message))
    if not platform:add('RULE_SOURCE','UNKNOWN','未选择版本化平台资料；不能确认兼容')
    required=[x for x in lines if x.required]
    for category,field,label in [('cpu','socket','CPU 插槽'),('memory','memory_generation','内存代际')]:
        parts=[x for x in required if x.sku.category==category]
        wanted=getattr(platform,field,None)
        if not wanted or not parts or any(not getattr(x.sku.specs,field) for x in parts):add(field,'UNKNOWN',label+'资料或必选部件不足')
        elif any(getattr(x.sku.specs,field)!=wanted for x in parts):add(field,'BLOCK',label+'与示例平台不一致')
        else:add(field,'PASS',label+'符合所选示例资料（非完整认证）')
    supplies=[x for x in required if x.sku.category=='psu']
    if not supplies:add('POWER','BLOCK','尚无必选电源：不含电源包件需要另选')
    elif not platform or platform.power_budget_w is None or any(x.sku.specs.power_w is None for x in supplies):add('POWER','UNKNOWN','电源容量或平台预算资料不足')
    else:
        total=sum(x.sku.specs.power_w*x.quantity for x in supplies)
        spare=max(x.sku.specs.power_w for x in supplies)
        if total<platform.power_budget_w:add('POWER','BLOCK','电源总容量不足示例预算')
        elif total-spare<platform.power_budget_w:add('POWER','WARN','总容量满足，但 N+1 可用容量不足示例预算')
        else:add('POWER','PASS','N+1 容量符合示例预算，仍需确认实际功耗与预留')
    add('COVERAGE','UNKNOWN','GPU 空间、PCIe/IB 槽位、磁盘背板、内存通道等尚无完整资料；未认证')
    if any(not x.required for x in lines):add('OPTIONAL','WARN','可选部件未计入必选组合校验，选用后须重新确认')
    return result


def bom_snapshot(db,body,*,validate=False):
    subject=sku(db,body.subject_sku_id)
    disabled=not subject.enabled
    if validate and not subject.enabled:raise Denied(422,'DISABLED_SKU')
    if validate and body.kind=='package' and subject.category!='host':raise Denied(422,'PACKAGE_REQUIRES_HOST')
    platform=rule(db,body.rule_id) if body.rule_id else None
    lines=[]
    def check_graph(id,ancestors,depth=0):
        if depth>16:raise Denied(422,'PACKAGE_DEPTH_LIMIT')
        package=row(db,'catalog_boms',id)
        if package['subject_sku_id'] in ancestors:raise Denied(422,'CYCLIC_PACKAGE')
        for child in db.execute(text('SELECT package_version_id,sku_id FROM catalog_bom_lines WHERE bom_id=:id'),{'id':id}).mappings():
            if child['sku_id'] in ancestors|{package['subject_sku_id']}:raise Denied(422,'CYCLIC_PACKAGE')
            if child['package_version_id']:check_graph(child['package_version_id'],ancestors|{package['subject_sku_id']},depth+1)
    for line in body.lines:
        if line.sku_id==subject.id:raise Denied(422,'CYCLIC_PACKAGE')
        part=sku(db,line.sku_id)
        disabled=disabled or not part.enabled
        if validate and not part.enabled:raise Denied(422,'DISABLED_SKU')
        if line.package_version_id:
            package=row(db,'catalog_boms',line.package_version_id)
            if package['state']!='published' or package['kind']!='package' or package['subject_sku_id']!=line.sku_id:raise Denied(422,'INVALID_PACKAGE_VERSION')
            check_graph(line.package_version_id,{subject.id})
            snap=BomSnapshot.model_validate(package['snapshot']);part=snap.subject
            if any(x.quantity*line.quantity>1000000 for x in snap.technical_lines):raise Denied(422,'PACKAGE_SIZE_LIMIT')
            lines.extend(TechnicalLine(sku=x.sku,quantity=x.quantity*line.quantity,required=x.required and line.required,charge_mode='included') for x in snap.technical_lines)
        lines.append(TechnicalLine(sku=part,quantity=line.quantity,required=line.required,charge_mode=line.charge_mode))
        if len(lines)>1000:raise Denied(422,'PACKAGE_SIZE_LIMIT')
    results=checks(lines,platform)
    if body.kind=='package' and subject.category!='host':results.append(Check(code='PACKAGE_REQUIRES_HOST',status='BLOCK',message='准系统主体已非主机类别；草稿可修复，发布前须更换主体或调整类别'))
    if disabled or any(not x.sku.enabled for x in lines):results.append(Check(code='DISABLED_SKU',status='BLOCK',message='包含已停用 SKU，发布前须调整'))
    return BomSnapshot(subject=subject,technical_lines=lines,rule=platform,checks=results)


def bom(db,id):
    item=row(db,'catalog_boms',id)
    lines=[dict(r) for r in db.execute(text('SELECT sku_id,package_version_id,quantity,required,charge_mode FROM catalog_bom_lines WHERE bom_id=:id ORDER BY position'),{'id':id}).mappings()]
    values={k:item[k] for k in ('id','family_id','revision','version','state','name','kind','subject_sku_id','rule_id')}
    from .models import BomInput
    body=BomInput(**{k:values[k] for k in BomInput.model_fields if k!='lines'},lines=lines)
    snapshot=BomSnapshot.model_validate(item['snapshot']) if item['state']=='published' else bom_snapshot(db,body)
    return Bom(**values,lines=lines,snapshot=snapshot)


def save_bom(db,access,body,id=None,family=None):
    if id:draft(row(db,'catalog_boms',id),body.expected_version)
    bom_snapshot(db,body)
    values=body.model_dump(exclude={'lines','expected_version'})
    if id:
        update(db,'catalog_boms',id,{**values,'version':body.expected_version+1})
        db.execute(text('DELETE FROM catalog_bom_lines WHERE bom_id=:id'),{'id':id})
    else:
        id=uuid4();family=family or id
        revision=db.scalar(text('SELECT COALESCE(max(revision),0)+1 FROM catalog_boms WHERE family_id=:id'),{'id':family})
        insert(db,'catalog_boms',dict(tenant_id=access.tenant_id,id=id,family_id=family,revision=revision,**values))
    for pos,line in enumerate(body.lines):insert(db,'catalog_bom_lines',dict(tenant_id=access.tenant_id,bom_id=id,position=pos,**line.model_dump()))
    return bom(db,id)


def publish_bom(db,id,version):
    draft(row(db,'catalog_boms',id),version)
    result=bom(db,id)
    bom_snapshot(db,result,validate=True)
    db.execute(text("UPDATE catalog_boms SET state='published',version=version+1,snapshot=CAST(:snapshot AS jsonb) WHERE id=:id"),{'id':id,'snapshot':result.snapshot.model_dump_json()})
    return bom(db,id)


def revise_bom(db,access,id,version):
    current=row(db,'catalog_boms',id);expected(current,version)
    if current['state']!='published':raise Denied(409,'PUBLISH_BEFORE_REVISION')
    from .models import BomInput
    source=bom(db,id)
    body=BomInput.model_validate(source.model_dump(include=set(BomInput.model_fields)))
    return save_bom(db,access,body,family=current['family_id'])


def price_book(db,id):
    item=row(db,'catalog_price_books',id)
    lines=list(db.execute(text('SELECT sku_id,amount FROM catalog_price_lines WHERE book_id=:id ORDER BY sku_id'),{'id':id}).mappings())
    issues=[]
    if item['state']=='draft':
        for line in lines:
            part=sku(db,line['sku_id'])
            if not part.enabled:issues.append(Check(code='DISABLED_SKU',status='BLOCK',message=f'{part.number} 已停用；草稿可替换或移除，发布前必须修复'))
    return PriceBook(**{k:item[k] for k in PriceBook.model_fields if k not in ('lines','checks')},lines=lines,checks=issues)


def save_price(db,access,body,id=None,family=None):
    if id:draft(row(db,'catalog_price_books',id),body.expected_version)
    for line in body.lines:
        sku(db,line.sku_id)  # Existence/tenant visibility always applies, even to repairable drafts.
    values=body.model_dump(exclude={'lines','expected_version'})
    if id:
        update(db,'catalog_price_books',id,{**values,'version':body.expected_version+1})
        db.execute(text('DELETE FROM catalog_price_lines WHERE book_id=:id'),{'id':id})
    else:
        id=uuid4();family=family or id
        revision=db.scalar(text('SELECT COALESCE(max(revision),0)+1 FROM catalog_price_books WHERE family_id=:id'),{'id':family})
        insert(db,'catalog_price_books',dict(tenant_id=access.tenant_id,id=id,family_id=family,revision=revision,**values))
    for line in body.lines:insert(db,'catalog_price_lines',dict(tenant_id=access.tenant_id,book_id=id,**line.model_dump()))
    return price_book(db,id)


def publish_price(db,id,version):
    current=row(db,'catalog_price_books',id);draft(current,version)
    if price_book(db,id).checks:raise Denied(422,'DISABLED_SKU')
    overlap=db.scalar(text('''SELECT 1 FROM catalog_price_books b JOIN catalog_price_lines p ON p.book_id=b.id
      WHERE b.state='published' AND b.scope=:scope AND b.tax_included=:tax_included AND b.currency=:currency
      AND b.valid_from<:valid_to AND b.valid_to>:valid_from
      AND p.sku_id IN (SELECT sku_id FROM catalog_price_lines WHERE book_id=:id) LIMIT 1'''),current)
    if overlap:raise Denied(409,'PRICE_OVERLAP')
    update(db,'catalog_price_books',id,{'state':'published','version':version+1})
    return price_book(db,id)


def revise_price(db,access,id,version):
    current=row(db,'catalog_price_books',id);expected(current,version)
    if current['state']!='published':raise Denied(409,'PUBLISH_BEFORE_REVISION')
    from .models import PriceInput
    source=price_book(db,id)
    return save_price(db,access,PriceInput.model_validate(source.model_dump(include=set(PriceInput.model_fields))),family=current['family_id'])


def current_price(db,id,scope,tax,at):
    sku(db,id)
    entries=list(db.execute(text('''SELECT b.*,p.amount FROM catalog_price_books b JOIN catalog_price_lines p ON p.book_id=b.id
      WHERE p.sku_id=:id AND b.state='published' AND b.scope=:scope AND b.tax_included=:tax
      ORDER BY b.valid_from DESC,b.id'''),dict(id=id,scope=scope,tax=tax)).mappings())
    active=next((r for r in entries if r['valid_from']<=at<r['valid_to']),None)
    expired=next((r for r in entries if r['valid_to']<=at),None)
    selected=active or expired or (entries[-1] if entries else None)
    result=dict(status='KNOWN' if active else 'EXPIRED' if expired else 'NOT_YET_VALID' if entries else 'UNKNOWN',amount=format(active['amount'],'.2f') if active else None,currency='CNY',scope=scope,tax_included=tax,as_of=at)
    if selected:result.update(book_id=selected['id'],revision=selected['revision'],source=selected['source'],valid_from=selected['valid_from'],valid_to=selected['valid_to'])
    return result
