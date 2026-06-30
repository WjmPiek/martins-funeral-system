"""Add annual gross turnover target scale

Revision ID: v83_gross_scale
Revises: v82_admin_fix
Create Date: 2026-06-30
"""
from alembic import op

revision = "v83_gross_scale"
down_revision = "v82_admin_fix"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")
    rows = [
        ("gross_turnover", 0, 100000, 15),
        ("gross_turnover", 100000, 200000, 12),
        ("gross_turnover", 200000, 400000, 10),
        ("gross_turnover", 400000, 700000, 7),
        ("gross_turnover", 700000, 1200000, 4),
        ("gross_turnover", 1200000, None, 3),
    ]
    for metric, amount_from, amount_to, percent in rows:
        to_clause = "amount_to IS NULL" if amount_to is None else f"amount_to = {amount_to}"
        amount_to_sql = "NULL" if amount_to is None else str(amount_to)
        op.execute(f"""
            INSERT INTO performance_growth_brackets
                (metric, amount_from, amount_to, growth_percent, basis_metric, is_active, created_at, updated_at)
            SELECT '{metric}', {amount_from}, {amount_to_sql}, {percent}, 'gross_turnover', true, NOW(), NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM performance_growth_brackets
                WHERE metric = '{metric}' AND amount_from = {amount_from} AND {to_clause} AND basis_metric = 'gross_turnover'
            )
        """)


def downgrade():
    op.execute("DELETE FROM performance_growth_brackets WHERE metric = 'gross_turnover' AND basis_metric = 'gross_turnover'")
