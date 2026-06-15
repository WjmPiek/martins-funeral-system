"""fix users by franchise grouping and role display v1.5

Revision ID: fix_users_by_franchise_v15
Revises: fix_role_permissions_v14
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "fix_users_by_franchise_v15"
down_revision = "fix_role_permissions_v14"
branch_labels = None
depends_on = None


def _role_id(conn, name):
    row = conn.execute(sa.text("SELECT id FROM roles WHERE name = :name"), {"name": name}).fetchone()
    return row.id if row else None


def upgrade():
    conn = op.get_bind()
    finance_admin_users = {
        "renette@martinsdirect.com": "Finance Manager",
        "lowhaan@martinsdirect.com": "Finance Assistant",
        "deon@martinsdirect.com": "Finance Assistant",
    }
    franchise_role_ids = [row.id for row in conn.execute(sa.text(
        "SELECT id FROM roles WHERE name IN ('Franchise User', 'Franchise Manager', 'Read Only User')"
    )).fetchall()]

    for email, role_name in finance_admin_users.items():
        user = conn.execute(sa.text("SELECT id FROM users WHERE lower(email) = :email"), {"email": email}).fetchone()
        if not user:
            continue
        conn.execute(sa.text("DELETE FROM user_franchises WHERE user_id = :user_id"), {"user_id": user.id})
        for role_id in franchise_role_ids:
            conn.execute(sa.text("DELETE FROM user_roles WHERE user_id = :user_id AND role_id = :role_id"), {"user_id": user.id, "role_id": role_id})
        admin_role_id = _role_id(conn, role_name)
        if admin_role_id:
            exists = conn.execute(sa.text(
                "SELECT 1 FROM user_roles WHERE user_id = :user_id AND role_id = :role_id"
            ), {"user_id": user.id, "role_id": admin_role_id}).fetchone()
            if not exists:
                conn.execute(sa.text(
                    "INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)"
                ), {"user_id": user.id, "role_id": admin_role_id})

    franchise_user_role = _role_id(conn, "Franchise User")
    if franchise_user_role:
        permission_ids = [row.id for row in conn.execute(sa.text(
            "SELECT id FROM permissions WHERE code LIKE 'franchise_agreement:%' OR code LIKE 'royalty_scale:%'"
        )).fetchall()]
        for permission_id in permission_ids:
            conn.execute(sa.text(
                "DELETE FROM role_permissions WHERE role_id = :role_id AND permission_id = :permission_id"
            ), {"role_id": franchise_user_role, "permission_id": permission_id})


def downgrade():
    pass
