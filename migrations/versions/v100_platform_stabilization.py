"""Platform stabilization and data repair safety

Revision ID: v100_platform_stabilization
Revises: v99_workflow_engine
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa


revision = "v100_platform_stabilization"
down_revision = "v99_workflow_engine"
branch_labels = None
depends_on = None


def _table_exists(bind, name):
    return sa.inspect(bind).has_table(name)


def _columns(bind, table):
    try:
        return {c["name"] for c in sa.inspect(bind).get_columns(table)}
    except Exception:
        return set()


def upgrade():
    bind = op.get_bind()

    # Ensure the standard royalty growth profile exists.  This is data repair,
    # not a formula change: it simply provides the default profile expected by
    # the Phase 9 snapshot engine when no custom profile has been entered.
    if _table_exists(bind, "royalty_growth_profiles"):
        bind.execute(sa.text("""
            INSERT INTO royalty_growth_profiles
                (name, source, default_growth_percent, scope_type, is_active, notes, created_at, updated_at)
            VALUES
                ('South Africa GDP Standard', 'SA GDP standard', 1.6000, 'global', TRUE,
                 'Default royalty target growth policy. Admin may change this; franchise users do not see it.',
                 NOW(), NOW())
            ON CONFLICT (name) DO NOTHING
        """))

    # Null numeric values caused several downstream pages to appear empty or
    # fail during rebuilds.  Preserve real values, but normalize nulls to zero.
    if _table_exists(bind, "monthly_figures"):
        cols = _columns(bind, "monthly_figures")
        numeric_cols = [
            "gross_turnover", "cash", "card", "eft", "policies", "sales",
            "payover", "royalty_percentage", "royalty_amount", "number_of_funerals",
            "insurance_joinings", "mf_files",
        ]
        assignments = [f"{col} = COALESCE({col}, 0)" for col in numeric_cols if col in cols]
        if assignments:
            bind.execute(sa.text("UPDATE monthly_figures SET " + ", ".join(assignments)))

    if _table_exists(bind, "royalty_calculation_snapshots"):
        cols = _columns(bind, "royalty_calculation_snapshots")
        numeric_cols = [
            "royalty_base", "royalty_percentage", "royalty_amount", "minimum_royalty_amount",
            "growth_percent", "target_amount", "previous_year_average",
        ]
        assignments = [f"{col} = COALESCE({col}, 0)" for col in numeric_cols if col in cols]
        if "status" in cols:
            assignments.append("status = COALESCE(NULLIF(status, ''), 'calculated')")
        if "diagnostics_json" in cols:
            assignments.append("diagnostics_json = COALESCE(NULLIF(diagnostics_json, ''), '{}')")
        if assignments:
            bind.execute(sa.text("UPDATE royalty_calculation_snapshots SET " + ", ".join(assignments)))


def downgrade():
    # Data normalization is intentionally not reversed.
    pass
