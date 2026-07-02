"""Live publishing refresh indexes

Revision ID: v89_live_refresh
Revises: v88_live_system
Create Date: 2026-07-02
"""
from alembic import op

revision = 'v89_live_refresh'
down_revision = 'v88_live_system'
branch_labels = None
depends_on = None


def upgrade():
    # Speed up the live refresh checks used after month-end imports.
    op.execute("CREATE INDEX IF NOT EXISTS ix_monthly_figures_live_status_period ON monthly_figures (status, year, month)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_monthly_figures_live_updated ON monthly_figures (updated_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_live_notifications_user_unread ON live_notifications (user_id, read_at, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_live_events_refresh_lookup ON live_events (visibility, year, month, created_at DESC)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_live_events_refresh_lookup")
    op.execute("DROP INDEX IF EXISTS ix_live_notifications_user_unread")
    op.execute("DROP INDEX IF EXISTS ix_monthly_figures_live_updated")
    op.execute("DROP INDEX IF EXISTS ix_monthly_figures_live_status_period")
