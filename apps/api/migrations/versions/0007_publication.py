"""Immutable approval/issue facts and separate lifecycle state."""
from alembic import op
revision='0007_publication'
down_revision='0006_quotes'
branch_labels=depends_on=None
TABLES=['publication_policies','publication_candidates','publication_decisions','quote_versions','quote_version_states','publication_events','contract_drafts','publication_commands']

def upgrade():
    op.execute('''
    INSERT INTO permissions VALUES ('quote.submit'),('quote.approve'),('quote.issue'),('quote.withdraw'),('contract.read'),('contract.create');
    INSERT INTO role_permissions SELECT 'admin',name FROM permissions WHERE name IN ('quote.submit','quote.approve','quote.issue','quote.withdraw','contract.read','contract.create');
    INSERT INTO role_permissions VALUES ('member','quote.submit'),('member','contract.read'),('member','contract.create'),('viewer','contract.read');
    CREATE TABLE publication_policies(
      tenant_id uuid REFERENCES tenants,id uuid,version int NOT NULL CHECK(version>0),enabled boolean NOT NULL,
      mode text NOT NULL CHECK(mode IN ('development','formal')),allow_risks boolean NOT NULL,
      responsibility text NOT NULL CHECK(length(trim(responsibility))>0),discount_quota text NOT NULL CHECK(discount_quota IN ('unlimited','limited')),
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,version));
    CREATE UNIQUE INDEX one_active_publication_policy ON publication_policies(tenant_id) WHERE enabled;
    CREATE TABLE publication_candidates(
      tenant_id uuid,id uuid,draft_id uuid NOT NULL,draft_version int NOT NULL,submitter_id uuid NOT NULL,
      policy_id uuid NOT NULL,content_hash text NOT NULL,content jsonb NOT NULL,valid_until timestamptz NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(tenant_id,id),
      FOREIGN KEY(tenant_id,draft_id) REFERENCES quote_drafts(tenant_id,id),
      FOREIGN KEY(tenant_id,submitter_id) REFERENCES memberships(tenant_id,user_id),
      FOREIGN KEY(tenant_id,policy_id) REFERENCES publication_policies(tenant_id,id));
    CREATE TABLE publication_decisions(
      tenant_id uuid,id uuid,candidate_id uuid NOT NULL,actor_id uuid NOT NULL,approved boolean NOT NULL,
      note text NOT NULL CHECK(length(trim(note))>0),confirmations jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,candidate_id),
      FOREIGN KEY(tenant_id,candidate_id) REFERENCES publication_candidates(tenant_id,id),
      FOREIGN KEY(tenant_id,actor_id) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE quote_versions(
      tenant_id uuid,id uuid,candidate_id uuid NOT NULL,draft_id uuid NOT NULL,decision_id uuid NOT NULL,
      number text NOT NULL,revision int NOT NULL CHECK(revision>0),content_hash text NOT NULL,content jsonb NOT NULL,
      issuer_id uuid NOT NULL,issued_at timestamptz NOT NULL,valid_until timestamptz NOT NULL,
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,candidate_id),UNIQUE(tenant_id,number),
      FOREIGN KEY(tenant_id,candidate_id) REFERENCES publication_candidates(tenant_id,id),
      FOREIGN KEY(tenant_id,draft_id) REFERENCES quote_drafts(tenant_id,id),
      FOREIGN KEY(tenant_id,decision_id) REFERENCES publication_decisions(tenant_id,id),
      FOREIGN KEY(tenant_id,issuer_id) REFERENCES memberships(tenant_id,user_id),CHECK(valid_until>issued_at));
    CREATE TABLE quote_version_states(
      tenant_id uuid,id uuid,version int NOT NULL DEFAULT 1,withdrawn boolean NOT NULL DEFAULT false,
      PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,id) REFERENCES quote_versions(tenant_id,id));
    CREATE TABLE publication_events(
      tenant_id uuid,id uuid,quote_version_id uuid NOT NULL,actor_id uuid NOT NULL,action text NOT NULL,reason text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(tenant_id,id),
      FOREIGN KEY(tenant_id,quote_version_id) REFERENCES quote_versions(tenant_id,id),FOREIGN KEY(tenant_id,actor_id) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE contract_drafts(
      tenant_id uuid,id uuid,quote_version_id uuid NOT NULL,source_hash text NOT NULL,content jsonb NOT NULL,
      created_by uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,quote_version_id),
      FOREIGN KEY(tenant_id,quote_version_id) REFERENCES quote_versions(tenant_id,id),FOREIGN KEY(tenant_id,created_by) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE publication_commands(
      tenant_id uuid,actor_id uuid,operation text,key text,request_hash text NOT NULL,response_id uuid NOT NULL,
      PRIMARY KEY(tenant_id,actor_id,operation,key),FOREIGN KEY(tenant_id,actor_id) REFERENCES memberships(tenant_id,user_id));
    ALTER TABLE quote_drafts ADD COLUMN approval_candidate_id uuid;
    ALTER TABLE quote_drafts ADD FOREIGN KEY(tenant_id,approval_candidate_id) REFERENCES publication_candidates(tenant_id,id);
    ALTER TABLE quote_drafts ADD COLUMN source_version_id uuid;
    ALTER TABLE quote_drafts ADD FOREIGN KEY(tenant_id,source_version_id) REFERENCES quote_versions(tenant_id,id);
    CREATE FUNCTION publication_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'immutable publication fact' USING ERRCODE='23514'; END $$;
    ''')
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY; ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_isolation ON {table} USING(tenant_visible(tenant_id)) WITH CHECK(tenant_visible(tenant_id))')
        op.execute(f'GRANT SELECT ON {table} TO silicon_app')
        if table!='publication_policies':op.execute(f'GRANT INSERT ON {table} TO silicon_app')
        if table not in ('publication_policies','quote_version_states'):
            op.execute(f'CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION publication_immutable()')
    op.execute('GRANT UPDATE ON quote_version_states TO silicon_app')

def downgrade():
    op.execute('ALTER TABLE quote_drafts DROP COLUMN source_version_id, DROP COLUMN approval_candidate_id')
    for table in reversed(TABLES):op.execute(f'DROP TABLE {table}')
    op.execute('DROP FUNCTION publication_immutable()')
    op.execute("DELETE FROM role_permissions WHERE permission IN ('quote.submit','quote.approve','quote.issue','quote.withdraw','contract.read','contract.create'); DELETE FROM permissions WHERE name IN ('quote.submit','quote.approve','quote.issue','quote.withdraw','contract.read','contract.create')")
