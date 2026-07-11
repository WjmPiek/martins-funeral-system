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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("franchises"):
        return
    # All existing franchises enter the approval queue once. Source records remain
    # untouched; only participation in operational calculations is disabled.
    bind.execute(sa.text("UPDATE franchises SET is_performance_active = FALSE, performance_inactive_reason = 'Awaiting Head Office activation', performance_inactive_at = CURRENT_TIMESTAMP"))
    # Disable franchise-owner and child accounts until their linked branch is approved.
    if inspector.has_table("users") and inspector.has_table("roles") and inspector.has_table("user_roles"):
        bind.execute(sa.text("""
            UPDATE users SET is_active_account = FALSE, deactivation_reason = 'Potential franchise awaiting Head Office activation', deactivated_at = CURRENT_TIMESTAMP
            WHERE id IN (
                SELECT DISTINCT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id
                WHERE r.name IN ('Franchise User','Franchise Manager','Franchise Employee','Franchise Agent')
            )
        """))
    # Remove derived operational output so potential data cannot remain visible from
    # a previous cache/snapshot. Raw monthly figures and master data are preserved.
    for table in (
        "performance_page_cache", "performance_results", "franchise_health_snapshots",
        "business_insights", "insight_narratives", "royalty_calculation_snapshots"
    ):
        if inspector.has_table(table):
            bind.execute(sa.text(f"DELETE FROM {table}"))

def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE franchises SET is_performance_active = TRUE WHERE is_performance_active = FALSE"))
