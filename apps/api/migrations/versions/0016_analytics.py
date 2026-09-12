"""Analytics permission, immutable confirmation times and report access indexes."""
from alembic import op
revision='0016_analytics'
down_revision='0015_service'
branch_labels=depends_on=None

def upgrade():
    op.execute("INSERT INTO permissions VALUES ('analytics.read'); INSERT INTO role_permissions VALUES ('admin','analytics.read')")
    op.execute("""CREATE TABLE analytics_confirmations(
      tenant_id uuid NOT NULL,id uuid NOT NULL,kind text NOT NULL CHECK(kind IN('plans','cash','refunds')),
      confirmed_at timestamptz NOT NULL,source text NOT NULL CHECK(source IN('audit','transition')),
      plan_id uuid GENERATED ALWAYS AS(CASE WHEN kind='plans' THEN id END) STORED,
      cash_id uuid GENERATED ALWAYS AS(CASE WHEN kind='cash' THEN id END) STORED,
      refund_id uuid GENERATED ALWAYS AS(CASE WHEN kind='refunds' THEN id END) STORED,
      FOREIGN KEY(tenant_id,plan_id) REFERENCES fin_plans(tenant_id,id),
      FOREIGN KEY(tenant_id,cash_id) REFERENCES fin_cash(tenant_id,id),
      FOREIGN KEY(tenant_id,refund_id) REFERENCES fin_refunds(tenant_id,id),
      PRIMARY KEY(tenant_id,kind,id));
      ALTER TABLE analytics_confirmations ENABLE ROW LEVEL SECURITY;
      ALTER TABLE analytics_confirmations FORCE ROW LEVEL SECURITY;
      CREATE POLICY tenant_isolation ON analytics_confirmations USING(tenant_visible(tenant_id)) WITH CHECK(tenant_visible(tenant_id));
      GRANT SELECT,INSERT ON analytics_confirmations TO silicon_app;
      CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON analytics_confirmations FOR EACH ROW EXECUTE FUNCTION publication_immutable();
      CREATE FUNCTION analytics_confirmed() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        IF NEW.state='confirmed' AND OLD.state='draft' THEN
          INSERT INTO analytics_confirmations(tenant_id,id,kind,confirmed_at,source) VALUES(NEW.tenant_id,NEW.id,substring(TG_TABLE_NAME from 5),clock_timestamp(),'transition');
        END IF; RETURN NEW; END $$;
    """)
    # Keep audit and metadata FORCE RLS active. Each eligible tenant is read under
    # one of its actual active memberships. A tenant with no active membership
    # cannot be backfilled now; report its missing historical time honestly.
    for kind in ('plans','cash','refunds'):
        op.execute(f"""DO $$ DECLARE member record; BEGIN
        FOR member IN SELECT DISTINCT ON (m.tenant_id) m.tenant_id,m.user_id
          FROM memberships m JOIN identity_users u ON u.id=m.user_id
          WHERE m.active AND u.active ORDER BY m.tenant_id,m.user_id LOOP
          PERFORM set_config('silicon.tenant_id',member.tenant_id::text,true);
          PERFORM set_config('silicon.user_id',member.user_id::text,true);
          INSERT INTO analytics_confirmations(tenant_id,id,kind,confirmed_at,source)
          SELECT tenant_id,object_id::uuid,'{kind}',min(created_at),'audit' FROM audit_events
          WHERE action='finance.{kind}.confirm:'||object_id AND outcome='allowed'
          GROUP BY tenant_id,object_id ON CONFLICT DO NOTHING;
        END LOOP;
        PERFORM set_config('silicon.tenant_id','',true);
        PERFORM set_config('silicon.user_id','',true);
        END $$;
        CREATE TRIGGER analytics_confirmed AFTER UPDATE ON fin_{kind} FOR EACH ROW EXECUTE FUNCTION analytics_confirmed();""")
    for name,table,columns in [('analytics_inventory_date','inv_movements','tenant_id,effective_on,id'),('analytics_entry_source','inv_entries','tenant_id,movement_id,layer_id'),('analytics_signed_date','signed_contracts','tenant_id,registered_at,id'),('analytics_finance_date','fin_cash','tenant_id,occurred_at,id')]:
        op.execute(f'CREATE INDEX {name} ON {table}({columns})')

def downgrade():
    op.execute("ALTER TABLE analytics_confirmations DISABLE ROW LEVEL SECURITY; DO $$ BEGIN IF EXISTS(SELECT 1 FROM analytics_confirmations WHERE source='transition') THEN RAISE EXCEPTION 'finance history prevents downgrade (confirmation time history)'; END IF; END $$")
    for kind in ('plans','cash','refunds'):op.execute(f'DROP TRIGGER analytics_confirmed ON fin_{kind}')
    op.execute('DROP FUNCTION analytics_confirmed();DROP TABLE analytics_confirmations')
    for name in ('analytics_inventory_date','analytics_entry_source','analytics_signed_date','analytics_finance_date'):op.execute(f'DROP INDEX {name}')
    op.execute("DELETE FROM role_permissions WHERE permission='analytics.read';DELETE FROM permissions WHERE name='analytics.read'")
