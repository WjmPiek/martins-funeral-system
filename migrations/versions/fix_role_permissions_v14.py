"""fix role permission enforcement v1.4

Revision ID: fix_role_permissions_v14
Revises: b35a3c48d6ee
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "fix_role_permissions_v14"
down_revision = "b35a3c48d6ee"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    legacy_emails = ["renette@martinsdirect.com", "lowhaan@martinsdirect.com", "deon@martinsdirect.com"]

    user_ids = [row.id for row in conn.execute(
        sa.text("SELECT id FROM users WHERE lower(email) IN :emails").bindparams(
            sa.bindparam("emails", expanding=True)
        ),
        {"emails": legacy_emails},
    ).fetchall()]

    franchise_role_ids = [row.id for row in conn.execute(
        sa.text("SELECT id FROM roles WHERE name IN ('Franchise User', 'Franchise Manager', 'Read Only User')")
    ).fetchall()]

    for user_id in user_ids:
        conn.execute(sa.text("DELETE FROM user_franchises WHERE user_id = :user_id"), {"user_id": user_id})
        for role_id in franchise_role_ids:
            conn.execute(sa.text(
                "DELETE FROM user_roles WHERE user_id = :user_id AND role_id = :role_id"
            ), {"user_id": user_id, "role_id": role_id})

    role = conn.execute(sa.text("SELECT id FROM roles WHERE name = :name"), {"name": "Franchise User"}).fetchone()
    if role:
        permission_ids = [row.id for row in conn.execute(sa.text(
            "SELECT id FROM permissions WHERE code LIKE 'franchise_agreement:%' OR code LIKE 'royalty_scale:%'"
        )).fetchall()]
        for permission_id in permission_ids:
            conn.execute(sa.text(
                "DELETE FROM role_permissions WHERE role_id = :role_id AND permission_id = :permission_id"
            ), {"role_id": role.id, "permission_id": permission_id})


def downgrade():
    pass
