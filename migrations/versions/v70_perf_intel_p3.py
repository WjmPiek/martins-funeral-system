"""Performance Intelligence Phase 3 annual budget builder

Revision ID: v70_perf_intel_p3
Revises: v69_perf_intel_p2
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "v70_perf_intel_p3"
down_revision = "v69_perf_intel_p2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Phase 3 uses the existing franchise_targets table for generated monthly budgets.
    # Keep this migration intentionally light and safe for existing PostgreSQL data.
    bind.execute(sa.text("SELECT 1"))


def downgrade():
    pass
