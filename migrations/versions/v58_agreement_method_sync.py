"""Sync agreement gross method and recalculate royalties

Revision ID: v58_agreement_sync
Revises: v57_society_royalty
Create Date: 2026-06-13
"""
from alembic import op

revision = "v58_agreement_sync"
down_revision = "v57_society_royalty"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("""
    UPDATE franchises
    SET royalty_gross_method = CASE
        WHEN agreement_start_date IS NOT NULL AND EXTRACT(YEAR FROM agreement_start_date) >= 2018 THEN 'new'
        ELSE 'old'
    END;

    WITH bases AS (
        SELECT
            mf.id,
            f.id AS franchise_id,
            COALESCE(NULLIF(f.royalty_gross_method,''),
                CASE WHEN f.agreement_start_date IS NOT NULL AND EXTRACT(YEAR FROM f.agreement_start_date) >= 2018
                     THEN 'new' ELSE 'old' END
            ) AS method,
            COALESCE(mf.funeral_receipts,0)
            + COALESCE(mf.society_receipts,0)
            + COALESCE(mf.cash_sales,0)
            + COALESCE(mf.tombstone_receipts,0)
            + COALESCE(mf.obo_service_receipts,0) AS sales_calc,
            COALESCE(mf.insurance_receipts,0) AS insurance_receipts_calc,
            GREATEST(COALESCE(mf.insurance_receipts,0) - COALESCE(mf.insurance_payover,0), 0) AS admin_fee_calc,
            COALESCE(f.minimum_royalty_amount,0) AS minimum_royalty_amount
        FROM monthly_figures mf
        JOIN franchises f ON f.id = mf.franchise_id
    ), calc AS (
        SELECT
            id,
            franchise_id,
            sales_calc,
            insurance_receipts_calc,
            admin_fee_calc,
            CASE
                WHEN method = 'new' THEN sales_calc + admin_fee_calc
                ELSE sales_calc + COALESCE(insurance_receipts_calc,0)
            END AS royalty_base,
            sales_calc + COALESCE(insurance_receipts_calc,0) AS cash_calc,
            minimum_royalty_amount
        FROM bases
    ), pct AS (
        SELECT
            c.id,
            c.sales_calc,
            c.insurance_receipts_calc,
            c.admin_fee_calc,
            c.royalty_base,
            c.cash_calc,
            c.minimum_royalty_amount,
            COALESCE((
                SELECT rs.percentage
                FROM royalty_scales rs
                WHERE rs.franchise_id = c.franchise_id
                  AND c.royalty_base >= COALESCE(rs.amount_from,0)
                  AND c.royalty_base <= COALESCE(NULLIF(rs.amount_to,0), 999999999999)
                ORDER BY rs.row_number ASC, rs.id ASC
                LIMIT 1
            ),0) AS percentage
        FROM calc c
    )
    UPDATE monthly_figures mf
    SET
        sales = pct.sales_calc,
        admin_fee = pct.admin_fee_calc,
        cash = pct.cash_calc,
        cash_received = pct.cash_calc,
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
    """)


def downgrade():
    pass
