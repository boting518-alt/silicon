"""Opaque session context changes on every explicit tenant selection, including A/B/A."""
from alembic import op
revision='0004_session_context'
down_revision='0003_crm'
branch_labels=depends_on=None


def upgrade():
    op.execute('ALTER TABLE sessions ADD COLUMN context_id uuid NOT NULL DEFAULT gen_random_uuid()')


def downgrade():
    op.execute('ALTER TABLE sessions DROP COLUMN context_id')
