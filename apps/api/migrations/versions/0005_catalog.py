"""Tenant catalog, immutable BOM/rule/price editions and typed hardware specifications."""
from alembic import op
revision='0005_catalog'
down_revision='0004_session_context'
branch_labels=depends_on=None
TABLES=['catalog_manufacturers','catalog_brands','catalog_skus','catalog_specs','catalog_rules','catalog_boms','catalog_bom_lines','catalog_price_books','catalog_price_lines','catalog_commands']


def upgrade():
    op.execute('''
    INSERT INTO permissions VALUES ('catalog.read'),('catalog.write');
    INSERT INTO role_permissions VALUES ('admin','catalog.read'),('admin','catalog.write'),('member','catalog.read'),('viewer','catalog.read');
    CREATE TABLE catalog_manufacturers(tenant_id uuid REFERENCES tenants,id uuid NOT NULL,name text NOT NULL CHECK(length(btrim(name))>0),PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,name));
    CREATE TABLE catalog_brands(tenant_id uuid REFERENCES tenants,id uuid NOT NULL,name text NOT NULL CHECK(length(btrim(name))>0),kind text NOT NULL CHECK(kind IN ('own','third_party')),PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,name));
    CREATE TABLE catalog_skus(
      tenant_id uuid REFERENCES tenants,id uuid NOT NULL,number text NOT NULL CHECK(length(btrim(number)) BETWEEN 1 AND 40),name text NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 160),
      category text NOT NULL CHECK(category IN ('host','cpu','gpu','memory','psu','system_disk','data_disk','nic','ib')),
      manufacturer_id uuid NOT NULL,brand_id uuid NOT NULL,enabled boolean NOT NULL,version int NOT NULL DEFAULT 1 CHECK(version>0),
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,number),
      FOREIGN KEY(tenant_id,manufacturer_id) REFERENCES catalog_manufacturers(tenant_id,id),FOREIGN KEY(tenant_id,brand_id) REFERENCES catalog_brands(tenant_id,id));
    CREATE TABLE catalog_specs(
      tenant_id uuid,sku_id uuid,socket text NOT NULL DEFAULT '',memory_generation text NOT NULL DEFAULT '',
      capacity_gb int CHECK(capacity_gb>0),power_w int CHECK(power_w>0),slot_width int CHECK(slot_width BETWEEN 1 AND 8),
      interface text NOT NULL DEFAULT '',speed_gbps int CHECK(speed_gbps>0),cpu_sockets int CHECK(cpu_sockets BETWEEN 1 AND 8),
      PRIMARY KEY(tenant_id,sku_id),FOREIGN KEY(tenant_id,sku_id) REFERENCES catalog_skus(tenant_id,id));
    CREATE TABLE catalog_rules(
      tenant_id uuid REFERENCES tenants,id uuid NOT NULL,family_id uuid NOT NULL,revision int NOT NULL CHECK(revision>0),name text NOT NULL,source text NOT NULL CHECK(length(btrim(source))>0),
      socket text NOT NULL,memory_generation text NOT NULL,power_budget_w int CHECK(power_budget_w>0),
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,family_id,revision));
    CREATE TABLE catalog_boms(
      tenant_id uuid REFERENCES tenants,id uuid NOT NULL,family_id uuid NOT NULL,revision int NOT NULL CHECK(revision>0),version int NOT NULL DEFAULT 1 CHECK(version>0),
      name text NOT NULL,kind text NOT NULL CHECK(kind IN ('package','bom')),subject_sku_id uuid NOT NULL,rule_id uuid,
      state text NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','published')),snapshot jsonb,
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,family_id,revision),
      FOREIGN KEY(tenant_id,subject_sku_id) REFERENCES catalog_skus(tenant_id,id),FOREIGN KEY(tenant_id,rule_id) REFERENCES catalog_rules(tenant_id,id),
      CHECK(state='draft' OR snapshot IS NOT NULL));
    CREATE TABLE catalog_bom_lines(
      tenant_id uuid,bom_id uuid,position int NOT NULL,sku_id uuid NOT NULL,package_version_id uuid,quantity int NOT NULL CHECK(quantity BETWEEN 1 AND 10000),
      required boolean NOT NULL,charge_mode text NOT NULL CHECK(charge_mode IN ('included','separate')),
      PRIMARY KEY(tenant_id,bom_id,position),UNIQUE(tenant_id,bom_id,sku_id),
      FOREIGN KEY(tenant_id,bom_id) REFERENCES catalog_boms(tenant_id,id),FOREIGN KEY(tenant_id,sku_id) REFERENCES catalog_skus(tenant_id,id),
      FOREIGN KEY(tenant_id,package_version_id) REFERENCES catalog_boms(tenant_id,id));
    CREATE TABLE catalog_price_books(
      tenant_id uuid REFERENCES tenants,id uuid NOT NULL,family_id uuid NOT NULL,revision int NOT NULL CHECK(revision>0),version int NOT NULL DEFAULT 1 CHECK(version>0),
      name text NOT NULL,scope text NOT NULL CHECK(length(btrim(scope))>0),currency text NOT NULL CHECK(currency='CNY'),tax_included boolean NOT NULL,
      valid_from timestamptz NOT NULL,valid_to timestamptz NOT NULL,source text NOT NULL CHECK(length(btrim(source))>0),state text NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','published')),
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,family_id,revision),CHECK(valid_to>valid_from));
    CREATE TABLE catalog_price_lines(
      tenant_id uuid,book_id uuid,sku_id uuid,amount numeric(18,2) NOT NULL CHECK(amount>=0),
      PRIMARY KEY(tenant_id,book_id,sku_id),FOREIGN KEY(tenant_id,book_id) REFERENCES catalog_price_books(tenant_id,id),FOREIGN KEY(tenant_id,sku_id) REFERENCES catalog_skus(tenant_id,id));
    CREATE TABLE catalog_commands(
      tenant_id uuid,actor_id uuid,operation text,key text,request_hash text NOT NULL,response jsonb NOT NULL,
      PRIMARY KEY(tenant_id,actor_id,operation,key),FOREIGN KEY(tenant_id,actor_id) REFERENCES memberships(tenant_id,user_id));
    CREATE FUNCTION catalog_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME='catalog_rules' OR OLD.state='published' THEN
        RAISE EXCEPTION 'published catalog version is immutable' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE FUNCTION catalog_child_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE parent_state text;
    BEGIN
      IF TG_TABLE_NAME='catalog_bom_lines' THEN
        SELECT state INTO parent_state FROM catalog_boms WHERE tenant_id=COALESCE(NEW.tenant_id,OLD.tenant_id) AND id=COALESCE(NEW.bom_id,OLD.bom_id);
      ELSE
        SELECT state INTO parent_state FROM catalog_price_books WHERE tenant_id=COALESCE(NEW.tenant_id,OLD.tenant_id) AND id=COALESCE(NEW.book_id,OLD.book_id);
      END IF;
      IF parent_state='published' THEN RAISE EXCEPTION 'published children are immutable' USING ERRCODE='23514'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END $$;
    ''')
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY; ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_isolation ON {table} USING (tenant_visible(tenant_id)) WITH CHECK (tenant_visible(tenant_id))')
        op.execute(f'GRANT SELECT,INSERT ON {table} TO silicon_app')
    op.execute('GRANT UPDATE ON catalog_skus,catalog_specs,catalog_boms,catalog_price_books TO silicon_app')
    op.execute('GRANT DELETE ON catalog_bom_lines,catalog_price_lines TO silicon_app')
    for table in ['catalog_boms','catalog_price_books','catalog_rules']:
        op.execute(f'CREATE TRIGGER immutable_version BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION catalog_immutable()')
    for table in ['catalog_bom_lines','catalog_price_lines']:
        op.execute(f'CREATE TRIGGER immutable_children BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION catalog_child_immutable()')


def downgrade():
    for table in reversed(TABLES):op.execute(f'DROP TABLE {table}')
    op.execute('DROP FUNCTION catalog_child_immutable(); DROP FUNCTION catalog_immutable()')
    op.execute("DELETE FROM role_permissions WHERE permission LIKE 'catalog.%'; DELETE FROM permissions WHERE name LIKE 'catalog.%'")
