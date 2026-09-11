"""Device testing and immutable physical delivery facts on existing stock ledger."""
from alembic import op
revision='0012_delivery'
down_revision='0011_assembly_corrections'
branch_labels=depends_on=None
TABLES=['del_tests','del_shipments','del_lines','del_acceptances','del_returns','del_reversals']
def upgrade():
    op.execute("""
    INSERT INTO permissions VALUES ('delivery.read'),('delivery.test'),('delivery.ship'),('delivery.accept'),('delivery.return'),('delivery.correct');
    INSERT INTO role_permissions SELECT 'admin',name FROM permissions WHERE name LIKE 'delivery.%';
    INSERT INTO role_permissions SELECT 'member',name FROM permissions WHERE name LIKE 'delivery.%' AND name<>'delivery.correct';
    INSERT INTO role_permissions VALUES ('viewer','delivery.read');
    ALTER TABLE inv_movements DROP CONSTRAINT inv_movements_kind_check;
    ALTER TABLE inv_movements ADD CHECK(kind IN ('receipt','opening','inspection','transfer','reverse','assembly_issue','assembly_complete','delivery_ship','delivery_return','delivery_reverse'));
    CREATE TABLE del_tests(tenant_id uuid,id uuid,device_id uuid NOT NULL,completion_id uuid NOT NULL,layer_version int NOT NULL CHECK(layer_version>0),
      result text NOT NULL CHECK(result IN ('pass','fail')),items jsonb NOT NULL,performed_at timestamptz NOT NULL,actor_id uuid NOT NULL,
      notes text NOT NULL,report_ref text NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,id,device_id,completion_id),
      FOREIGN KEY(tenant_id,completion_id,device_id) REFERENCES asm_completions(tenant_id,id,device_id),FOREIGN KEY(actor_id) REFERENCES identity_users(id));
    CREATE TABLE del_shipments(tenant_id uuid,id uuid,order_id uuid NOT NULL,recipient text NOT NULL,address text NOT NULL,contact text NOT NULL,
      state text NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','confirmed','cancelled')),version int NOT NULL DEFAULT 1 CHECK(version>0),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,id,order_id),FOREIGN KEY(tenant_id,order_id) REFERENCES sales_orders(tenant_id,id));
    CREATE TABLE del_lines(tenant_id uuid,id uuid,shipment_id uuid NOT NULL,order_id uuid NOT NULL,device_id uuid NOT NULL,completion_id uuid NOT NULL,
      layer_id uuid NOT NULL,location_id uuid,test_id uuid,movement_id uuid,PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,shipment_id,device_id),
      UNIQUE(tenant_id,id,device_id),FOREIGN KEY(tenant_id,shipment_id,order_id) REFERENCES del_shipments(tenant_id,id,order_id),
      FOREIGN KEY(tenant_id,completion_id,device_id) REFERENCES asm_completions(tenant_id,id,device_id),
      FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id),FOREIGN KEY(tenant_id,location_id) REFERENCES inv_locations(tenant_id,id),
      FOREIGN KEY(tenant_id,test_id,device_id,completion_id) REFERENCES del_tests(tenant_id,id,device_id,completion_id),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id),
      CHECK((movement_id IS NULL AND test_id IS NULL AND location_id IS NULL) OR (movement_id IS NOT NULL AND test_id IS NOT NULL AND location_id IS NOT NULL)));
    CREATE TABLE del_acceptances(tenant_id uuid,id uuid,line_id uuid NOT NULL,accepted bool NOT NULL,corrects uuid,performed_at timestamptz NOT NULL,actor_id uuid NOT NULL,confirmation text NOT NULL,notes text NOT NULL,evidence_ref text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,id,line_id),UNIQUE(tenant_id,corrects),FOREIGN KEY(tenant_id,line_id) REFERENCES del_lines(tenant_id,id),FOREIGN KEY(tenant_id,corrects,line_id) REFERENCES del_acceptances(tenant_id,id,line_id),FOREIGN KEY(actor_id) REFERENCES identity_users(id));
    CREATE TABLE del_returns(tenant_id uuid,id uuid,line_id uuid NOT NULL,location_id uuid NOT NULL,movement_id uuid NOT NULL,performed_at timestamptz NOT NULL,actor_id uuid NOT NULL,reason text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,line_id),FOREIGN KEY(tenant_id,line_id) REFERENCES del_lines(tenant_id,id),FOREIGN KEY(tenant_id,location_id) REFERENCES inv_locations(tenant_id,id),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id),FOREIGN KEY(actor_id) REFERENCES identity_users(id));
    CREATE TABLE del_reversals(tenant_id uuid,id uuid,shipment_id uuid NOT NULL,movement_id uuid NOT NULL,actor_id uuid NOT NULL,reason text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,shipment_id),FOREIGN KEY(tenant_id,shipment_id) REFERENCES del_shipments(tenant_id,id),FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id),FOREIGN KEY(actor_id) REFERENCES identity_users(id));
    CREATE FUNCTION del_ship_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' OR (OLD.state<>'draft' AND (to_jsonb(NEW)-'version')<>(to_jsonb(OLD)-'version')) OR NEW.order_id<>OLD.order_id THEN RAISE EXCEPTION 'frozen delivery' USING ERRCODE='23514'; END IF; RETURN NEW; END $$;
    CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON del_shipments FOR EACH ROW EXECUTE FUNCTION del_ship_guard();
    CREATE FUNCTION del_line_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' OR OLD.movement_id IS NOT NULL OR (to_jsonb(NEW)-'movement_id'-'test_id'-'location_id')<>(to_jsonb(OLD)-'movement_id'-'test_id'-'location_id') THEN RAISE EXCEPTION 'frozen delivery line' USING ERRCODE='23514'; END IF; RETURN NEW; END $$;
    CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON del_lines FOR EACH ROW EXECUTE FUNCTION del_line_guard();
    GRANT UPDATE ON del_lines,del_shipments TO silicon_app;
    """)
    for t in TABLES:
        op.execute(f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY; ALTER TABLE {t} FORCE ROW LEVEL SECURITY; CREATE POLICY tenant_isolation ON {t} USING(tenant_visible(tenant_id)) WITH CHECK(tenant_visible(tenant_id)); GRANT SELECT,INSERT ON {t} TO silicon_app')
        if t not in ('del_lines','del_shipments'):op.execute(f'CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION publication_immutable()')
def downgrade():
    for t in TABLES:op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY; DO $$ BEGIN IF EXISTS(SELECT 1 FROM {t}) THEN RAISE EXCEPTION 'delivery history prevents downgrade'; END IF; END $$")
    for t in reversed(TABLES):op.execute(f'DROP TABLE {t}')
    op.execute("DROP FUNCTION del_ship_guard();DROP FUNCTION del_line_guard(); DELETE FROM role_permissions WHERE permission LIKE 'delivery.%';DELETE FROM permissions WHERE name LIKE 'delivery.%';ALTER TABLE inv_movements DROP CONSTRAINT inv_movements_kind_check;ALTER TABLE inv_movements ADD CHECK(kind IN ('receipt','opening','inspection','transfer','reverse','assembly_issue','assembly_complete'))")
