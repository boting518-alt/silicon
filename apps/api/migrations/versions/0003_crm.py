"""Customer aggregate independent from contracts, with tenant keys and RLS."""
from alembic import op
revision='0003_crm'
down_revision='0002_identity'
branch_labels=depends_on=None

TABLES=['crm_customers','crm_contacts','crm_projects','crm_project_people','crm_sites','crm_responsibilities','crm_role_history','crm_commands']


def upgrade():
    op.execute('''
    INSERT INTO permissions VALUES ('crm.read'),('crm.write');
    INSERT INTO role_permissions VALUES ('admin','crm.read'),('admin','crm.write'),('member','crm.read'),('member','crm.write'),('viewer','crm.read');
    CREATE TABLE crm_customers (
      tenant_id uuid NOT NULL REFERENCES tenants(id), id uuid NOT NULL,
      number text NOT NULL CHECK(length(btrim(number)) BETWEEN 1 AND 40),
      name text NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 160),
      province text NOT NULL DEFAULT '', city text NOT NULL DEFAULT '', industry text NOT NULL DEFAULT '',
      level text NOT NULL DEFAULT '普通客户', stage text NOT NULL DEFAULT '跟进中', notes text NOT NULL DEFAULT '',
      owner_id uuid NOT NULL, version integer NOT NULL DEFAULT 1 CHECK(version>0),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,number),
      FOREIGN KEY(tenant_id,owner_id) REFERENCES memberships(tenant_id,user_id));
    CREATE INDEX crm_customer_page ON crm_customers(tenant_id,created_at DESC,id);
    CREATE TABLE crm_contacts (
      tenant_id uuid NOT NULL, id uuid NOT NULL, customer_id uuid NOT NULL,
      name text NOT NULL CHECK(length(btrim(name))>0), title text NOT NULL DEFAULT '',
      phone text NOT NULL DEFAULT '', email text NOT NULL DEFAULT '',
      PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,customer_id,id),
      FOREIGN KEY(tenant_id,customer_id) REFERENCES crm_customers(tenant_id,id));
    CREATE TABLE crm_projects (
      tenant_id uuid NOT NULL, id uuid NOT NULL, customer_id uuid NOT NULL,
      name text NOT NULL CHECK(length(btrim(name))>0), notes text NOT NULL DEFAULT '',
      PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,customer_id,id),
      FOREIGN KEY(tenant_id,customer_id) REFERENCES crm_customers(tenant_id,id));
    CREATE TABLE crm_project_people (
      tenant_id uuid NOT NULL, customer_id uuid NOT NULL, project_id uuid NOT NULL, contact_id uuid NOT NULL,
      role text NOT NULL CHECK(role IN ('project_lead','key_person')),
      PRIMARY KEY(tenant_id,project_id,contact_id,role),
      FOREIGN KEY(tenant_id,customer_id,project_id) REFERENCES crm_projects(tenant_id,customer_id,id),
      FOREIGN KEY(tenant_id,customer_id,contact_id) REFERENCES crm_contacts(tenant_id,customer_id,id));
    CREATE TABLE crm_sites (
      tenant_id uuid NOT NULL, id uuid NOT NULL, customer_id uuid NOT NULL,
      name text NOT NULL, address text NOT NULL,
      PRIMARY KEY(tenant_id,id), FOREIGN KEY(tenant_id,customer_id) REFERENCES crm_customers(tenant_id,id));
    CREATE TABLE crm_responsibilities (
      tenant_id uuid NOT NULL, customer_id uuid NOT NULL, role text NOT NULL CHECK(role IN ('sales','service')),
      user_id uuid NOT NULL, PRIMARY KEY(tenant_id,customer_id,role),
      FOREIGN KEY(tenant_id,customer_id) REFERENCES crm_customers(tenant_id,id),
      FOREIGN KEY(tenant_id,user_id) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE crm_role_history (
      tenant_id uuid NOT NULL, id uuid NOT NULL, customer_id uuid NOT NULL,
      party text NOT NULL CHECK(party IN ('customer','internal')), project_id uuid, role text NOT NULL,
      person_id uuid NOT NULL, person_name text NOT NULL, project_name text NOT NULL DEFAULT '',
      valid_from timestamptz NOT NULL DEFAULT now(), valid_until timestamptz, changed_by uuid NOT NULL,
      CHECK((party='customer' AND project_id IS NOT NULL AND role IN ('project_lead','key_person')) OR
            (party='internal' AND project_id IS NULL AND role IN ('sales','service'))),
      PRIMARY KEY(tenant_id,id), FOREIGN KEY(tenant_id,customer_id) REFERENCES crm_customers(tenant_id,id),
      FOREIGN KEY(tenant_id,changed_by) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE crm_commands (
      tenant_id uuid NOT NULL, actor_id uuid NOT NULL, operation text NOT NULL, key text NOT NULL,
      request_hash text NOT NULL, response jsonb NOT NULL,
      PRIMARY KEY(tenant_id,actor_id,operation,key),
      FOREIGN KEY(tenant_id,actor_id) REFERENCES memberships(tenant_id,user_id));
    ''')
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_isolation ON {table} USING (tenant_visible(tenant_id)) WITH CHECK (tenant_visible(tenant_id))')
        op.execute(f'GRANT SELECT,INSERT,UPDATE ON {table} TO silicon_app')
    op.execute('GRANT DELETE ON crm_project_people,crm_projects,crm_contacts,crm_sites,crm_responsibilities TO silicon_app')


def downgrade():
    for table in reversed(TABLES): op.execute(f'DROP TABLE {table}')
    op.execute("DELETE FROM role_permissions WHERE permission IN ('crm.read','crm.write'); DELETE FROM permissions WHERE name IN ('crm.read','crm.write')")
