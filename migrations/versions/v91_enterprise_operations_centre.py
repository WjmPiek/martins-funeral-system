"""Enterprise Operations Centre

Revision ID: v91_ops_centre
Revises: v90_perf_cache
Create Date: 2026-07-02
"""
from alembic import op

revision = 'v91_ops_centre'
down_revision = 'v90_perf_cache'
branch_labels = None
depends_on = None


def upgrade():
    # Phase 6 is mostly application/UI, but these indexes keep the operations
    # centre fast on live production data.
    op.execute("CREATE INDEX IF NOT EXISTS ix_import_jobs_status_started ON import_jobs (status, started_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_import_jobs_created_by_started ON import_jobs (created_by_id, started_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_live_events_created_kind ON live_events (created_at DESC, kind)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_live_notifications_created_user ON live_notifications (created_at DESC, user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_created_module ON audit_logs (created_at DESC, module)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_created_module")
    op.execute("DROP INDEX IF EXISTS ix_live_notifications_created_user")
    op.execute("DROP INDEX IF EXISTS ix_live_events_created_kind")
    op.execute("DROP INDEX IF EXISTS ix_import_jobs_created_by_started")
    op.execute("DROP INDEX IF EXISTS ix_import_jobs_status_started")
