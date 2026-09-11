"""After-sales custody and shared stock/installation facts; no sales return implied."""
from alembic import op
revision='0015_service'
down_revision='0014_finance_corrections'
branch_labels=depends_on=None
TABLES=['svc_works','svc_events','svc_receipts','svc_returns','svc_tests','svc_reservations','svc_issues','svc_spare_returns','svc_changes','svc_old_parts','svc_change_reversals','svc_rmas','svc_rma_lines','svc_rma_returns','svc_rma_inspections','svc_costs','svc_charges','svc_dispositions']
PERMISSIONS=['service.read','service.manage','service.diagnose','service.custody','service.spares','service.replace','service.rma','service.fee','service.correct','service.cost']
COMMON='tenant_id uuid NOT NULL,id uuid NOT NULL,PRIMARY KEY(tenant_id,id),created_at timestamptz NOT NULL DEFAULT clock_timestamp()'
WORK='work_id uuid NOT NULL,FOREIGN KEY(tenant_id,work_id) REFERENCES svc_works(tenant_id,id)'
ACTOR='actor_id uuid NOT NULL REFERENCES identity_users(id),reason text NOT NULL'
def upgrade():
    for p in PERMISSIONS:op.execute(f"INSERT INTO permissions VALUES('{p}');INSERT INTO role_permissions VALUES('admin','{p}')")
    op.execute(f"""CREATE TABLE svc_works({COMMON},number text NOT NULL,device_id uuid NOT NULL,line_id uuid NOT NULL,manager_id uuid NOT NULL,
    parts_location_id uuid NOT NULL,FOREIGN KEY(tenant_id,parts_location_id) REFERENCES inv_locations(tenant_id,id),fault text NOT NULL,reported_at timestamptz NOT NULL,contact text NOT NULL,mode text NOT NULL CHECK(mode IN('remote','onsite','return')),priority text NOT NULL,
    planned_on date NOT NULL,state text NOT NULL DEFAULT 'new' CHECK(state IN('new','working','waiting','verify','resolved','closed','cancelled')),
    version int NOT NULL DEFAULT 1,config_version int NOT NULL DEFAULT 1,diagnosis text NOT NULL DEFAULT '',solution text NOT NULL DEFAULT '',warranty text NOT NULL DEFAULT 'pending',warranty_basis text NOT NULL DEFAULT '',customer_confirmation text NOT NULL DEFAULT '',
    UNIQUE(tenant_id,number),FOREIGN KEY(tenant_id,device_id) REFERENCES asm_devices(tenant_id,id),FOREIGN KEY(tenant_id,line_id) REFERENCES del_lines(tenant_id,id),FOREIGN KEY(tenant_id,manager_id) REFERENCES memberships(tenant_id,user_id));
    CREATE UNIQUE INDEX svc_live_device ON svc_works(tenant_id,device_id) WHERE state NOT IN('closed','cancelled');
    CREATE TABLE svc_events({COMMON},{WORK},{ACTOR},action text NOT NULL,details jsonb NOT NULL DEFAULT '{{}}');
    CREATE TABLE svc_receipts({COMMON},{WORK},{ACTOR},location_id uuid NOT NULL,performed_at timestamptz NOT NULL,appearance text NOT NULL,accessories text NOT NULL,FOREIGN KEY(tenant_id,location_id) REFERENCES inv_locations(tenant_id,id));
    CREATE TABLE svc_returns({COMMON},{WORK},{ACTOR},receipt_id uuid NOT NULL,performed_at timestamptz NOT NULL,customer_confirmation text NOT NULL,UNIQUE(tenant_id,receipt_id),FOREIGN KEY(tenant_id,receipt_id) REFERENCES svc_receipts(tenant_id,id));
    CREATE TABLE svc_tests({COMMON},{WORK},{ACTOR},config_version int NOT NULL,result text NOT NULL CHECK(result IN('pass','fail')),performed_at timestamptz NOT NULL,items jsonb NOT NULL,report_ref text NOT NULL);
    CREATE TABLE svc_reservations({COMMON},{WORK},layer_id uuid NOT NULL,location_id uuid NOT NULL,quantity int NOT NULL CHECK(quantity>0),consumed int NOT NULL DEFAULT 0 CHECK(consumed>=0),released int NOT NULL DEFAULT 0 CHECK(released>=0),expires_at timestamptz NOT NULL,CHECK(consumed+released<=quantity),FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id),FOREIGN KEY(tenant_id,location_id) REFERENCES inv_locations(tenant_id,id));
    CREATE TABLE svc_issues({COMMON},{WORK},{ACTOR},reservation_id uuid NOT NULL,layer_id uuid NOT NULL,location_id uuid NOT NULL,quantity int NOT NULL CHECK(quantity>0),movement_id uuid NOT NULL,FOREIGN KEY(tenant_id,reservation_id) REFERENCES svc_reservations(tenant_id,id),FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id),FOREIGN KEY(tenant_id,location_id) REFERENCES inv_locations(tenant_id,id),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id));
    CREATE TABLE svc_spare_returns({COMMON},{WORK},{ACTOR},issue_id uuid NOT NULL,quantity int NOT NULL CHECK(quantity>0),movement_id uuid NOT NULL,FOREIGN KEY(tenant_id,issue_id) REFERENCES svc_issues(tenant_id,id),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id));
    CREATE TABLE svc_changes({COMMON},{WORK},{ACTOR},old_installation_id uuid NOT NULL,new_installation_id uuid NOT NULL,issue_id uuid NOT NULL,movement_id uuid NOT NULL,compatibility_basis text NOT NULL,
    FOREIGN KEY(tenant_id,old_installation_id) REFERENCES asm_installations(tenant_id,id),FOREIGN KEY(tenant_id,new_installation_id) REFERENCES asm_installations(tenant_id,id),FOREIGN KEY(tenant_id,issue_id) REFERENCES svc_issues(tenant_id,id),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id));
    CREATE TABLE svc_old_parts({COMMON},{WORK},change_id uuid NOT NULL,layer_id uuid,original_layer_id uuid NOT NULL,unit_id uuid,quantity int NOT NULL CHECK(quantity>0),destination text NOT NULL CHECK(destination IN('customer','quarantine','dispose')),owner text NOT NULL DEFAULT 'customer' CHECK(owner='customer'),responsible_id uuid NOT NULL,
    UNIQUE(tenant_id,change_id),FOREIGN KEY(tenant_id,change_id) REFERENCES svc_changes(tenant_id,id),FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id),FOREIGN KEY(tenant_id,original_layer_id) REFERENCES inv_layers(tenant_id,id),FOREIGN KEY(tenant_id,unit_id) REFERENCES inv_units(tenant_id,id),FOREIGN KEY(tenant_id,responsible_id) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE svc_change_reversals({COMMON},{WORK},{ACTOR},change_id uuid NOT NULL,movement_id uuid NOT NULL,restored_installation_id uuid NOT NULL,UNIQUE(tenant_id,change_id),FOREIGN KEY(tenant_id,change_id) REFERENCES svc_changes(tenant_id,id),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id),FOREIGN KEY(tenant_id,restored_installation_id) REFERENCES asm_installations(tenant_id,id));
    CREATE TABLE svc_rmas({COMMON},{WORK},number text NOT NULL,supplier_id uuid NOT NULL,manager_id uuid NOT NULL,supplier_number text NOT NULL,fault text NOT NULL,expected_on date NOT NULL,authorization_basis text NOT NULL,state text NOT NULL DEFAULT 'draft',version int NOT NULL DEFAULT 1,UNIQUE(tenant_id,number),FOREIGN KEY(tenant_id,supplier_id) REFERENCES inv_suppliers(tenant_id,id),FOREIGN KEY(tenant_id,manager_id) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE svc_rma_lines({COMMON},rma_id uuid NOT NULL,old_part_id uuid NOT NULL,quantity int NOT NULL CHECK(quantity>0),FOREIGN KEY(tenant_id,rma_id) REFERENCES svc_rmas(tenant_id,id),FOREIGN KEY(tenant_id,old_part_id) REFERENCES svc_old_parts(tenant_id,id),UNIQUE(tenant_id,old_part_id));
    CREATE TABLE svc_rma_returns({COMMON},{ACTOR},line_id uuid NOT NULL,quantity int NOT NULL CHECK(quantity>0),kind text NOT NULL CHECK(kind IN('repair','replacement')),layer_id uuid NOT NULL,movement_id uuid NOT NULL,performed_at timestamptz NOT NULL,result text NOT NULL,FOREIGN KEY(tenant_id,line_id) REFERENCES svc_rma_lines(tenant_id,id),FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id));
    CREATE TABLE svc_rma_inspections({COMMON},{ACTOR},return_id uuid NOT NULL,passed bool NOT NULL,disposition text NOT NULL,ownership_basis text NOT NULL,new_layer_id uuid,movement_id uuid NOT NULL,UNIQUE(tenant_id,return_id),FOREIGN KEY(tenant_id,return_id) REFERENCES svc_rma_returns(tenant_id,id),FOREIGN KEY(tenant_id,new_layer_id) REFERENCES inv_layers(tenant_id,id),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id));
    CREATE TABLE svc_costs({COMMON},{WORK},{ACTOR},kind text NOT NULL CHECK(kind IN('labor','other')),person_id uuid,hours numeric(10,2),amount numeric(18,2) NOT NULL CHECK(amount>=0),basis text NOT NULL,occurred_on date NOT NULL,FOREIGN KEY(tenant_id,person_id) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE svc_charges({COMMON},{WORK},{ACTOR},rma_id uuid,kind text NOT NULL CHECK(kind IN('customer_service','supplier_repair')),direction text NOT NULL CHECK(direction IN('receivable','payable')),customer_id uuid,supplier_id uuid,amount numeric(18,2) NOT NULL CHECK(amount>0),basis_ref text NOT NULL,number text NOT NULL,UNIQUE(tenant_id,work_id,kind,basis_ref),
    FOREIGN KEY(tenant_id,rma_id) REFERENCES svc_rmas(tenant_id,id),FOREIGN KEY(tenant_id,customer_id) REFERENCES crm_customers(tenant_id,id),FOREIGN KEY(tenant_id,supplier_id) REFERENCES inv_suppliers(tenant_id,id),CHECK((kind='customer_service' AND direction='receivable' AND customer_id IS NOT NULL AND supplier_id IS NULL AND rma_id IS NULL) OR (kind='supplier_repair' AND direction='payable' AND supplier_id IS NOT NULL AND customer_id IS NULL AND rma_id IS NOT NULL)));
    """)
    op.execute(f"""CREATE TABLE svc_dispositions({COMMON},{WORK},{ACTOR},old_part_id uuid,return_id uuid,disposition text NOT NULL CHECK(disposition IN('customer','scrap')),basis text NOT NULL,movement_id uuid NOT NULL,CHECK((old_part_id IS NULL)<>(return_id IS NULL)),UNIQUE(tenant_id,old_part_id),UNIQUE(tenant_id,return_id),FOREIGN KEY(tenant_id,old_part_id) REFERENCES svc_old_parts(tenant_id,id),FOREIGN KEY(tenant_id,return_id) REFERENCES svc_rma_returns(tenant_id,id),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id));""")
    for t in TABLES:
        op.execute(f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;ALTER TABLE {t} FORCE ROW LEVEL SECURITY;CREATE POLICY tenant_isolation ON {t} USING(tenant_visible(tenant_id)) WITH CHECK(tenant_visible(tenant_id));GRANT SELECT,INSERT ON {t} TO silicon_app')
        if t in ('svc_works','svc_reservations','svc_rmas'):op.execute(f'GRANT UPDATE ON {t} TO silicon_app')
        else:op.execute(f'CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION publication_immutable()')
    op.execute("""CREATE FUNCTION service_mutation_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
    IF TG_TABLE_NAME='svc_works' THEN
      IF (to_jsonb(NEW)-ARRAY['version','config_version','state','manager_id','diagnosis','solution','warranty','warranty_basis','customer_confirmation']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['version','config_version','state','manager_id','diagnosis','solution','warranty','warranty_basis','customer_confirmation']) THEN RAISE EXCEPTION 'immutable service source';END IF;
    ELSIF TG_TABLE_NAME='svc_rmas' THEN
      IF (to_jsonb(NEW)-ARRAY['version','state']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['version','state']) THEN RAISE EXCEPTION 'immutable RMA source';END IF;
    ELSIF (to_jsonb(NEW)-ARRAY['consumed','released']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['consumed','released']) OR NEW.consumed<OLD.consumed OR NEW.released<OLD.released THEN RAISE EXCEPTION 'immutable reservation source';
    END IF;RETURN NEW;END $$;
    CREATE TRIGGER source_guard BEFORE UPDATE ON svc_works FOR EACH ROW EXECUTE FUNCTION service_mutation_guard();
    CREATE TRIGGER source_guard BEFORE UPDATE ON svc_rmas FOR EACH ROW EXECUTE FUNCTION service_mutation_guard();
    CREATE TRIGGER source_guard BEFORE UPDATE ON svc_reservations FOR EACH ROW EXECUTE FUNCTION service_mutation_guard();""")
    op.execute("""ALTER TABLE asm_installations ADD COLUMN slot_id uuid NOT NULL DEFAULT gen_random_uuid();
    ALTER TABLE asm_installations ADD COLUMN service_work_id uuid;
    ALTER TABLE asm_installations ADD FOREIGN KEY(tenant_id,service_work_id) REFERENCES svc_works(tenant_id,id);
    CREATE UNIQUE INDEX svc_active_slot ON asm_installations(tenant_id,device_id,slot_id) WHERE removed_at IS NULL;
    ALTER TABLE inv_movements DROP CONSTRAINT inv_movements_kind_check;
    ALTER TABLE inv_movements ADD CHECK(kind IN('receipt','opening','inspection','transfer','reverse','assembly_issue','assembly_complete','delivery_ship','delivery_return','delivery_reverse','service_issue','service_return','service_replace','service_reverse','service_rma_send','service_rma_return','service_rma_inspect'));
    """)
    for t in ('inv_entries','inv_balances'):
        op.execute(f"ALTER TABLE {t} DROP CONSTRAINT {t}_state_check;ALTER TABLE {t} ADD CHECK(state IN('pending','qualified','quarantine','wip','service_issued','supplier'))")
    for t in ('fin_plans','fin_invoice_lines','fin_source_adjustments'):
        # Source relation check is an unnamed constraint in 0013; identify by referenced column.
        op.execute(f"""DO $$ DECLARE c record;BEGIN FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='{t}'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%sales_contract_id%' LOOP EXECUTE format('ALTER TABLE {t} DROP CONSTRAINT %I',c.conname);END LOOP;END $$;
        ALTER TABLE {t} ADD COLUMN service_source_id uuid;
        ALTER TABLE {t} ADD FOREIGN KEY(tenant_id,service_source_id) REFERENCES svc_charges(tenant_id,id);
        ALTER TABLE {t} ALTER COLUMN source_id SET EXPRESSION AS (coalesce(sales_contract_id,purchase_contract_id,service_source_id));
        ALTER TABLE {t} ADD CONSTRAINT {t}_source_kind CHECK((service_source_id IS NOT NULL AND sales_contract_id IS NULL AND purchase_contract_id IS NULL) OR (service_source_id IS NULL AND ((direction='receivable' AND sales_contract_id IS NOT NULL AND purchase_contract_id IS NULL) OR (direction='payable' AND purchase_contract_id IS NOT NULL AND sales_contract_id IS NULL))));""")
def downgrade():
    for t in TABLES:op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY;DO $$ BEGIN IF EXISTS(SELECT 1 FROM {t}) THEN RAISE EXCEPTION 'service history prevents downgrade';END IF;END $$")
    for t in ('fin_plans','fin_invoice_lines','fin_source_adjustments'):
        op.execute(f"ALTER TABLE {t} ALTER COLUMN source_id SET EXPRESSION AS (coalesce(sales_contract_id,purchase_contract_id));ALTER TABLE {t} DROP CONSTRAINT {t}_source_kind;ALTER TABLE {t} DROP COLUMN service_source_id;ALTER TABLE {t} ADD CHECK((direction='receivable' AND sales_contract_id IS NOT NULL AND purchase_contract_id IS NULL) OR (direction='payable' AND purchase_contract_id IS NOT NULL AND sales_contract_id IS NULL))")
    op.execute('DROP INDEX svc_active_slot;ALTER TABLE asm_installations DROP COLUMN service_work_id;ALTER TABLE asm_installations DROP COLUMN slot_id')
    op.execute("ALTER TABLE inv_movements DROP CONSTRAINT inv_movements_kind_check;ALTER TABLE inv_movements ADD CHECK(kind IN('receipt','opening','inspection','transfer','reverse','assembly_issue','assembly_complete','delivery_ship','delivery_return','delivery_reverse'))")
    for t in ('inv_entries','inv_balances'):op.execute(f"ALTER TABLE {t} DROP CONSTRAINT {t}_state_check;ALTER TABLE {t} ADD CHECK(state IN('pending','qualified','quarantine','wip'))")
    for t in reversed(TABLES):op.execute(f'DROP TABLE {t}')
    op.execute('DROP FUNCTION service_mutation_guard()')
    for p in PERMISSIONS:op.execute(f"DELETE FROM role_permissions WHERE permission='{p}';DELETE FROM permissions WHERE name='{p}'")
