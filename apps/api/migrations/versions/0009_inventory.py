"""Procurement and immutable stock facts; projection is transaction maintained."""
from alembic import op
revision='0009_inventory'
down_revision='0008_contracts'
branch_labels=depends_on=None
TABLES=['inv_suppliers','inv_commands','inv_tracking','inv_contracts','inv_contract_lines','inv_orders','inv_order_lines','inv_cancellations','inv_locations','inv_receipts','inv_receipt_lines','inv_movements','inv_layers','inv_units','inv_lots','inv_entries','inv_balances','inv_opening_policy','inv_imports','inv_import_rows','inv_attachments','inv_amendments']
def upgrade():
    op.execute('''
    INSERT INTO permissions VALUES ('purchase.read'),('purchase.write'),('purchase.activate'),('inventory.read'),('inventory.receive'),('inventory.inspect'),('inventory.move'),('inventory.reverse'),('inventory.opening'),('inventory.cost'),('inventory.configure'),('inventory.download');
    INSERT INTO role_permissions SELECT 'admin',name FROM permissions WHERE name LIKE 'purchase.%' OR name LIKE 'inventory.%' ON CONFLICT DO NOTHING;
    INSERT INTO role_permissions SELECT 'member',name FROM permissions WHERE name IN ('inventory.read','inventory.receive','inventory.inspect','inventory.move','inventory.download');
    INSERT INTO role_permissions VALUES ('viewer','inventory.read');
    CREATE TABLE inv_suppliers(tenant_id uuid REFERENCES tenants,id uuid,name text NOT NULL CHECK(length(btrim(name))>0),address text NOT NULL,contact text NOT NULL,phone text NOT NULL,enabled boolean NOT NULL,version int NOT NULL CHECK(version>0),PRIMARY KEY(tenant_id,id));
    CREATE TABLE inv_commands(tenant_id uuid REFERENCES tenants,actor_id uuid,operation text,key text,request_hash text NOT NULL,response jsonb NOT NULL,PRIMARY KEY(tenant_id,actor_id,operation,key),FOREIGN KEY(tenant_id,actor_id) REFERENCES memberships(tenant_id,user_id));
    ''')
    op.execute("""
    CREATE TABLE inv_tracking(tenant_id uuid,id uuid,mode text NOT NULL CHECK(mode IN ('sn','batch')),unit text NOT NULL CHECK(unit='piece'),version int NOT NULL,PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,id) REFERENCES catalog_skus(tenant_id,id));
    CREATE TABLE inv_contracts(tenant_id uuid,id uuid,number text NOT NULL,supplier_id uuid NOT NULL,buyer text NOT NULL,manager_id uuid NOT NULL,signing_date date NOT NULL,currency text NOT NULL CHECK(currency='CNY'),notes text NOT NULL,state text NOT NULL CHECK(state IN ('draft','active')),version int NOT NULL,snapshot jsonb,
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,number),FOREIGN KEY(tenant_id,supplier_id) REFERENCES inv_suppliers(tenant_id,id),FOREIGN KEY(tenant_id,manager_id) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE inv_contract_lines(tenant_id uuid,id uuid,contract_id uuid NOT NULL,sku_id uuid NOT NULL,quantity int NOT NULL CHECK(quantity>0),unit_price numeric(18,2) NOT NULL CHECK(unit_price>=0),tax_basis text NOT NULL CHECK(tax_basis IN ('included','excluded','unconfirmed')),due_date date NOT NULL,
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,contract_id,sku_id),FOREIGN KEY(tenant_id,contract_id) REFERENCES inv_contracts(tenant_id,id),FOREIGN KEY(tenant_id,sku_id) REFERENCES catalog_skus(tenant_id,id));
    CREATE TABLE inv_orders(tenant_id uuid,id uuid,number text NOT NULL,contract_id uuid NOT NULL,supplier_confirmation text NOT NULL,state text NOT NULL CHECK(state IN ('draft','confirmed')),version int NOT NULL,PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,number),FOREIGN KEY(tenant_id,contract_id) REFERENCES inv_contracts(tenant_id,id));
    CREATE TABLE inv_order_lines(tenant_id uuid,id uuid,order_id uuid NOT NULL,contract_line_id uuid NOT NULL,quantity int NOT NULL CHECK(quantity>0),sales_order_id uuid,project_id uuid,
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,order_id,contract_line_id),FOREIGN KEY(tenant_id,order_id) REFERENCES inv_orders(tenant_id,id),FOREIGN KEY(tenant_id,contract_line_id) REFERENCES inv_contract_lines(tenant_id,id),FOREIGN KEY(tenant_id,sales_order_id) REFERENCES sales_orders(tenant_id,id),FOREIGN KEY(tenant_id,project_id) REFERENCES crm_projects(tenant_id,id));
    CREATE TABLE inv_cancellations(tenant_id uuid,id uuid,line_id uuid NOT NULL,quantity int NOT NULL CHECK(quantity>0),reason text NOT NULL,actor_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,line_id) REFERENCES inv_order_lines(tenant_id,id));
    CREATE FUNCTION inv_frozen() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_TABLE_NAME='inv_contracts' AND OLD.state='active' THEN RAISE EXCEPTION 'frozen contract' USING ERRCODE='23514'; END IF;
      IF TG_TABLE_NAME='inv_contract_lines' THEN IF EXISTS(SELECT 1 FROM inv_contracts WHERE tenant_id=OLD.tenant_id AND id=OLD.contract_id AND state='active') THEN RAISE EXCEPTION 'frozen line' USING ERRCODE='23514'; END IF; END IF;
      IF TG_TABLE_NAME='inv_orders' AND OLD.state='confirmed' AND (to_jsonb(NEW)-'version')<>(to_jsonb(OLD)-'version') THEN RAISE EXCEPTION 'frozen order' USING ERRCODE='23514'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$;
    CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON inv_contracts FOR EACH ROW EXECUTE FUNCTION inv_frozen();
    CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON inv_contract_lines FOR EACH ROW EXECUTE FUNCTION inv_frozen();
    CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON inv_orders FOR EACH ROW EXECUTE FUNCTION inv_frozen();
    GRANT UPDATE ON inv_tracking,inv_contracts,inv_orders TO silicon_app;
    GRANT DELETE ON inv_contract_lines TO silicon_app;
    """)
    op.execute("""
    CREATE TABLE inv_locations(tenant_id uuid REFERENCES tenants,id uuid,warehouse text NOT NULL,name text NOT NULL,PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,warehouse,name));
    CREATE TABLE inv_receipts(tenant_id uuid,id uuid,order_id uuid NOT NULL,location_id uuid NOT NULL,received_on date NOT NULL,state text NOT NULL CHECK(state IN ('draft','posted')),version int NOT NULL,PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,order_id) REFERENCES inv_orders(tenant_id,id),FOREIGN KEY(tenant_id,location_id) REFERENCES inv_locations(tenant_id,id));
    CREATE TABLE inv_receipt_lines(tenant_id uuid,id uuid,receipt_id uuid NOT NULL,order_line_id uuid NOT NULL,quantity int NOT NULL CHECK(quantity>0),serials jsonb NOT NULL,batch text NOT NULL,cost_status text NOT NULL CHECK(cost_status IN ('unknown','provisional','confirmed')),unit_cost numeric(18,2) CHECK(unit_cost>=0),deductible_tax numeric(18,2) CHECK(deductible_tax>=0),cost_basis text NOT NULL,
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,receipt_id,order_line_id),FOREIGN KEY(tenant_id,receipt_id) REFERENCES inv_receipts(tenant_id,id),FOREIGN KEY(tenant_id,order_line_id) REFERENCES inv_order_lines(tenant_id,id),CHECK((cost_status='unknown')=(unit_cost IS NULL)));
    CREATE TABLE inv_movements(tenant_id uuid REFERENCES tenants,id uuid,kind text NOT NULL CHECK(kind IN ('receipt','opening','inspection','transfer','reverse')),receipt_id uuid,reverse_of uuid,reason text NOT NULL,actor_id uuid NOT NULL,request_id text NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),effective_on date NOT NULL,
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,receipt_id),UNIQUE(tenant_id,reverse_of),FOREIGN KEY(tenant_id,receipt_id) REFERENCES inv_receipts(tenant_id,id),FOREIGN KEY(tenant_id,reverse_of) REFERENCES inv_movements(tenant_id,id));
    CREATE TABLE inv_layers(tenant_id uuid,id uuid,sku_id uuid NOT NULL,source_movement uuid NOT NULL,source_line uuid,quantity int NOT NULL CHECK(quantity>0),ownership text NOT NULL CHECK(ownership IN ('own','customer')),cost_status text NOT NULL CHECK(cost_status IN ('unknown','provisional','confirmed')),unit_cost numeric(18,2) CHECK(unit_cost>=0),deductible_tax numeric(18,2),cost_basis text NOT NULL,currency text NOT NULL CHECK(currency='CNY'),tax_basis text NOT NULL,version int NOT NULL DEFAULT 1,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,sku_id) REFERENCES inv_tracking(tenant_id,id),FOREIGN KEY(tenant_id,source_movement) REFERENCES inv_movements(tenant_id,id),FOREIGN KEY(tenant_id,source_line) REFERENCES inv_receipt_lines(tenant_id,id),CHECK((cost_status='unknown')=(unit_cost IS NULL)));
    CREATE TABLE inv_units(tenant_id uuid,id uuid,sku_id uuid NOT NULL,manufacturer_id uuid NOT NULL,serial_raw text NOT NULL,serial_normal text NOT NULL,PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,manufacturer_id,sku_id,serial_normal),FOREIGN KEY(tenant_id,sku_id) REFERENCES catalog_skus(tenant_id,id),FOREIGN KEY(tenant_id,manufacturer_id) REFERENCES catalog_manufacturers(tenant_id,id));
    ALTER TABLE inv_layers ADD COLUMN unit_id uuid; ALTER TABLE inv_layers ADD FOREIGN KEY(tenant_id,unit_id) REFERENCES inv_units(tenant_id,id);
    CREATE TABLE inv_lots(tenant_id uuid,id uuid,layer_id uuid NOT NULL,batch text NOT NULL,PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,layer_id),FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id));
    CREATE TABLE inv_entries(tenant_id uuid,id uuid,movement_id uuid NOT NULL,layer_id uuid NOT NULL,location_id uuid NOT NULL,state text NOT NULL CHECK(state IN ('pending','qualified','quarantine')),quantity int NOT NULL CHECK(quantity<>0),PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,movement_id,layer_id,location_id,state),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id),FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id),FOREIGN KEY(tenant_id,location_id) REFERENCES inv_locations(tenant_id,id));
    CREATE TABLE inv_balances(tenant_id uuid,layer_id uuid,location_id uuid,state text CHECK(state IN ('pending','qualified','quarantine')),quantity int NOT NULL CHECK(quantity>=0),PRIMARY KEY(tenant_id,layer_id,location_id,state),FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id),FOREIGN KEY(tenant_id,location_id) REFERENCES inv_locations(tenant_id,id));
    CREATE FUNCTION inv_receipt_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.state='posted' THEN RAISE EXCEPTION 'posted receipt' USING ERRCODE='23514'; END IF;RETURN NEW;END $$;
    CREATE TRIGGER immutable_posted BEFORE UPDATE OR DELETE ON inv_receipts FOR EACH ROW EXECUTE FUNCTION inv_receipt_guard();
    CREATE FUNCTION inv_layer_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' OR (to_jsonb(NEW)-'version')<>(to_jsonb(OLD)-'version') THEN RAISE EXCEPTION 'immutable cost layer' USING ERRCODE='23514'; END IF;RETURN NEW;END $$;
    CREATE TRIGGER immutable_cost BEFORE UPDATE OR DELETE ON inv_layers FOR EACH ROW EXECUTE FUNCTION inv_layer_guard();
    GRANT UPDATE ON inv_receipts,inv_layers,inv_balances TO silicon_app;
    """)
    for t in ['inv_receipt_lines','inv_movements','inv_units','inv_lots','inv_entries']:op.execute(f'CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION publication_immutable()')
    op.execute("""
    CREATE TABLE inv_opening_policy(tenant_id uuid PRIMARY KEY REFERENCES tenants,cutoff date NOT NULL,opened boolean NOT NULL,version int NOT NULL,reason text NOT NULL);
    CREATE TABLE inv_imports(tenant_id uuid REFERENCES tenants,id uuid,content_hash text NOT NULL,storage_id uuid NOT NULL UNIQUE,name text NOT NULL,media_type text NOT NULL,size bigint NOT NULL,sha256 text NOT NULL,validation jsonb NOT NULL,state text NOT NULL CHECK(state IN ('preview','posted')),version int NOT NULL,movement_id uuid,actor_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,content_hash),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id));
    CREATE TABLE inv_import_rows(tenant_id uuid,id uuid,import_id uuid NOT NULL,external_id text NOT NULL,layer_id uuid NOT NULL,PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,external_id),FOREIGN KEY(tenant_id,import_id) REFERENCES inv_imports(tenant_id,id),FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id));
    CREATE TABLE inv_attachments(tenant_id uuid,id uuid,contract_id uuid,receipt_id uuid,storage_id uuid NOT NULL UNIQUE,name text NOT NULL,media_type text NOT NULL,size bigint NOT NULL,sha256 text NOT NULL,actor_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,id),CHECK((contract_id IS NULL)<>(receipt_id IS NULL)),FOREIGN KEY(tenant_id,contract_id) REFERENCES inv_contracts(tenant_id,id),FOREIGN KEY(tenant_id,receipt_id) REFERENCES inv_receipts(tenant_id,id));
    CREATE TABLE inv_amendments(tenant_id uuid,id uuid,contract_id uuid NOT NULL,line_id uuid NOT NULL,extra_quantity int NOT NULL CHECK(extra_quantity>0),reason text NOT NULL,actor_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,contract_id) REFERENCES inv_contracts(tenant_id,id),FOREIGN KEY(tenant_id,line_id) REFERENCES inv_contract_lines(tenant_id,id));
    GRANT UPDATE ON inv_opening_policy,inv_imports TO silicon_app;
    CREATE FUNCTION inv_import_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.state='posted' OR TG_OP='DELETE' THEN RAISE EXCEPTION 'frozen import' USING ERRCODE='23514'; END IF;RETURN NEW;END $$;
    CREATE TRIGGER immutable_import BEFORE UPDATE OR DELETE ON inv_imports FOR EACH ROW EXECUTE FUNCTION inv_import_guard();
    """)
    for t in ['inv_import_rows','inv_attachments','inv_amendments']:op.execute(f'CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION publication_immutable()')
    for t in TABLES:
        op.execute(f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY; ALTER TABLE {t} FORCE ROW LEVEL SECURITY; CREATE POLICY tenant_isolation ON {t} USING(tenant_visible(tenant_id)) WITH CHECK(tenant_visible(tenant_id)); GRANT SELECT,INSERT ON {t} TO silicon_app')
    op.execute('GRANT UPDATE ON inv_suppliers TO silicon_app')
    for t in ['inv_commands','inv_order_lines','inv_cancellations']:op.execute(f'CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION publication_immutable()')
def downgrade():
    op.execute("ALTER TABLE inv_layers DROP CONSTRAINT inv_layers_tenant_id_unit_id_fkey")
    for t in reversed(TABLES):op.execute(f'DROP TABLE {t}')
    op.execute('DROP FUNCTION inv_frozen(); DROP FUNCTION inv_receipt_guard(); DROP FUNCTION inv_layer_guard(); DROP FUNCTION inv_import_guard()')
    op.execute("DELETE FROM role_permissions WHERE permission LIKE 'purchase.%' OR permission LIKE 'inventory.%'; DELETE FROM permissions WHERE name LIKE 'purchase.%' OR name LIKE 'inventory.%'")
