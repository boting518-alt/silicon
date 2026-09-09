"""Global identity and authorization control plane; tenant audit uses forced RLS."""
from alembic import op
revision = '0002_identity'
down_revision = '0001_platform'
branch_labels = depends_on = None


def upgrade():
    op.execute('''
    CREATE TABLE identity_users (
      id uuid PRIMARY KEY, issuer text NOT NULL, subject text NOT NULL,
      display_name text NOT NULL, active boolean NOT NULL DEFAULT true,
      UNIQUE(issuer, subject));
    CREATE TABLE tenants (id uuid PRIMARY KEY, name text NOT NULL);
    CREATE TABLE roles (name text PRIMARY KEY, data_scope text NOT NULL CHECK(data_scope IN ('all','own')));
    CREATE TABLE permissions (name text PRIMARY KEY);
    CREATE TABLE role_permissions (role text REFERENCES roles(name), permission text REFERENCES permissions(name), PRIMARY KEY(role,permission));
    CREATE TABLE memberships (
      tenant_id uuid REFERENCES tenants(id), user_id uuid REFERENCES identity_users(id),
      role text NOT NULL REFERENCES roles(name), active boolean NOT NULL DEFAULT true,
      PRIMARY KEY(tenant_id,user_id));
    INSERT INTO roles VALUES ('admin','all'),('member','own'),('viewer','all');
    INSERT INTO permissions VALUES ('resource.read'),('resource.write'),('field.cost'),('attachment.read'),('job.run');
    INSERT INTO role_permissions SELECT 'admin', name FROM permissions;
    INSERT INTO role_permissions VALUES ('member','resource.read'),('member','resource.write'),('member','attachment.read'),('member','job.run'),('viewer','resource.read');
    CREATE FUNCTION lock_membership(actor uuid, tenant uuid)
      RETURNS TABLE(data_scope text, role text) LANGUAGE sql VOLATILE SECURITY DEFINER
      SET search_path=pg_catalog,public AS $$
      SELECT r.data_scope,m.role FROM public.memberships m
      JOIN public.identity_users u ON u.id=m.user_id JOIN public.roles r ON r.name=m.role
      WHERE m.user_id=actor AND m.tenant_id=tenant AND m.active AND u.active FOR SHARE OF m,u
    $$;
    REVOKE ALL ON FUNCTION lock_membership(uuid,uuid) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION lock_membership(uuid,uuid) TO silicon_app;
    CREATE TABLE login_attempts (
      state_hash text PRIMARY KEY, browser_hash text NOT NULL, nonce text NOT NULL,
      verifier text NOT NULL, expires_at timestamptz NOT NULL);
    CREATE TABLE sessions (
      token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES identity_users(id),
      tenant_id uuid, csrf_hash text NOT NULL, expires_at timestamptz NOT NULL,
      FOREIGN KEY(tenant_id,user_id) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE audit_events (
      id uuid PRIMARY KEY, actor_id uuid, tenant_id uuid,
      action text NOT NULL, object_id text NOT NULL, outcome text NOT NULL CHECK(outcome IN ('allowed','denied')),
      request_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
    CREATE FUNCTION tenant_visible(target uuid) RETURNS boolean LANGUAGE sql STABLE AS $$
      SELECT target = NULLIF(current_setting('silicon.tenant_id',true),'')::uuid
      AND EXISTS (SELECT 1 FROM memberships m JOIN identity_users u ON u.id=m.user_id
        WHERE m.tenant_id=target AND m.user_id=NULLIF(current_setting('silicon.user_id',true),'')::uuid
        AND m.active AND u.active)
    $$;
    ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
    ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
    CREATE POLICY audit_read ON audit_events FOR SELECT USING (tenant_visible(tenant_id));
    CREATE POLICY audit_append ON audit_events FOR INSERT WITH CHECK (true);
    ALTER TABLE jobs ADD COLUMN tenant_id uuid, ADD COLUMN actor_id uuid, ADD COLUMN request_id text;
    ALTER TABLE jobs ADD CONSTRAINT jobs_membership FOREIGN KEY(tenant_id,actor_id) REFERENCES memberships(tenant_id,user_id);
    ALTER TABLE jobs ADD CONSTRAINT jobs_context CHECK ((tenant_id IS NULL) = (actor_id IS NULL));
    GRANT SELECT ON identity_users,tenants,memberships,roles,permissions,role_permissions TO silicon_app;
    GRANT INSERT ON identity_users TO silicon_app;
    GRANT SELECT,INSERT,UPDATE,DELETE ON sessions,login_attempts TO silicon_app;
    GRANT SELECT,INSERT ON audit_events TO silicon_app;
    ''')


def downgrade():
    op.execute('''ALTER TABLE jobs DROP CONSTRAINT jobs_membership, DROP CONSTRAINT jobs_context,
      DROP COLUMN tenant_id, DROP COLUMN actor_id, DROP COLUMN request_id;
      DROP TABLE audit_events;
      DROP FUNCTION tenant_visible(uuid),lock_membership(uuid,uuid);
      DROP TABLE sessions,login_attempts,memberships,role_permissions,permissions,roles,tenants,identity_users;''')
