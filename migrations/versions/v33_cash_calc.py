"""Fix cash calculation to sales plus insurance receipts for all franchises

Revision ID: v33_cash_calc
Revises: fix_royalty_calculation_v31
Create Date: 2026-06-13
"""
from alembic import op

revision = "v33_cash_calc"
down_revision = "fix_royalty_calculation_v31"
branch_labels = None
depends_on = None


def upgrade():
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
                COALESCE(mf.insurance_receipts,0) AS insurance_receipts_calc,
                GREATEST(COALESCE(mf.insurance_receipts,0) - COALESCE(mf.insurance_payover,0), 0) AS admin_fee_calc,
                COALESCE(f.minimum_royalty_amount,0) AS minimum_royalty_amount
            FROM monthly_figures mf
            JOIN franchises f ON f.id = mf.franchise_id
        ), calc AS (
            SELECT
                id,
                sales_calc,
                insurance_receipts_calc,
                admin_fee_calc,
                sales_calc + insurance_receipts_calc AS royalty_base,
                minimum_royalty_amount
            FROM bases
        ), pct AS (
            SELECT
                c.id,
                c.sales_calc,
                c.insurance_receipts_calc,
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
            insurance_received = pct.insurance_receipts_calc,
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

        UPDATE franchises
        SET royalty_gross_method = 'old';
        """)
    else:
        # SQLite/dev fallback: future imports/saves use the corrected Python logic.
        pass


def downgrade():
    pass
