"""Fix royalty calculation base to use sales plus selected insurance component

Revision ID: fix_royalty_calculation_v31
Revises: fix_royalty_scale_fields_v25
Create Date: 2026-06-13
"""
from alembic import op

revision = "fix_royalty_calculation_v31"
down_revision = "fix_royalty_scale_fields_v25"
branch_labels = None
depends_on = None


def upgrade():
    # Recalculate existing monthly figures using the corrected rule:
    # Gross - New = SALES + ADMIN FEE
    # Gross - Old = SALES + INSURANCE RECEIPTS
    # The previous logic used CASH + ADMIN/INSURANCE, which double-counted insurance.
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("""
        WITH bases AS (
            SELECT
                mf.id,
                COALESCE(mf.funeral_receipts,0)
                + COALESCE(mf.obo_service_receipts,0)
                + COALESCE(mf.cash_sales,0)
                + COALESCE(mf.tombstone_receipts,0) AS sales_calc,
                GREATEST(COALESCE(mf.insurance_receipts,0) - COALESCE(mf.insurance_payover,0), 0) AS admin_fee_calc,
                COALESCE(mf.insurance_receipts,0) AS insurance_receipts_calc,
                COALESCE(f.royalty_gross_method, 'new') AS method,
                COALESCE(f.minimum_royalty_amount,0) AS minimum_royalty_amount
            FROM monthly_figures mf
            JOIN franchises f ON f.id = mf.franchise_id
        ), calc AS (
            SELECT
                id,
                sales_calc,
                admin_fee_calc,
                CASE
                    WHEN method = 'old' THEN sales_calc + insurance_receipts_calc
                    ELSE sales_calc + admin_fee_calc
                END AS royalty_base,
                minimum_royalty_amount
            FROM bases
        ), pct AS (
            SELECT
                c.id,
                c.sales_calc,
                c.admin_fee_calc,
                c.royalty_base,
                c.minimum_royalty_amount,
                COALESCE((
                    SELECT rs.percentage
                    FROM royalty_scales rs
                    JOIN monthly_figures mf2 ON mf2.franchise_id = rs.franchise_id
                    WHERE mf2.id = c.id
                      AND c.royalty_base >= COALESCE(rs.amount_from,0)
                      AND c.royalty_base <= COALESCE(rs.amount_to,0)
                    ORDER BY rs.row_number ASC, rs.id ASC
                    LIMIT 1
                ),0) AS percentage
            FROM calc c
        )
        UPDATE monthly_figures mf
        SET
            sales = pct.sales_calc,
            admin_fee = pct.admin_fee_calc,
            cash = pct.royalty_base,
            cash_received = pct.royalty_base,
            gross_turnover = pct.royalty_base,
            gross_revenue = pct.royalty_base,
            insurance_received = COALESCE(mf.insurance_receipts,0),
            payover = COALESCE(mf.insurance_payover,0),
            other_income = pct.admin_fee_calc,
            royalty_percentage = pct.percentage,
            royalty_amount = CASE
                WHEN pct.minimum_royalty_amount > 0
                 AND ((pct.royalty_base * pct.percentage) / 100) < pct.minimum_royalty_amount
                THEN pct.minimum_royalty_amount
                ELSE ((pct.royalty_base * pct.percentage) / 100)
            END,
            minimum_royalty_applied = CASE
                WHEN pct.minimum_royalty_amount > 0
                 AND ((pct.royalty_base * pct.percentage) / 100) < pct.minimum_royalty_amount
                THEN TRUE ELSE FALSE END
        FROM pct
        WHERE mf.id = pct.id;
        """)
    else:
        # SQLite/dev fallback: keep migration safe; future saves/imports use corrected Python logic.
        pass


def downgrade():
    pass
