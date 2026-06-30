"""Async performance graphs and dashboard indexes

Revision ID: v86_async_perf
Revises: v85_user_visibility
Create Date: 2026-06-30
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "v86_async_perf"
down_revision = "v85_user_visibility"
branch_labels = None
depends_on = None


def _create_index(name, table, columns):
    bind = op.get_bind()
    inspector = __import__("sqlalchemy").inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns)


def _drop_index(name, table):
    bind = op.get_bind()
    inspector = __import__("sqlalchemy").inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes(table)}
    if name in existing:
        op.drop_index(name, table_name=table)


def upgrade():
    # The graph API reads by period/franchise/metric constantly.  These indexes
    # make cached dashboard reads fast and keep any fallback rebuild focused.
    _create_index("ix_monthly_figures_period_franchise", "monthly_figures", ["year", "month", "franchise_id"])
    _create_index("ix_monthly_figures_franchise_period", "monthly_figures", ["franchise_id", "year", "month"])
    _create_index("ix_performance_results_period_metric", "performance_results", ["year", "month", "metric"])
    _create_index("ix_performance_results_franchise_period", "performance_results", ["franchise_id", "year", "month"])
    _create_index("ix_franchise_targets_period_metric", "franchise_targets", ["year", "month", "metric"])


def downgrade():
    _drop_index("ix_franchise_targets_period_metric", "franchise_targets")
    _drop_index("ix_performance_results_franchise_period", "performance_results")
    _drop_index("ix_performance_results_period_metric", "performance_results")
    _drop_index("ix_monthly_figures_franchise_period", "monthly_figures")
    _drop_index("ix_monthly_figures_period_franchise", "monthly_figures")
