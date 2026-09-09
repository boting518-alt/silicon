"""Platform smoke jobs and outbox foundation, without tenant business data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0001_platform"
down_revision = "0000_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False, unique=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_token", UUID(as_uuid=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("result", JSONB()),
        sa.Column("error_code", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('queued','running','completed','failed')", name="jobs_status"),
        sa.CheckConstraint("attempts >= 0 AND max_attempts > 0 AND attempts <= max_attempts", name="jobs_attempts"),
        sa.CheckConstraint("(status = 'running') = (lease_token IS NOT NULL AND lease_until IS NOT NULL)", name="jobs_lease"),
    )
    op.create_index("jobs_claim", "jobs", ["status", "available_at", "created_at"])
    op.create_table(
        "outbox_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    # The application role is provisioned separately; it cannot migrate or own tables.
    op.execute("GRANT SELECT, INSERT, UPDATE ON jobs, outbox_events TO silicon_app")
    op.execute("GRANT SELECT ON alembic_version TO silicon_app")


def downgrade():
    op.drop_table("outbox_events")
    op.drop_table("jobs")
