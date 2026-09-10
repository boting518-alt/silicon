"""Contract workspace alongside immutable source, signed facts and private attachments."""
from alembic import op
revision='0008_contracts'
down_revision='0007_publication'
branch_labels=depends_on=None
TABLES=['contract_workspaces','contract_payments','contract_files','signed_contracts','signed_files','sales_orders','contract_editions','contract_commands']
def upgrade():
    op.execute('''
    INSERT INTO permissions VALUES ('contract.write'),('contract.sign'),('contract.download'),('contract.contact');
    INSERT INTO role_permissions SELECT 'admin',name FROM permissions WHERE name LIKE 'contract.%' ON CONFLICT DO NOTHING;
    INSERT INTO role_permissions VALUES ('member','contract.write'),('member','contract.download'),('member','contract.contact'),('viewer','contract.download');
    CREATE TABLE contract_workspaces(tenant_id uuid,id uuid,version int NOT NULL CHECK(version>0),number text,fields jsonb NOT NULL,sales_id uuid,support_id uuid,
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,number),FOREIGN KEY(tenant_id,id) REFERENCES contract_drafts(tenant_id,id),FOREIGN KEY(tenant_id,sales_id) REFERENCES memberships(tenant_id,user_id),FOREIGN KEY(tenant_id,support_id) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE contract_payments(tenant_id uuid,contract_id uuid,id uuid,position int NOT NULL,amount numeric(18,2) NOT NULL CHECK(amount>0),body jsonb NOT NULL,
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,contract_id,position),FOREIGN KEY(tenant_id,contract_id) REFERENCES contract_workspaces(tenant_id,id));
    CREATE TABLE contract_files(tenant_id uuid,id uuid,contract_id uuid NOT NULL,storage_id uuid NOT NULL UNIQUE,name text NOT NULL,media_type text NOT NULL,
      size bigint NOT NULL CHECK(size>0),sha256 text NOT NULL CHECK(length(sha256)=64),category text NOT NULL CHECK(category IN ('contract','proof','technical','other')),
      supplemental boolean NOT NULL DEFAULT false,state text NOT NULL CHECK(state IN ('pending','linked','deleted')),uploaded_by uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,contract_id) REFERENCES contract_drafts(tenant_id,id),FOREIGN KEY(tenant_id,uploaded_by) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE signed_contracts(tenant_id uuid,id uuid,contract_id uuid NOT NULL,number text NOT NULL,version int NOT NULL,content_hash text NOT NULL,content jsonb NOT NULL,
      quote_version_id uuid NOT NULL,registered_by uuid NOT NULL,registered_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,contract_id),UNIQUE(tenant_id,number),FOREIGN KEY(tenant_id,contract_id) REFERENCES contract_drafts(tenant_id,id),
      FOREIGN KEY(tenant_id,quote_version_id) REFERENCES quote_versions(tenant_id,id),FOREIGN KEY(tenant_id,registered_by) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE signed_files(tenant_id uuid,contract_version_id uuid,file_id uuid,
      PRIMARY KEY(tenant_id,contract_version_id,file_id),FOREIGN KEY(tenant_id,contract_version_id) REFERENCES signed_contracts(tenant_id,id),FOREIGN KEY(tenant_id,file_id) REFERENCES contract_files(tenant_id,id));
    CREATE TABLE sales_orders(tenant_id uuid,id uuid,contract_version_id uuid NOT NULL,quote_version_id uuid NOT NULL,number text NOT NULL,amount numeric(18,2) NOT NULL CHECK(amount>=0),
      currency text NOT NULL CHECK(currency='CNY'),state text NOT NULL CHECK(state='pending_fulfillment'),content jsonb NOT NULL,
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,contract_version_id),UNIQUE(tenant_id,number),FOREIGN KEY(tenant_id,contract_version_id) REFERENCES signed_contracts(tenant_id,id),
      FOREIGN KEY(tenant_id,quote_version_id) REFERENCES quote_versions(tenant_id,id));
    CREATE TABLE contract_editions(tenant_id uuid,id uuid,contract_id uuid NOT NULL,version int NOT NULL,fields jsonb NOT NULL,actor_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,contract_id,version),FOREIGN KEY(tenant_id,contract_id) REFERENCES contract_drafts(tenant_id,id),FOREIGN KEY(tenant_id,actor_id) REFERENCES memberships(tenant_id,user_id));
    CREATE TABLE contract_commands(tenant_id uuid,actor_id uuid,operation text,key text,request_hash text NOT NULL,response_id uuid NOT NULL,
      PRIMARY KEY(tenant_id,actor_id,operation,key),FOREIGN KEY(tenant_id,actor_id) REFERENCES memberships(tenant_id,user_id));
    CREATE FUNCTION contract_protection() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_TABLE_NAME='contract_workspaces' THEN IF EXISTS(SELECT 1 FROM signed_contracts WHERE tenant_id=OLD.tenant_id AND contract_id=OLD.id) THEN RAISE EXCEPTION 'signed contract' USING ERRCODE='23514'; END IF; END IF;
      IF TG_TABLE_NAME='contract_payments' THEN IF EXISTS(SELECT 1 FROM signed_contracts WHERE tenant_id=OLD.tenant_id AND contract_id=OLD.contract_id) THEN RAISE EXCEPTION 'signed payment' USING ERRCODE='23514'; END IF; END IF;
      IF TG_TABLE_NAME='contract_files' THEN
        IF TG_OP='DELETE' OR (to_jsonb(NEW)-'state')<>(to_jsonb(OLD)-'state') OR EXISTS(SELECT 1 FROM signed_files WHERE tenant_id=OLD.tenant_id AND file_id=OLD.id) THEN RAISE EXCEPTION 'immutable attachment' USING ERRCODE='23514'; END IF;
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$;
    ''')
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY; ALTER TABLE {table} FORCE ROW LEVEL SECURITY; CREATE POLICY tenant_isolation ON {table} USING(tenant_visible(tenant_id)) WITH CHECK(tenant_visible(tenant_id)); GRANT SELECT,INSERT ON {table} TO silicon_app')
        function='contract_protection' if table in TABLES[:3] else 'publication_immutable'
        op.execute(f'CREATE TRIGGER contract_guard BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION {function}()')
    op.execute('GRANT UPDATE ON contract_workspaces,contract_files TO silicon_app; GRANT DELETE ON contract_payments TO silicon_app')
def downgrade():
    for table in reversed(TABLES):op.execute(f'DROP TABLE {table}')
    op.execute('DROP FUNCTION contract_protection()')
    op.execute("DELETE FROM role_permissions WHERE permission IN ('contract.write','contract.sign','contract.download','contract.contact'); DELETE FROM permissions WHERE name IN ('contract.write','contract.sign','contract.download','contract.contact')")
