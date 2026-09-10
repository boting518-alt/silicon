"""Explicit TASK-006 fictional seed for an isolated browser database only."""
from uuid import UUID
from sqlalchemy import text
from silicon.identity.access import tenant_transaction
from silicon.catalog import service as c
from silicon.catalog.models import BomInput
from silicon.quotes import service as q
from silicon.quotes.models import QuoteInput

APPROVER=UUID('22222222-2222-4222-8222-222222222222')
def seed(engine,migration,actor,tenant,issuer):
    with migration.begin() as db:
        db.execute(text("INSERT INTO identity_users(id,issuer,subject,display_name) VALUES (:id,:issuer,:subject,'虚构审批人乙')"),{'id':APPROVER,'issuer':issuer,'subject':str(APPROVER)})
        db.execute(text("INSERT INTO memberships VALUES (:t,:u,'admin',true)"),{'t':tenant,'u':APPROVER})
    with tenant_transaction(migration,actor,tenant,'quote.issue','publication-fixture') as (db,a):
        q.guard(db,a,True)
        db.execute(text("INSERT INTO publication_policies VALUES (:t,:id,1,true,'development',true,'虚构开发审批责任；不用于真实商务','unlimited')"),{'t':tenant,'id':UUID('66666666-6666-4666-8666-666666666666')})
    with tenant_transaction(engine,actor,tenant,'catalog.write','publication-fixture') as (db,a):
        c.guard(db,a,True)
        skus={r['number']:r['id'] for r in db.execute(text('SELECT number,id FROM catalog_skus')).mappings()}
        rule=db.scalar(text('SELECT id FROM catalog_rules ORDER BY id LIMIT 1'))
        bom=c.save_bom(db,a,BomInput(name='虚构审批验收 BOM',kind='bom',subject_sku_id=skus['DEMO-BARE'],rule_id=rule,lines=[
            dict(sku_id=skus[n],quantity=2 if n=='DEMO-PSU' else 1,required=n!='DEMO-GPU',charge_mode='included' if n=='DEMO-PSU' else 'separate')
            for n in ('DEMO-CPU','DEMO-RAM','DEMO-PSU','DEMO-SSD','DEMO-GPU')]))
        bom=c.publish_bom(db,bom.id,bom.version)
    with tenant_transaction(engine,actor,tenant,'quote.write','publication-fixture') as (db,a):
        q.guard(db,a,True)
        customer=db.scalar(text("SELECT id FROM crm_customers WHERE number='CUS-001'"))
        project=db.scalar(text('SELECT id FROM crm_projects WHERE customer_id=:id'),{'id':customer})
        q.save(db,a,QuoteInput(name='虚构 TASK-006 发布验收',customer_id=customer,project_id=project,bom_id=bom.id,quantity=1),'publication-seed','publication-fixture')
