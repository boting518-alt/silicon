"""Append-only full corrections of negative adjustments; preserve 0013 facts."""
from alembic import op
revision='0014_finance_corrections'
down_revision='0013_finance'
branch_labels=depends_on=None

def upgrade():
    op.execute("""
    ALTER TABLE fin_adjustments ADD CONSTRAINT fin_adjustment_plan_identity UNIQUE(tenant_id,plan_id,id);
    CREATE TABLE fin_adjustment_corrections(
      tenant_id uuid NOT NULL,id uuid NOT NULL,plan_id uuid NOT NULL,adjustment_id uuid NOT NULL,
      reason text NOT NULL,basis_ref text NOT NULL,actor_id uuid NOT NULL REFERENCES identity_users(id),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,id),
      UNIQUE(tenant_id,adjustment_id),
      FOREIGN KEY(tenant_id,plan_id,adjustment_id) REFERENCES fin_adjustments(tenant_id,plan_id,id));
    ALTER TABLE fin_adjustment_corrections ENABLE ROW LEVEL SECURITY;
    ALTER TABLE fin_adjustment_corrections FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON fin_adjustment_corrections USING(tenant_visible(tenant_id)) WITH CHECK(tenant_visible(tenant_id));
    GRANT SELECT,INSERT ON fin_adjustment_corrections TO silicon_app;
    CREATE FUNCTION fin_correction_negative() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF NOT EXISTS(SELECT 1 FROM fin_adjustments WHERE tenant_id=NEW.tenant_id AND plan_id=NEW.plan_id AND id=NEW.adjustment_id AND amount<0)
      THEN RAISE EXCEPTION 'correction requires original negative adjustment' USING ERRCODE='23514';END IF;
      RETURN NEW;END $$;
    CREATE TRIGGER negative_original BEFORE INSERT ON fin_adjustment_corrections FOR EACH ROW EXECUTE FUNCTION fin_correction_negative();
    CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON fin_adjustment_corrections FOR EACH ROW EXECUTE FUNCTION publication_immutable();
    """)

def downgrade():
    op.execute("""ALTER TABLE fin_adjustment_corrections DISABLE ROW LEVEL SECURITY;
    DO $$ BEGIN IF EXISTS(SELECT 1 FROM fin_adjustment_corrections) THEN RAISE EXCEPTION 'finance history prevents downgrade: adjustment corrections';END IF;END $$;
    DROP TABLE fin_adjustment_corrections;
    DROP FUNCTION fin_correction_negative();
    ALTER TABLE fin_adjustments DROP CONSTRAINT fin_adjustment_plan_identity;""")
