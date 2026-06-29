"""Performance Intelligence Phase 1 foundation

Revision ID: v68_perf_intel_p1
Revises: v67_gross_old_royalty_fix
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "v68_perf_intel_p1"
down_revision = "v67_gross_old_royalty_fix"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name):
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()

    if not _table_exists(bind, "performance_growth_brackets"):
        op.create_table(
            "performance_growth_brackets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("metric", sa.String(length=80), nullable=False),
            sa.Column("amount_from", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("amount_to", sa.Numeric(14, 2), nullable=True),
            sa.Column("growth_percent", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("basis_metric", sa.String(length=80), nullable=False, server_default="cash"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("metric", "amount_from", "amount_to", "basis_metric", name="uq_performance_growth_bracket"),
        )
        op.create_index("ix_performance_growth_brackets_metric", "performance_growth_brackets", ["metric"])
        op.create_index("ix_performance_growth_brackets_is_active", "performance_growth_brackets", ["is_active"])

    if not _table_exists(bind, "performance_results"):
        op.create_table(
            "performance_results",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=False),
            sa.Column("metric", sa.String(length=80), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("month", sa.Integer(), nullable=False),
            sa.Column("actual_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("target_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("achievement_percent", sa.Numeric(8, 2), nullable=False, server_default="0"),
            sa.Column("growth_percent", sa.Numeric(8, 2), nullable=False, server_default="0"),
            sa.Column("previous_month_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("same_month_last_year_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("three_year_average_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("forecast_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("source", sa.String(length=80), nullable=False, server_default="monthly_figures"),
            sa.Column("calculated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("franchise_id", "metric", "year", "month", name="uq_performance_result_period_metric"),
        )
        op.create_index("ix_performance_results_franchise_id", "performance_results", ["franchise_id"])
        op.create_index("ix_performance_results_metric", "performance_results", ["metric"])
        op.create_index("ix_performance_results_year", "performance_results", ["year"])
        op.create_index("ix_performance_results_month", "performance_results", ["month"])

    money_brackets = [
        (0, 150000, 15),
        (150000, 300000, 12),
        (300000, 500000, 10),
        (500000, 750000, 8),
        (750000, 1200000, 6),
        (1200000, None, 5),
    ]
    count_brackets = [
        (0, 10, 20),
        (10, 25, 15),
        (25, 50, 10),
        (50, None, 7),
    ]
    metric_brackets = {
        "cash": money_brackets,
        "sales": money_brackets,
        "insurance_premiums": money_brackets,
        "joinings": count_brackets,
        "funerals": count_brackets,
    }
    for metric, brackets in metric_brackets.items():
        for amount_from, amount_to, growth_percent in brackets:
            exists = bind.execute(sa.text("""
                SELECT id FROM performance_growth_brackets
                WHERE metric = :metric
                  AND amount_from = :amount_from
                  AND COALESCE(amount_to, -1) = COALESCE(:amount_to, -1)
                LIMIT 1
            """), {"metric": metric, "amount_from": amount_from, "amount_to": amount_to}).scalar()
            if not exists:
                bind.execute(sa.text("""
                    INSERT INTO performance_growth_brackets
                    (metric, amount_from, amount_to, growth_percent, basis_metric, is_active)
                    VALUES (:metric, :amount_from, :amount_to, :growth_percent, :basis_metric, true)
                """), {
                    "metric": metric,
                    "amount_from": amount_from,
                    "amount_to": amount_to,
                    "growth_percent": growth_percent,
                    "basis_metric": metric,
                })


def downgrade():
    bind = op.get_bind()
    if _table_exists(bind, "performance_results"):
        op.drop_index("ix_performance_results_month", table_name="performance_results")
        op.drop_index("ix_performance_results_year", table_name="performance_results")
        op.drop_index("ix_performance_results_metric", table_name="performance_results")
        op.drop_index("ix_performance_results_franchise_id", table_name="performance_results")
        op.drop_table("performance_results")
    if _table_exists(bind, "performance_growth_brackets"):
        op.drop_index("ix_performance_growth_brackets_is_active", table_name="performance_growth_brackets")
        op.drop_index("ix_performance_growth_brackets_metric", table_name="performance_growth_brackets")
        op.drop_table("performance_growth_brackets")
