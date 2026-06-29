"""v79 performance cleanup indexes

Revision ID: v79_perf_cleanup
Revises: v78_security_growth
Create Date: 2026-06-29

Adds safe database indexes used by performance analytics, dashboards,
leaderboards and user-scope lookups. This improves page speed without
changing existing data.
"""
from alembic import op
import sqlalchemy as sa

revision = "v79_perf_cleanup"
down_revision = "v78_security_growth"
branch_labels = None
depends_on = None


def table_exists(bind, table_name):
    return bool(bind.execute(sa.text("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name=:table_name
        LIMIT 1
    """), {"table_name": table_name}).scalar())


def columns_exist(bind, table_name, columns):
    found = {
        row[0]
        for row in bind.execute(sa.text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:table_name
        """), {"table_name": table_name}).all()
    }
    return all(column in found for column in columns)


def create_index_if_possible(bind, table_name, index_name, columns):
    if table_exists(bind, table_name) and columns_exist(bind, table_name, columns):
        column_sql = ", ".join(columns)
        op.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_sql})"))


def upgrade():
    bind = op.get_bind()

    create_index_if_possible(bind, "monthly_figures", "idx_monthly_figures_period_franchise", ["year", "month", "franchise_id"])
    create_index_if_possible(bind, "monthly_figures", "idx_monthly_figures_franchise_period", ["franchise_id", "year", "month"])

    create_index_if_possible(bind, "franchise_targets", "idx_franchise_targets_period_lookup", ["year", "month", "franchise_id", "metric"])
    create_index_if_possible(bind, "performance_results", "idx_performance_results_period_lookup", ["year", "month", "franchise_id", "metric"])
    create_index_if_possible(bind, "performance_growth_brackets", "idx_performance_growth_brackets_lookup", ["metric", "is_active", "amount_from", "amount_to"])

    create_index_if_possible(bind, "user_franchises", "idx_user_franchises_user_franchise", ["user_id", "franchise_id"])
    create_index_if_possible(bind, "user_franchises", "idx_user_franchises_franchise_user", ["franchise_id", "user_id"])
    create_index_if_possible(bind, "user_roles", "idx_user_roles_user_role", ["user_id", "role_id"])
    create_index_if_possible(bind, "role_permissions", "idx_role_permissions_role_permission", ["role_id", "permission_id"])


def downgrade():
    for index_name in [
        "idx_role_permissions_role_permission",
        "idx_user_roles_user_role",
        "idx_user_franchises_franchise_user",
        "idx_user_franchises_user_franchise",
        "idx_performance_growth_brackets_lookup",
        "idx_performance_results_period_lookup",
        "idx_franchise_targets_period_lookup",
        "idx_monthly_figures_franchise_period",
        "idx_monthly_figures_period_franchise",
    ]:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))
