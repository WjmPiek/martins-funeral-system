"""Enterprise event bus

Revision ID: v94_event_bus
Revises: v93_worker_heartbeat
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "v94_event_bus"
down_revision = "v93_worker_heartbeat"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("title", sa.String(length=180), nullable=False, server_default=""),
        sa.Column("message", sa.String(length=800), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("correlation_id", sa.String(length=120), nullable=True),
        sa.Column("aggregate_type", sa.String(length=80), nullable=True),
        sa.Column("aggregate_id", sa.Integer(), nullable=True),
        sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("import_jobs.id"), nullable=True),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error_json", sa.Text(), nullable=False, server_default=""),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("available_at", sa.DateTime(), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    for col in ["event_type", "source", "status", "priority", "correlation_id", "aggregate_type", "aggregate_id", "import_job_id", "franchise_id", "user_id", "year", "month", "available_at", "locked_at", "locked_by", "processed_at", "created_at"]:
        op.create_index(f"ix_system_events_{col}", "system_events", [col])

    op.create_table(
        "event_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("handler", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_event_subscriptions_name", "event_subscriptions", ["name"], unique=True)
    op.create_index("ix_event_subscriptions_event_type", "event_subscriptions", ["event_type"])
    op.create_index("ix_event_subscriptions_is_active", "event_subscriptions", ["is_active"])

    op.create_table(
        "event_processing_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("system_event_id", sa.Integer(), sa.ForeignKey("system_events.id"), nullable=False),
        sa.Column("handler", sa.String(length=160), nullable=False, server_default="event_bus"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="info"),
        sa.Column("message", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("data_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    for col in ["system_event_id", "handler", "status", "created_at"]:
        op.create_index(f"ix_event_processing_logs_{col}", "event_processing_logs", [col])

    # Seed visible subscription registry used by Operations Centre.
    op.execute("""
        INSERT INTO event_subscriptions (name, event_type, handler, description, is_active)
        VALUES
        ('import-publishing', 'monthly_import_published', 'live.publish_monthly_import', 'Refresh users after month-end figures are published.', true),
        ('trusted-financials', 'trusted_financials_published', 'live.publish_trusted_financials', 'Refresh dashboards after royalties and cache are trusted.', true),
        ('job-completed', 'job.completed', 'jobs', 'Record completed background jobs.', true),
        ('job-failed', 'job.failed', 'jobs', 'Record failed background jobs for Operations Centre.', true),
        ('cache-rebuilt', 'cache.rebuilt', 'performance.cache', 'Record performance cache rebuilds.', true),
        ('attendance-updated', 'attendance.updated', 'attendance', 'Future hook for Attendance module live sync.', true),
        ('claim-created', 'claim.created', 'insurance_claims', 'Future hook for Claims module live sync.', true)
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade():
    op.drop_table("event_processing_logs")
    op.drop_table("event_subscriptions")
    op.drop_table("system_events")
