"""Performance Intelligence Phase 12: inactive franchise hiding

Revision ID: v72_perf_inactive
Revises: v71_perf_intel_p11
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


revision = "v72_perf_inactive"
down_revision = "v71_perf_intel_p11"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name):
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _columns(bind, table_name):
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)} if _table_exists(bind, table_name) else set()


def _insert_permission(bind, code, module, action, label, sort_order=0):
    cols = _columns(bind, "permissions")
    values = {"code": code, "module": module, "action": action, "label": label, "sort_order": sort_order}
    insert_cols = [col for col in ("module", "action", "code", "label", "sort_order") if col in cols]
    if not insert_cols:
        return
    bind.execute(sa.text(f"""
        INSERT INTO permissions ({', '.join(insert_cols)})
        SELECT {', '.join(':' + col for col in insert_cols)}
        WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
    """), values)


def _grant_to_roles(bind, code, role_names):
    if not _table_exists(bind, "role_permissions"):
        return
    permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :code LIMIT 1"), {"code": code}).scalar()
    if not permission_id:
        return
    for role_name in role_names:
        role_id = bind.execute(sa.text("SELECT id FROM roles WHERE lower(name) = lower(:name) LIMIT 1"), {"name": role_name}).scalar()
        if role_id:
            bind.execute(sa.text("""
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT :role_id, :permission_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM role_permissions
                    WHERE role_id = :role_id AND permission_id = :permission_id
                )
            """), {"role_id": role_id, "permission_id": permission_id})


def upgrade():
    bind = op.get_bind()
    franchise_cols = _columns(bind, "franchises")

    if "is_performance_active" not in franchise_cols:
        op.add_column("franchises", sa.Column("is_performance_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        op.create_index("ix_franchises_is_performance_active", "franchises", ["is_performance_active"], unique=False)
    if "performance_inactive_at" not in franchise_cols:
        op.add_column("franchises", sa.Column("performance_inactive_at", sa.DateTime(), nullable=True))
    if "performance_inactive_reason" not in franchise_cols:
        op.add_column("franchises", sa.Column("performance_inactive_reason", sa.String(length=255), nullable=True, server_default=""))
    if "performance_reactivated_at" not in franchise_cols:
        op.add_column("franchises", sa.Column("performance_reactivated_at", sa.DateTime(), nullable=True))
    if "performance_reactivated_by_id" not in franchise_cols:
        op.add_column("franchises", sa.Column("performance_reactivated_by_id", sa.Integer(), nullable=True))
        try:
            op.create_foreign_key("fk_franchises_perf_reactivated_by", "franchises", "users", ["performance_reactivated_by_id"], ["id"])
        except Exception:
            pass

    _insert_permission(
        bind,
        "performance:manage_inactive",
        "Performance",
        "manage_inactive",
        "Hide and reactivate inactive franchises",
        85,
    )
    _grant_to_roles(bind, "performance:manage_inactive", ["Admin", "Super Admin", "Finance Manager", "Finance"])


def downgrade():
    bind = op.get_bind()
    cols = _columns(bind, "franchises")
    if "performance_reactivated_by_id" in cols:
        try:
            op.drop_constraint("fk_franchises_perf_reactivated_by", "franchises", type_="foreignkey")
        except Exception:
            pass
        op.drop_column("franchises", "performance_reactivated_by_id")
    for column_name in ["performance_reactivated_at", "performance_inactive_reason", "performance_inactive_at"]:
        if column_name in _columns(bind, "franchises"):
            op.drop_column("franchises", column_name)
    if "is_performance_active" in _columns(bind, "franchises"):
        try:
            op.drop_index("ix_franchises_is_performance_active", table_name="franchises")
        except Exception:
            pass
        op.drop_column("franchises", "is_performance_active")
