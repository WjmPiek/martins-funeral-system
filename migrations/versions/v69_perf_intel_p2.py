"""Performance Intelligence Phase 2 growth bracket engine

Revision ID: v69_perf_intel_p2
Revises: v68_perf_intel_p1
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "v69_perf_intel_p2"
down_revision = "v68_perf_intel_p1"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name):
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()
    if not _table_exists(bind, "performance_growth_brackets"):
        return

    # Keep Phase 2 idempotent: update/seed practical default brackets without
    # touching any Head Office edits that already exist for the same bracket.
    defaults = {
        "cash": [(0, 150000, 15), (150000, 300000, 12), (300000, 500000, 10), (500000, 750000, 8), (750000, 1200000, 6), (1200000, None, 5)],
        "sales": [(0, 150000, 15), (150000, 300000, 12), (300000, 500000, 10), (500000, 750000, 8), (750000, 1200000, 6), (1200000, None, 5)],
        "insurance_premiums": [(0, 25000, 15), (25000, 75000, 12), (75000, 150000, 10), (150000, 300000, 8), (300000, None, 6)],
        "joinings": [(0, 10, 20), (10, 25, 15), (25, 50, 10), (50, 100, 7), (100, None, 5)],
        "funerals": [(0, 10, 20), (10, 25, 15), (25, 50, 10), (50, 100, 7), (100, None, 5)],
    }
    for metric, brackets in defaults.items():
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
    # No destructive downgrade: Phase 2 only seeds/uses growth bracket data.
    pass
