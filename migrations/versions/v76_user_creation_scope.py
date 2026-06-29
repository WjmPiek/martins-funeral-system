"""v76 user creation scope repair

Revision ID: v76_user_creation_scope
Revises: v74_franchise_employees
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "v76_user_creation_scope"
down_revision = "v74_franchise_employees"
branch_labels = None
depends_on = None

ADMIN_SIDE_ROLES = ("Admin", "Finance Manager", "Finance Assistant")


def upgrade():
    bind = op.get_bind()

    for role_name, description in [
        ("Finance Manager", "Martins Funerals South Africa finance manager"),
        ("Finance Assistant", "Martins Funerals South Africa finance assistant"),
        ("Regional Manager", "Martins regional manager linked to selected franchises"),
        ("Franchise User", "Franchise owner/user linked to selected franchise data"),
        ("Franchise Manager", "Manager created by a franchise user"),
        ("Franchise Employee", "Employee created by a franchise user"),
        ("Franchise Agent", "Agent created by a franchise user"),
    ]:
        bind.execute(sa.text("""
            INSERT INTO roles (name, description, is_system_role, created_at)
            SELECT :name, :description, TRUE, NOW()
            WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = :name)
        """), {"name": role_name, "description": description})

    # Admin/finance-side users must never be children of franchise users.
    bind.execute(sa.text("""
        UPDATE users
        SET parent_franchise_user_id = NULL
        WHERE id IN (
            SELECT ur.user_id
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE r.name IN ('Admin', 'Finance Manager', 'Finance Assistant')
        )
    """))

    # Remove accidental franchise links from Admin/Finance Manager/Finance Assistant users.
    bind.execute(sa.text("""
        DELETE FROM user_franchises uf
        USING user_roles ur, roles r
        WHERE uf.user_id = ur.user_id
          AND ur.role_id = r.id
          AND r.name IN ('Admin', 'Finance Manager', 'Finance Assistant')
    """))


def downgrade():
    pass
