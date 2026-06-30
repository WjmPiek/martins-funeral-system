"""v81 graphs default landing

Revision ID: v81_graphs_default_landing
Revises: v80_perf_fast_cache
Create Date: 2026-06-30

Makes Performance Graphs the default dashboard experience for all roles by
ensuring every standard role has performance:view.
"""
from alembic import op
import sqlalchemy as sa

revision = "v81_graphs_default_landing"
down_revision = "v80_perf_fast_cache"
branch_labels = None
depends_on = None

STANDARD_ROLES = [
    "Admin",
    "Super Admin",
    "Finance Manager",
    "Finance Assistant",
    "Regional Manager",
    "Franchise User",
    "Franchise Manager",
    "Franchise Employee",
    "Franchise Agent",
    "Read Only User",
]


def table_exists(bind, table_name):
    return bool(bind.execute(sa.text("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name=:table_name
        LIMIT 1
    """), {"table_name": table_name}).scalar())


def column_exists(bind, table_name, column_name):
    return bool(bind.execute(sa.text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:table_name AND column_name=:column_name
        LIMIT 1
    """), {"table_name": table_name, "column_name": column_name}).scalar())


def scalar(bind, sql, params=None):
    return bind.execute(sa.text(sql), params or {}).scalar()


def execute(bind, sql, params=None):
    bind.execute(sa.text(sql), params or {})


def ensure_performance_permission(bind):
    if not table_exists(bind, "permissions"):
        return None
    permission_id = scalar(bind, "SELECT id FROM permissions WHERE code='performance:view' LIMIT 1")
    if permission_id:
        return permission_id

    cols = ["module", "code"]
    vals = [":module", ":code"]
    params = {
        "module": "Performance",
        "action": "view",
        "code": "performance:view",
        "label": "View performance",
        "sort_order": 1,
    }
    if column_exists(bind, "permissions", "action"):
        cols.append("action")
        vals.append(":action")
    if column_exists(bind, "permissions", "label"):
        cols.append("label")
        vals.append(":label")
    if column_exists(bind, "permissions", "description"):
        cols.append("description")
        vals.append(":label")
    if column_exists(bind, "permissions", "sort_order"):
        cols.append("sort_order")
        vals.append(":sort_order")

    execute(bind, f"INSERT INTO permissions ({', '.join(cols)}) VALUES ({', '.join(vals)})", params)
    return scalar(bind, "SELECT id FROM permissions WHERE code='performance:view' LIMIT 1")


def grant_performance_to_standard_roles(bind, permission_id):
    if not permission_id or not (table_exists(bind, "roles") and table_exists(bind, "role_permissions")):
        return
    execute(bind, """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, :permission_id
        FROM roles r
        WHERE r.name = ANY(:role_names)
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id=r.id AND rp.permission_id=:permission_id
          )
    """, {"permission_id": permission_id, "role_names": STANDARD_ROLES})


def upgrade():
    bind = op.get_bind()
    permission_id = ensure_performance_permission(bind)
    grant_performance_to_standard_roles(bind, permission_id)


def downgrade():
    # Keep permission grants in place; this migration is a safe data repair.
    pass
