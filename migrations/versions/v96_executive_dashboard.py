"""Executive dashboard

Revision ID: v96_exec_dashboard
Revises: v95_royalty_mgmt
Create Date: 2026-07-02
"""
from alembic import op

revision = "v96_exec_dashboard"
down_revision = "v95_royalty_mgmt"
branch_labels = None
depends_on = None


def upgrade():
    # Phase marker migration. The executive dashboard reads existing operational,
    # royalty, event, cache and import tables and does not require new schema.
    op.execute("SELECT 1")


def downgrade():
    op.execute("SELECT 1")
