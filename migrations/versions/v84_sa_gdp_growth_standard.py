"""Use SA GDP growth as default performance scale

Revision ID: v84_gdp_standard
Revises: v83_gross_scale
Create Date: 2026-06-30
"""
from alembic import op

revision = "v84_gdp_standard"
down_revision = "v83_gross_scale"
branch_labels = None
depends_on = None


def upgrade():
    # Keep Alembic version values safe on Render/PostgreSQL.
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")

    # Default SA GDP growth standard for the annual gross turnover target scale.
    # Admin can change these values later from Performance > Growth Brackets.
    rows = [
        (0, 100000),
        (100000, 200000),
        (200000, 400000),
        (400000, 700000),
        (700000, 1200000),
        (1200000, None),
    ]
    for amount_from, amount_to in rows:
        amount_to_sql = "NULL" if amount_to is None else str(amount_to)
        to_match = "amount_to IS NULL" if amount_to is None else f"amount_to = {amount_to}"
        op.execute(f"""
            INSERT INTO performance_growth_brackets
                (metric, amount_from, amount_to, growth_percent, basis_metric, is_active, created_at, updated_at)
            SELECT 'gross_turnover', {amount_from}, {amount_to_sql}, 1.60, 'gross_turnover', true, NOW(), NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM performance_growth_brackets
                WHERE metric = 'gross_turnover'
                  AND basis_metric = 'gross_turnover'
                  AND amount_from = {amount_from}
                  AND {to_match}
            )
        """)

    op.execute("""
        UPDATE performance_growth_brackets
        SET growth_percent = 1.60,
            updated_at = NOW()
        WHERE metric = 'gross_turnover'
          AND basis_metric = 'gross_turnover'
          AND is_active = true
    """)


def downgrade():
    # Do not restore old high-growth assumptions automatically.
    pass
