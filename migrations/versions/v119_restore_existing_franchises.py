"""Restore existing franchises after potential-franchise rollout

Revision ID: v119_restore_existing_franchises
Revises: v118_potential_franchise_activation
"""
from alembic import op
import sqlalchemy as sa

revision = "v119_restore_existing_franchises"
down_revision = "v118_potential_franchise_activation"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("franchises"):
        # Restore only rows moved by the V118 bulk rollout. Franchises that Head
        # Office later moved to Potential Franchises keep their manual status.
        bind.execute(sa.text("""
            UPDATE franchises
               SET is_performance_active = TRUE,
                   performance_inactive_at = NULL,
                   performance_inactive_reason = '',
                   performance_reactivated_at = CURRENT_TIMESTAMP
             WHERE is_performance_active = FALSE
               AND performance_inactive_reason = 'Awaiting Head Office activation'
        """))

    if inspector.has_table("users"):
        # Restore only accounts disabled by V118. Do not reactivate users that
        # were disabled for any other business or security reason.
        bind.execute(sa.text("""
            UPDATE users
               SET is_active = TRUE,
                   is_active_account = TRUE,
                   deactivated_at = NULL,
                   deactivation_reason = ''
             WHERE deactivation_reason = 'Potential franchise awaiting Head Office activation'
        """))


def downgrade():
    # Deliberately non-destructive. Rolling back this repair must not hide live
    # franchises or disable users again.
    pass
