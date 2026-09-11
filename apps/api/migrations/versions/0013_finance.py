"""Explicit finance facts, allocations and immutable inverse records."""
from alembic import op
revision='0013_finance'
down_revision='0012_delivery'
branch_labels=depends_on=None
TABLES=['fin_plans','fin_cash','fin_adjustments','fin_releases','fin_allocations','fin_refunds','fin_invoices','fin_invoice_lines','fin_reversals','fin_source_adjustments','fin_commands']
PERMISSIONS=['finance.read','finance.plan','finance.confirm','finance.cash','finance.allocate','finance.correct','finance.invoice']
PARTY="""direction text NOT NULL CHECK(direction IN ('receivable','payable')),customer_id uuid,supplier_id uuid,
 party_id uuid GENERATED ALWAYS AS (coalesce(customer_id,supplier_id)) STORED,
 FOREIGN KEY(tenant_id,customer_id) REFERENCES crm_customers(tenant_id,id),FOREIGN KEY(tenant_id,supplier_id) REFERENCES inv_suppliers(tenant_id,id),
 CHECK((direction='receivable' AND customer_id IS NOT NULL AND supplier_id IS NULL) OR (direction='payable' AND supplier_id IS NOT NULL AND customer_id IS NULL))"""
SOURCE="""sales_contract_id uuid,purchase_contract_id uuid,source_id uuid GENERATED ALWAYS AS(coalesce(sales_contract_id,purchase_contract_id)) STORED,
 FOREIGN KEY(tenant_id,sales_contract_id) REFERENCES signed_contracts(tenant_id,id),FOREIGN KEY(tenant_id,purchase_contract_id) REFERENCES inv_contracts(tenant_id,id),
 CHECK((direction='receivable' AND sales_contract_id IS NOT NULL AND purchase_contract_id IS NULL) OR (direction='payable' AND purchase_contract_id IS NOT NULL AND sales_contract_id IS NULL))"""
STATE="state text NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','confirmed','cancelled')),version int NOT NULL DEFAULT 1 CHECK(version>0)"
def upgrade():
    for p in PERMISSIONS:op.execute(f"INSERT INTO permissions VALUES ('{p}');INSERT INTO role_permissions VALUES ('admin','{p}')")
    op.execute(f"""
 CREATE TABLE fin_plans(tenant_id uuid,id uuid,PRIMARY KEY(tenant_id,id),{PARTY},{SOURCE},{STATE},
 node text NOT NULL,amount numeric(18,2) NOT NULL CHECK(amount>0),currency text NOT NULL CHECK(currency='CNY'),due_date date,
 retention bool NOT NULL,release_condition text NOT NULL,order_id uuid,purchase_order_id uuid,
 notes text NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(tenant_id,id,direction,party_id),FOREIGN KEY(tenant_id,order_id) REFERENCES sales_orders(tenant_id,id),FOREIGN KEY(tenant_id,purchase_order_id) REFERENCES inv_orders(tenant_id,id));
 CREATE UNIQUE INDEX fin_plan_node ON fin_plans(tenant_id,direction,source_id,node) WHERE state<>'cancelled';
 CREATE TABLE fin_cash(tenant_id uuid,id uuid,PRIMARY KEY(tenant_id,id),{PARTY},{STATE},amount numeric(18,2) NOT NULL CHECK(amount>0),currency text NOT NULL CHECK(currency='CNY'),
 purpose text NOT NULL CHECK(purpose IN ('unallocated','advance')),occurred_at timestamptz NOT NULL,method text NOT NULL,account text NOT NULL,external_ref text NOT NULL,notes text NOT NULL,
 actor_id uuid NOT NULL REFERENCES identity_users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(tenant_id,id,direction,party_id));
 CREATE UNIQUE INDEX fin_cash_external ON fin_cash(tenant_id,account,direction,external_ref) WHERE state='confirmed' AND external_ref<>'';
 CREATE TABLE fin_adjustments(tenant_id uuid,id uuid,PRIMARY KEY(tenant_id,id),plan_id uuid NOT NULL,amount numeric(18,2) NOT NULL CHECK(amount<>0),reason text NOT NULL,basis_ref text NOT NULL,return_id uuid,
 actor_id uuid NOT NULL REFERENCES identity_users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(tenant_id,plan_id) REFERENCES fin_plans(tenant_id,id),FOREIGN KEY(tenant_id,return_id) REFERENCES del_returns(tenant_id,id),UNIQUE(tenant_id,return_id),UNIQUE(tenant_id,plan_id,basis_ref));
 CREATE TABLE fin_releases(tenant_id uuid,id uuid,PRIMARY KEY(tenant_id,id),plan_id uuid NOT NULL,due_date date NOT NULL,reason text NOT NULL,actor_id uuid NOT NULL REFERENCES identity_users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(tenant_id,plan_id) REFERENCES fin_plans(tenant_id,id),UNIQUE(tenant_id,plan_id));
 CREATE TABLE fin_allocations(tenant_id uuid,id uuid,PRIMARY KEY(tenant_id,id),cash_id uuid NOT NULL,plan_id uuid NOT NULL,direction text NOT NULL,party_id uuid NOT NULL,
 amount numeric(18,2) NOT NULL CHECK(amount>0),actor_id uuid NOT NULL REFERENCES identity_users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(tenant_id,cash_id,direction,party_id) REFERENCES fin_cash(tenant_id,id,direction,party_id),FOREIGN KEY(tenant_id,plan_id,direction,party_id) REFERENCES fin_plans(tenant_id,id,direction,party_id));
 CREATE TABLE fin_refunds(tenant_id uuid,id uuid,PRIMARY KEY(tenant_id,id),cash_id uuid NOT NULL,{STATE},amount numeric(18,2) NOT NULL CHECK(amount>0),occurred_at timestamptz NOT NULL,account text NOT NULL,external_ref text NOT NULL,reason text NOT NULL,
 actor_id uuid NOT NULL REFERENCES identity_users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),FOREIGN KEY(tenant_id,cash_id) REFERENCES fin_cash(tenant_id,id));
 CREATE UNIQUE INDEX fin_refund_external ON fin_refunds(tenant_id,account,external_ref) WHERE state='confirmed' AND external_ref<>'';
 CREATE TABLE fin_invoices(tenant_id uuid,id uuid,PRIMARY KEY(tenant_id,id),{PARTY},{STATE},number text NOT NULL,kind text NOT NULL,issued_on date NOT NULL,buyer text NOT NULL,seller text NOT NULL,currency text NOT NULL CHECK(currency='CNY'),
 amount numeric(18,2) NOT NULL CHECK(amount>0),net_amount numeric(18,2),tax_amount numeric(18,2),original_id uuid,notes text NOT NULL,archive_ref text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),FOREIGN KEY(tenant_id,original_id) REFERENCES fin_invoices(tenant_id,id),
 CHECK((net_amount IS NULL AND tax_amount IS NULL) OR (net_amount IS NOT NULL AND tax_amount IS NOT NULL AND net_amount>=0 AND tax_amount>=0 AND net_amount+tax_amount=amount)));
 CREATE UNIQUE INDEX fin_invoice_number ON fin_invoices(tenant_id,direction,number) WHERE state='confirmed';
 CREATE TABLE fin_invoice_lines(tenant_id uuid,id uuid,PRIMARY KEY(tenant_id,id),invoice_id uuid NOT NULL,direction text NOT NULL,{SOURCE},amount numeric(18,2) NOT NULL CHECK(amount>0),
 FOREIGN KEY(tenant_id,invoice_id) REFERENCES fin_invoices(tenant_id,id),UNIQUE(tenant_id,invoice_id,direction,source_id));
 CREATE TABLE fin_reversals(tenant_id uuid,id uuid,PRIMARY KEY(tenant_id,id),allocation_id uuid,cash_id uuid,refund_id uuid,invoice_id uuid,
 reason text NOT NULL,actor_id uuid NOT NULL REFERENCES identity_users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(num_nonnulls(allocation_id,cash_id,refund_id,invoice_id)=1),
 FOREIGN KEY(tenant_id,allocation_id) REFERENCES fin_allocations(tenant_id,id),FOREIGN KEY(tenant_id,cash_id) REFERENCES fin_cash(tenant_id,id),
 FOREIGN KEY(tenant_id,refund_id) REFERENCES fin_refunds(tenant_id,id),FOREIGN KEY(tenant_id,invoice_id) REFERENCES fin_invoices(tenant_id,id),
 UNIQUE(tenant_id,allocation_id),UNIQUE(tenant_id,cash_id),UNIQUE(tenant_id,refund_id),UNIQUE(tenant_id,invoice_id));
 CREATE TABLE fin_source_adjustments(tenant_id uuid,id uuid,PRIMARY KEY(tenant_id,id),direction text NOT NULL,{SOURCE},amount numeric(18,2) NOT NULL CHECK(amount<>0),
 basis_ref text NOT NULL,reason text NOT NULL,actor_id uuid NOT NULL REFERENCES identity_users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(tenant_id,direction,source_id,basis_ref));
 CREATE TABLE fin_commands(tenant_id uuid,actor_id uuid REFERENCES identity_users(id),operation text,key text,request_hash text NOT NULL,response jsonb NOT NULL,PRIMARY KEY(tenant_id,actor_id,operation,key));
 CREATE FUNCTION fin_parent_frozen() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(NEW)-'version'-'state'-'party_id'-'source_id')<>(to_jsonb(OLD)-'version'-'state'-'party_id'-'source_id') OR (OLD.state<>'draft' AND NEW.state<>OLD.state) THEN RAISE EXCEPTION 'frozen finance fact' USING ERRCODE='23514'; END IF;RETURN NEW;END $$;
 """)
    for t in TABLES:
        op.execute(f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;ALTER TABLE {t} FORCE ROW LEVEL SECURITY;CREATE POLICY tenant_isolation ON {t} USING(tenant_visible(tenant_id)) WITH CHECK(tenant_visible(tenant_id));GRANT SELECT,INSERT ON {t} TO silicon_app')
        mutable=t in ('fin_plans','fin_cash','fin_refunds','fin_invoices')
        op.execute(f"CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION {'fin_parent_frozen' if mutable else 'publication_immutable'}()")
        if mutable:op.execute(f'GRANT UPDATE ON {t} TO silicon_app')
def downgrade():
    for t in TABLES:op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY;DO $$ BEGIN IF EXISTS(SELECT 1 FROM {t}) THEN RAISE EXCEPTION 'finance history prevents downgrade';END IF;END $$")
    for t in reversed(TABLES):op.execute(f'DROP TABLE {t}')
    op.execute('DROP FUNCTION fin_parent_frozen()')
    for p in PERMISSIONS:op.execute(f"DELETE FROM role_permissions WHERE permission='{p}';DELETE FROM permissions WHERE name='{p}'")
