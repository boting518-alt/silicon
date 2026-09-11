"""Preserve device identity; append controlled completion corrections."""
from alembic import op
revision='0011_assembly_corrections'
down_revision='0010_assembly'
branch_labels=depends_on=None

def upgrade():
    op.execute("""
    ALTER TABLE asm_devices DISABLE ROW LEVEL SECURITY;
    ALTER TABLE inv_movements DISABLE ROW LEVEL SECURITY;
    ALTER TABLE asm_installations DISABLE ROW LEVEL SECURITY;
    ALTER TABLE asm_devices ADD CONSTRAINT asm_device_work UNIQUE(tenant_id,id,work_id);
    CREATE TABLE asm_completions(
      tenant_id uuid,id uuid,device_id uuid NOT NULL,work_id uuid NOT NULL,
      layer_id uuid NOT NULL,movement_id uuid NOT NULL,completed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      correction_of uuid,reversed_by uuid,
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,movement_id),UNIQUE(tenant_id,id,device_id),
      FOREIGN KEY(tenant_id,device_id,work_id) REFERENCES asm_devices(tenant_id,id,work_id),
      FOREIGN KEY(tenant_id,layer_id) REFERENCES inv_layers(tenant_id,id),
      FOREIGN KEY(tenant_id,movement_id) REFERENCES inv_movements(tenant_id,id),
      FOREIGN KEY(tenant_id,correction_of,device_id) REFERENCES asm_completions(tenant_id,id,device_id),
      FOREIGN KEY(tenant_id,reversed_by) REFERENCES inv_movements(tenant_id,id));
    INSERT INTO asm_completions(tenant_id,id,device_id,work_id,layer_id,movement_id,completed_at,reversed_by)
      SELECT d.tenant_id,d.id,d.id,d.work_id,d.layer_id,d.movement_id,d.completed_at,r.id
      FROM asm_devices d LEFT JOIN inv_movements r ON r.tenant_id=d.tenant_id AND r.reverse_of=d.movement_id;
    CREATE UNIQUE INDEX asm_one_live_device_completion ON asm_completions(tenant_id,device_id) WHERE reversed_by IS NULL;
    CREATE UNIQUE INDEX asm_one_live_work_completion ON asm_completions(tenant_id,work_id) WHERE reversed_by IS NULL;
    CREATE FUNCTION asm_completion_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'immutable completion' USING ERRCODE='23514'; END IF;
      IF TG_OP='UPDATE' AND (OLD.reversed_by IS NOT NULL OR NEW.reversed_by IS NULL OR (to_jsonb(NEW)-'reversed_by')<>(to_jsonb(OLD)-'reversed_by')) THEN
        RAISE EXCEPTION 'immutable completion' USING ERRCODE='23514'; END IF;
      IF NEW.reversed_by IS NOT NULL AND NOT EXISTS(SELECT 1 FROM inv_movements WHERE tenant_id=NEW.tenant_id AND id=NEW.reversed_by AND reverse_of=NEW.movement_id) THEN
        RAISE EXCEPTION 'invalid completion reversal' USING ERRCODE='23514'; END IF;
      IF TG_OP='INSERT' AND NEW.correction_of IS NOT NULL AND NOT EXISTS(SELECT 1 FROM asm_completions WHERE tenant_id=NEW.tenant_id AND id=NEW.correction_of AND device_id=NEW.device_id AND reversed_by IS NOT NULL) THEN
        RAISE EXCEPTION 'correction requires reversed completion' USING ERRCODE='23514'; END IF;
      RETURN NEW; END $$;
    CREATE TRIGGER frozen BEFORE UPDATE OR DELETE OR INSERT ON asm_completions FOR EACH ROW EXECUTE FUNCTION asm_completion_guard();
    ALTER TABLE asm_installations ADD COLUMN completion_id uuid;
    ALTER TABLE asm_installations DISABLE TRIGGER immutable;
    UPDATE asm_installations SET completion_id=device_id;
    ALTER TABLE asm_installations ENABLE TRIGGER immutable;
    ALTER TABLE asm_installations ALTER COLUMN completion_id SET NOT NULL;
    ALTER TABLE asm_installations ADD FOREIGN KEY(tenant_id,completion_id,device_id) REFERENCES asm_completions(tenant_id,id,device_id);
    ALTER TABLE asm_devices ENABLE ROW LEVEL SECURITY;
    ALTER TABLE inv_movements ENABLE ROW LEVEL SECURITY;
    ALTER TABLE asm_installations ENABLE ROW LEVEL SECURITY;
    ALTER TABLE asm_completions ENABLE ROW LEVEL SECURITY;
    ALTER TABLE asm_completions FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON asm_completions USING(tenant_visible(tenant_id)) WITH CHECK(tenant_visible(tenant_id));
    GRANT SELECT,INSERT,UPDATE ON asm_completions TO silicon_app;
    """)

def downgrade():
    # Corrections cannot be represented by 0010; do not discard their history.
    op.execute("""ALTER TABLE asm_completions DISABLE ROW LEVEL SECURITY; DO $$ BEGIN IF EXISTS(SELECT 1 FROM asm_completions WHERE correction_of IS NOT NULL) THEN
      RAISE EXCEPTION 'cannot downgrade corrected assembly history'; END IF; END $$;
      ALTER TABLE asm_installations DROP COLUMN completion_id;
      DROP TABLE asm_completions;
      DROP FUNCTION asm_completion_guard();
      ALTER TABLE asm_devices DROP CONSTRAINT asm_device_work;
    """)
