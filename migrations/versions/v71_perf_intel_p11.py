"""Performance Intelligence Phase 11: history and access foundation

Revision ID: v71_perf_intel_p11
Revises: v70_perf_intel_p3
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


revision = "v71_perf_intel_p11"
down_revision = "v70_perf_intel_p3"
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
    col_list = ", ".join(insert_cols)
    param_list = ", ".join(f":{col}" for col in insert_cols)
    bind.execute(sa.text(f"""
        INSERT INTO permissions ({col_list})
        SELECT {param_list}
        WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
    """), values)


def _grant_to_admin(bind, code):
    if not _table_exists(bind, "role_permissions"):
        return
    role_id = bind.execute(sa.text("SELECT id FROM roles WHERE name = 'Admin' LIMIT 1")).scalar()
    permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :code LIMIT 1"), {"code": code}).scalar()
    if role_id and permission_id:
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

    if not _table_exists(bind, "performance_snapshots"):
        op.create_table(
            "performance_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=False, index=True),
            sa.Column("year", sa.Integer(), nullable=False, index=True),
            sa.Column("month", sa.Integer(), nullable=False, index=True),
            sa.Column("metric", sa.String(length=80), nullable=False, index=True),
            sa.Column("actual_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("target_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("achievement_percent", sa.Numeric(8, 2), nullable=False, server_default="0"),
            sa.Column("growth_percent", sa.Numeric(8, 2), nullable=False, server_default="0"),
            sa.Column("forecast_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("previous_rank", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("movement", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("health_score", sa.Numeric(8, 2), nullable=False, server_default="0"),
            sa.Column("source", sa.String(length=80), nullable=False, server_default="performance_results"),
            sa.Column("captured_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("captured_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
            sa.UniqueConstraint("franchise_id", "metric", "year", "month", name="uq_perf_snapshot_period_metric"),
        )

    if not _table_exists(bind, "user_dashboard_preferences"):
        op.create_table(
            "user_dashboard_preferences",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True, index=True),
            sa.Column("default_module", sa.String(length=80), nullable=False, server_default="dashboard"),
            sa.Column("default_metric", sa.String(length=80), nullable=False, server_default="cash"),
            sa.Column("default_date_range", sa.String(length=40), nullable=False, server_default="current_month"),
            sa.Column("show_graphs", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("show_leaderboard", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("show_insights", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    permissions = [
        ("performance:history", "Performance", "history", "View performance history", 80),
        ("users:manage", "Users", "manage", "Manage users and access", 90),
    ]
    for code, module, action, label, sort_order in permissions:
        _insert_permission(bind, code, module, action, label, sort_order)
        _grant_to_admin(bind, code)


def downgrade():
    op.drop_table("user_dashboard_preferences")
    op.drop_table("performance_snapshots")
