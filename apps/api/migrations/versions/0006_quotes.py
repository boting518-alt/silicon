"""Persistent quote drafts; no publication or discount redemption."""
from alembic import op
revision='0006_quotes'
down_revision='0005_catalog'
branch_labels=depends_on=None
TABLES=['quote_discounts','quote_drafts','quote_selections','quote_exclusions','quote_commands']

def upgrade():
    op.execute('''
    INSERT INTO permissions VALUES ('quote.read'),('quote.write'),('quote.discount');
    INSERT INTO role_permissions VALUES ('admin','quote.read'),('admin','quote.write'),('admin','quote.discount'),('member','quote.read'),('member','quote.write'),('viewer','quote.read');
    CREATE TABLE quote_discounts(
      tenant_id uuid REFERENCES tenants,id uuid,code_hash text NOT NULL,name text NOT NULL,version int NOT NULL CHECK(version>0),
      enabled boolean NOT NULL,valid_from timestamptz NOT NULL,valid_to timestamptz NOT NULL,
      scope text NOT NULL,tax_included boolean NOT NULL,basis_points int NOT NULL CHECK(basis_points BETWEEN 1 AND 10000),
      minimum numeric(18,2) NOT NULL CHECK(minimum>=0),maximum_discount numeric(18,2) NOT NULL CHECK(maximum_discount>=0),
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,code_hash),CHECK(valid_to>valid_from));
    CREATE TABLE quote_drafts(
      tenant_id uuid REFERENCES tenants,id uuid,name text NOT NULL,customer_id uuid NOT NULL,project_id uuid NOT NULL,bom_id uuid NOT NULL,
      quantity int NOT NULL CHECK(quantity BETWEEN 1 AND 10000),scope text NOT NULL,tax_included boolean NOT NULL,discount_id uuid,
      version int NOT NULL DEFAULT 1 CHECK(version>0),calculation jsonb NOT NULL,owner_id uuid NOT NULL,
      PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,customer_id) REFERENCES crm_customers(tenant_id,id),
      FOREIGN KEY(tenant_id,customer_id,project_id) REFERENCES crm_projects(tenant_id,customer_id,id) DEFERRABLE INITIALLY DEFERRED,
      FOREIGN KEY(tenant_id,bom_id) REFERENCES catalog_boms(tenant_id,id),
      FOREIGN KEY(tenant_id,discount_id) REFERENCES quote_discounts(tenant_id,id),
      FOREIGN KEY(tenant_id,owner_id) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE quote_selections(
      tenant_id uuid,draft_id uuid,sku_id uuid,quantity int NOT NULL CHECK(quantity BETWEEN 1 AND 10000),
      PRIMARY KEY(tenant_id,draft_id,sku_id),FOREIGN KEY(tenant_id,draft_id) REFERENCES quote_drafts(tenant_id,id),FOREIGN KEY(tenant_id,sku_id) REFERENCES catalog_skus(tenant_id,id));
    CREATE TABLE quote_exclusions(
      tenant_id uuid,draft_id uuid,sku_id uuid,PRIMARY KEY(tenant_id,draft_id,sku_id),
      FOREIGN KEY(tenant_id,draft_id) REFERENCES quote_drafts(tenant_id,id),FOREIGN KEY(tenant_id,sku_id) REFERENCES catalog_skus(tenant_id,id));
    CREATE TABLE quote_commands(
      tenant_id uuid,actor_id uuid,operation text,key text,request_hash text NOT NULL,response jsonb NOT NULL,
      PRIMARY KEY(tenant_id,actor_id,operation,key),FOREIGN KEY(tenant_id,actor_id) REFERENCES memberships(tenant_id,user_id));
    ''')
    for t in TABLES:
        op.execute(f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY; ALTER TABLE {t} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_isolation ON {t} USING (tenant_visible(tenant_id)) WITH CHECK (tenant_visible(tenant_id))')
        op.execute(f'GRANT SELECT ON {t} TO silicon_app')
    # Discount configuration is an explicit operator/migrator task, never an HTTP mutation.
    op.execute('GRANT INSERT ON quote_drafts,quote_selections,quote_exclusions,quote_commands TO silicon_app')
    op.execute('GRANT UPDATE ON quote_drafts TO silicon_app; GRANT DELETE ON quote_selections,quote_exclusions TO silicon_app')

def downgrade():
    for t in reversed(TABLES):op.execute(f'DROP TABLE {t}')
    op.execute("DELETE FROM role_permissions WHERE permission LIKE 'quote.%'; DELETE FROM permissions WHERE name LIKE 'quote.%'")
