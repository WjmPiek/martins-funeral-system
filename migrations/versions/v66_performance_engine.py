"""v66 performance engine

Revision ID: v66_performance_engine
Revises: v65_leaderboard_module
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "v66_performance_engine"
down_revision = "v65_leaderboard_module"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    permissions = [
        ("performance:view", "Performance", "View performance dashboards, targets and graphs"),
        ("performance:manage_targets", "Performance", "Capture and update performance targets"),
    ]
    for code, module, _description in permissions:
        bind.execute(sa.text("""
            INSERT INTO permissions (module, action, code)
            SELECT :module, :action, :code
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
        """), {"code": code, "module": module})
    admin_id = bind.execute(sa.text("SELECT id FROM roles WHERE name = 'Admin' LIMIT 1")).scalar()
    if admin_id:
        for code, module, _description in permissions:
            action = code.split(":")[-1]
            bind.execute(sa.text("""
                INSERT INTO permissions (module, action, code)
                SELECT :module, :action, :code
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
            """), {
                "code": code,
                "module": module,
                "action": action
            })


def downgrade():
    bind = op.get_bind()
    for code in ("performance:view", "performance:manage_targets"):
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}).scalar()
        if permission_id:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
            bind.execute(sa.text("DELETE FROM permissions WHERE id = :permission_id"), {"permission_id": permission_id})
