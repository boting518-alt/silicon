"""Single-unit work orders mapped only from frozen sales configuration."""
from alembic import op
revision='0010_assembly'
down_revision='0009_inventory'
branch_labels=depends_on=None
TABLES=['asm_works','asm_requirements','asm_reservations','asm_events','asm_issues','asm_issue_lines','asm_devices','asm_installations']
def upgrade():
    op.execute("""
    INSERT INTO permissions VALUES ('assembly.read'),('assembly.write'),('assembly.reserve'),('assembly.release'),('assembly.issue'),('assembly.complete'),('assembly.reverse'),('device.read');
    INSERT INTO role_permissions SELECT 'admin',name FROM permissions WHERE name LIKE 'assembly.%' OR name='device.read';
    INSERT INTO role_permissions SELECT 'member',name FROM permissions WHERE name IN ('assembly.read','assembly.write','assembly.reserve','assembly.release','assembly.issue','assembly.complete','device.read');
    INSERT INTO role_permissions VALUES ('viewer','device.read');
    CREATE TABLE asm_works(tenant_id uuid,id uuid,order_id uuid NOT NULL,product_sku_id uuid NOT NULL,manager_id uuid NOT NULL,planned_on date NOT NULL,notes text NOT NULL,state text NOT NULL CHECK(state IN ('draft','ready','in_progress','completed','cancelled')),version int NOT NULL CHECK(version>0),mapping jsonb NOT NULL,wip_location_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,order_id) REFERENCES sales_orders(tenant_id,id),FOREIGN KEY(tenant_id,product_sku_id) REFERENCES catalog_skus(tenant_id,id),FOREIGN KEY(tenant_id,manager_id) REFERENCES memberships(tenant_id,user_id),FOREIGN KEY(tenant_id,wip_location_id) REFERENCES inv_locations(tenant_id,id));
    CREATE TABLE asm_requirements(tenant_id uuid,id uuid,work_id uuid NOT NULL,sku_id uuid NOT NULL,quantity int NOT NULL CHECK(quantity>0),position text NOT NULL,PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,work_id,sku_id),FOREIGN KEY(tenant_id,work_id) REFERENCES asm_works(tenant_id,id),FOREIGN KEY(tenant_id,sku_id) REFERENCES inv_tracking(tenant_id,id));
    GRANT UPDATE ON asm_works TO silicon_app;
    CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON asm_requirements FOR EACH ROW EXECUTE FUNCTION publication_immutable();
    """)
    op.execute("""
    CREATE TABLE asm_reservations(tenant_id uuid,id uuid,work_id uuid NOT NULL,requirement_id uuid NOT NULL,layer_id uuid NOT NULL,location_id uuid NOT NULL,quantity int NOT NULL CHECK(quantity>0),consumed int NOT NULL DEFAULT 0 CHECK(consumed>=0),released int NOT NULL DEFAULT 0 CHECK(released>=0),expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,id),CHECK(consumed+released<=quantity),FOREIGN KEY(tenant_id,work_id) REFERENCES asm_works(tenant_id,id),FOREIGN KEY(tenant_id,requirement_id) REFERENCES asm_requirements(tenant_id,id),FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id),FOREIGN KEY(tenant_id,location_id) REFERENCES inv_locations(tenant_id,id));
    CREATE TABLE asm_events(tenant_id uuid,id uuid,work_id uuid NOT NULL,action text NOT NULL,reason text NOT NULL,actor_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,work_id) REFERENCES asm_works(tenant_id,id));
    CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON asm_events FOR EACH ROW EXECUTE FUNCTION publication_immutable();
    GRANT UPDATE ON asm_reservations TO silicon_app;
    """)
    op.execute("""
    ALTER TABLE inv_movements DROP CONSTRAINT inv_movements_kind_check;
    ALTER TABLE inv_movements ADD CHECK(kind IN ('receipt','opening','inspection','transfer','reverse','assembly_issue','assembly_complete'));
    ALTER TABLE inv_entries DROP CONSTRAINT inv_entries_state_check;
    ALTER TABLE inv_entries ADD CHECK(state IN ('pending','qualified','quarantine','wip'));
    ALTER TABLE inv_balances DROP CONSTRAINT inv_balances_state_check;
    ALTER TABLE inv_balances ADD CHECK(state IN ('pending','qualified','quarantine','wip'));
    CREATE TABLE asm_issues(tenant_id uuid,id uuid,work_id uuid NOT NULL,movement_id uuid NOT NULL,PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,movement_id),FOREIGN KEY(tenant_id,work_id) REFERENCES asm_works(tenant_id,id),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id));
    CREATE TABLE asm_issue_lines(tenant_id uuid,id uuid,issue_id uuid NOT NULL,reservation_id uuid NOT NULL,quantity int NOT NULL CHECK(quantity>0),PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,issue_id,reservation_id),FOREIGN KEY(tenant_id,issue_id) REFERENCES asm_issues(tenant_id,id),FOREIGN KEY(tenant_id,reservation_id) REFERENCES asm_reservations(tenant_id,id));
    CREATE TABLE asm_devices(tenant_id uuid,id uuid,work_id uuid NOT NULL,inventory_unit_id uuid NOT NULL,layer_id uuid NOT NULL,movement_id uuid NOT NULL,number text NOT NULL,product jsonb NOT NULL,completed_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,inventory_unit_id),UNIQUE(tenant_id,movement_id),UNIQUE(tenant_id,number),FOREIGN KEY(tenant_id,work_id) REFERENCES asm_works(tenant_id,id),FOREIGN KEY(tenant_id,inventory_unit_id) REFERENCES inv_units(tenant_id,id),FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id));
    CREATE TABLE asm_installations(tenant_id uuid,id uuid,device_id uuid NOT NULL,layer_id uuid NOT NULL,unit_id uuid,quantity int NOT NULL CHECK(quantity>0),position text NOT NULL,installed_at timestamptz NOT NULL DEFAULT clock_timestamp(),removed_at timestamptz,correction_id uuid,PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,device_id) REFERENCES asm_devices(tenant_id,id),FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id),FOREIGN KEY(tenant_id,unit_id) REFERENCES inv_units(tenant_id,id),FOREIGN KEY(tenant_id,correction_id) REFERENCES inv_movements(tenant_id,id));
    CREATE UNIQUE INDEX installed_once ON asm_installations(tenant_id,unit_id) WHERE removed_at IS NULL AND unit_id IS NOT NULL;
    CREATE FUNCTION asm_installation_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' OR OLD.removed_at IS NOT NULL OR NEW.removed_at IS NULL OR NEW.correction_id IS NULL OR (to_jsonb(NEW)-'removed_at'-'correction_id')<>(to_jsonb(OLD)-'removed_at'-'correction_id') THEN RAISE EXCEPTION 'immutable installation' USING ERRCODE='23514'; END IF;RETURN NEW; END $$;
    CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON asm_installations FOR EACH ROW EXECUTE FUNCTION asm_installation_guard();
    GRANT UPDATE ON asm_installations TO silicon_app;
    """)
    for t in ['asm_issues','asm_issue_lines','asm_devices']:op.execute(f'CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION publication_immutable()')
    op.execute("""
    ALTER TABLE asm_requirements ADD UNIQUE(tenant_id,id,work_id);
    ALTER TABLE asm_reservations ADD FOREIGN KEY(tenant_id,requirement_id,work_id) REFERENCES asm_requirements(tenant_id,id,work_id);
    CREATE FUNCTION asm_work_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' OR NEW.order_id<>OLD.order_id OR NEW.wip_location_id<>OLD.wip_location_id OR (OLD.state<>'draft' AND (to_jsonb(NEW)-'version'-'state')<>(to_jsonb(OLD)-'version'-'state')) THEN RAISE EXCEPTION 'frozen assembly source' USING ERRCODE='23514'; END IF;RETURN NEW; END $$;
    CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON asm_works FOR EACH ROW EXECUTE FUNCTION asm_work_guard();
    """)
    for t in TABLES:op.execute(f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY; ALTER TABLE {t} FORCE ROW LEVEL SECURITY; CREATE POLICY tenant_isolation ON {t} USING(tenant_visible(tenant_id)) WITH CHECK(tenant_visible(tenant_id)); GRANT SELECT,INSERT ON {t} TO silicon_app')
def downgrade():
    for t in reversed(TABLES):op.execute(f'DROP TABLE {t}')
    op.execute("DROP FUNCTION asm_installation_guard(); DROP FUNCTION asm_work_guard()")
    op.execute("ALTER TABLE inv_movements DROP CONSTRAINT inv_movements_kind_check; ALTER TABLE inv_movements ADD CHECK(kind IN ('receipt','opening','inspection','transfer','reverse')); ALTER TABLE inv_entries DROP CONSTRAINT inv_entries_state_check; ALTER TABLE inv_entries ADD CHECK(state IN ('pending','qualified','quarantine')); ALTER TABLE inv_balances DROP CONSTRAINT inv_balances_state_check; ALTER TABLE inv_balances ADD CHECK(state IN ('pending','qualified','quarantine'))")
    op.execute("DELETE FROM role_permissions WHERE permission LIKE 'assembly.%' OR permission='device.read'; DELETE FROM permissions WHERE name LIKE 'assembly.%' OR name='device.read'")
