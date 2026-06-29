"""v80 performance fast cache indexes

Revision ID: v80_perf_fast_cache
Revises: v79_perf_cleanup
Create Date: 2026-06-29

Adds extra covering indexes for the fast read path.  The application now
pre-calculates performance_results after import/recalculate and dashboards read
those rows instead of recalculating everything on every request.
"""
from alembic import op
import sqlalchemy as sa

revision = "v80_perf_fast_cache"
down_revision = "v79_perf_cleanup"
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
    create_index_if_possible(bind, "performance_results", "idx_perf_results_fast_period", ["year", "month", "franchise_id", "metric"])
    create_index_if_possible(bind, "performance_results", "idx_perf_results_fast_franchise", ["franchise_id", "year", "month", "metric"])
    create_index_if_possible(bind, "performance_snapshots", "idx_perf_snapshots_fast_period", ["year", "month", "franchise_id", "metric"])
    create_index_if_possible(bind, "performance_snapshots", "idx_perf_snapshots_fast_franchise", ["franchise_id", "year", "month", "metric"])
    create_index_if_possible(bind, "monthly_figures", "idx_monthly_figures_status_period", ["status", "year", "month", "franchise_id"])
    create_index_if_possible(bind, "franchises", "idx_franchises_performance_active", ["is_performance_active", "business_name"])


def downgrade():
    for index_name in [
        "idx_franchises_performance_active",
        "idx_monthly_figures_status_period",
        "idx_perf_snapshots_fast_franchise",
        "idx_perf_snapshots_fast_period",
        "idx_perf_results_fast_franchise",
        "idx_perf_results_fast_period",
    ]:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))
