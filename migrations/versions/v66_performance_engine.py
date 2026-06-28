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


PERFORMANCE_PERMISSIONS = [
    ("Performance", "view", "performance:view", "Performance - View", 97),
    ("Performance", "manage_targets", "performance:manage_targets", "Performance - Manage Targets", 98),
]


def upgrade():
    bind = op.get_bind()

    # Insert permissions using the actual permissions table structure:
    # id, module, action, code, label, sort_order.
    for module, action, code, label, sort_order in PERFORMANCE_PERMISSIONS:
        bind.execute(sa.text("""
            INSERT INTO permissions (module, action, code, label, sort_order)
            SELECT :module, :action, :code, :label, :sort_order
            WHERE NOT EXISTS (
                SELECT 1 FROM permissions WHERE code = :code
            )
        """), {
            "module": module,
            "action": action,
            "code": code,
            "label": label,
            "sort_order": sort_order,
        })

    # Give Admin full access to the performance module.
    bind.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.name = 'Admin'
          AND p.code IN ('performance:view', 'performance:manage_targets')
          AND NOT EXISTS (
              SELECT 1
              FROM role_permissions rp
              WHERE rp.role_id = r.id
                AND rp.permission_id = p.id
          )
    """))

    # Give normal franchise-facing roles view access only.
    bind.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.name IN ('Franchise User', 'Franchise Manager', 'Read Only User', 'Finance Manager', 'Finance Assistant')
          AND p.code = 'performance:view'
          AND NOT EXISTS (
              SELECT 1
              FROM role_permissions rp
              WHERE rp.role_id = r.id
                AND rp.permission_id = p.id
          )
    """))


def downgrade():
    bind = op.get_bind()

    bind.execute(sa.text("""
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT id FROM permissions
            WHERE code IN ('performance:view', 'performance:manage_targets')
        )
    """))

    bind.execute(sa.text("""
        DELETE FROM permissions
        WHERE code IN ('performance:view', 'performance:manage_targets')
    """))
