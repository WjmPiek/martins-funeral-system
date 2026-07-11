"""Potential franchise activation lifecycle

Revision ID: v118_potential_franchise_activation
Revises: v107_master_import_source_of_truth
"""
from alembic import op
import sqlalchemy as sa

revision = "v118_potential_franchise_activation"
down_revision = "v107_master_import_source_of_truth"
branch_labels = None
depends_on = None

def upgrade():
    # Lifecycle support only. Existing franchises and users remain active.
    # A franchise enters Potential Franchises only through an explicit Head
    # Office action or the controlled creation workflow. No raw or derived data
    # is deleted by this migration.
    return

def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE franchises SET is_performance_active = TRUE WHERE is_performance_active = FALSE"))
