"""v76 user creation scope repair

Revision ID: v76_user_creation_scope
Revises: v75_user_scope_ui
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "v76_user_creation_scope"
down_revision = "v75_user_scope_ui"
branch_labels = None
depends_on = None

ADMIN_SIDE_ROLES = ("Admin", "Finance Manager", "Finance Assistant")


def upgrade():
    bind = op.get_bind()

    # Admin/finance-side users must never be children of franchise users.
    bind.execute(sa.text("""
        UPDATE users
        SET parent_franchise_user_id = NULL
        WHERE id IN (
            SELECT ur.user_id
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE r.name IN :admin_roles
        )
    """), {"admin_roles": ADMIN_SIDE_ROLES})

    # Remove accidental franchise links from Admin/Finance Manager/Finance Assistant users.
    bind.execute(sa.text("""
        DELETE FROM user_franchises uf
        USING user_roles ur, roles r
        WHERE uf.user_id = ur.user_id
          AND ur.role_id = r.id
          AND r.name IN :admin_roles
    """), {"admin_roles": ADMIN_SIDE_ROLES})


def downgrade():
    pass
