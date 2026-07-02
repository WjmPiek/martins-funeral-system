"""Enterprise royalty management snapshots

Revision ID: v95_royalty_mgmt
Revises: v94_event_bus
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "v95_royalty_mgmt"
down_revision = "v94_event_bus"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "royalty_growth_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False, server_default="SA GDP standard"),
        sa.Column("default_growth_percent", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("scope_type", sa.String(length=40), nullable=False, server_default="global"),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_royalty_growth_profiles_name", "royalty_growth_profiles", ["name"], unique=True)
    op.create_index("ix_royalty_growth_profiles_scope_type", "royalty_growth_profiles", ["scope_type"])
    op.create_index("ix_royalty_growth_profiles_scope_id", "royalty_growth_profiles", ["scope_id"])
    op.create_index("ix_royalty_growth_profiles_is_active", "royalty_growth_profiles", ["is_active"])
    op.create_index("ix_royalty_growth_profiles_created_at", "royalty_growth_profiles", ["created_at"])

    op.create_table(
        "royalty_agreement_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=False),
        sa.Column("agreement_version", sa.String(length=80), nullable=False, server_default="legacy"),
        sa.Column("formula_version", sa.String(length=80), nullable=False, server_default="current_scale"),
        sa.Column("royalty_method", sa.String(length=20), nullable=False, server_default="old"),
        sa.Column("target_method", sa.String(length=80), nullable=False, server_default="previous_year_average_plus_growth"),
        sa.Column("growth_profile_id", sa.Integer(), sa.ForeignKey("royalty_growth_profiles.id"), nullable=True),
        sa.Column("custom_growth_percent", sa.Numeric(8, 4), nullable=True),
        sa.Column("effective_start_date", sa.Date(), nullable=True),
        sa.Column("effective_end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    for col in ["franchise_id", "agreement_version", "formula_version", "royalty_method", "growth_profile_id", "effective_start_date", "effective_end_date", "is_active", "created_at"]:
        op.create_index(f"ix_royalty_agreement_profiles_{col}", "royalty_agreement_profiles", [col])
    op.create_unique_constraint("uq_royalty_agreement_profile_version", "royalty_agreement_profiles", ["franchise_id", "agreement_version", "formula_version"])

    op.create_table(
        "royalty_calculation_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("monthly_figure_id", sa.Integer(), sa.ForeignKey("monthly_figures.id"), nullable=False),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("agreement_profile_id", sa.Integer(), sa.ForeignKey("royalty_agreement_profiles.id"), nullable=True),
        sa.Column("agreement_version", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("formula_version", sa.String(length=80), nullable=False, server_default="current_scale"),
        sa.Column("royalty_method", sa.String(length=20), nullable=False, server_default="old"),
        sa.Column("method_source", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("royalty_base", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("royalty_percentage", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("royalty_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("minimum_royalty_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("minimum_royalty_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("scale_source_franchise_id", sa.Integer(), nullable=True),
        sa.Column("scale_source_franchise_name", sa.String(length=180), nullable=False, server_default=""),
        sa.Column("growth_profile_id", sa.Integer(), sa.ForeignKey("royalty_growth_profiles.id"), nullable=True),
        sa.Column("growth_percent", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("target_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("previous_year_average", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="calculated"),
        sa.Column("diagnostics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("calculated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_royalty_calculation_snapshots_monthly_figure_id", "royalty_calculation_snapshots", ["monthly_figure_id"], unique=True)
    for col in ["franchise_id", "year", "month", "agreement_profile_id", "scale_source_franchise_id", "growth_profile_id", "status", "calculated_at", "created_at"]:
        op.create_index(f"ix_royalty_calculation_snapshots_{col}", "royalty_calculation_snapshots", [col])
    op.create_index("ix_royalty_snapshots_period", "royalty_calculation_snapshots", ["year", "month"])

    op.create_table(
        "royalty_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
        sa.Column("override_type", sa.String(length=80), nullable=False),
        sa.Column("field_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("old_value", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("new_value", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("effective_month", sa.Integer(), nullable=True),
        sa.Column("effective_year", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    for col in ["franchise_id", "override_type", "effective_month", "effective_year", "created_by_id", "created_at"]:
        op.create_index(f"ix_royalty_overrides_{col}", "royalty_overrides", [col])

    op.execute("""
        INSERT INTO royalty_growth_profiles (name, source, default_growth_percent, scope_type, is_active, notes)
        VALUES ('South Africa GDP Standard', 'SA GDP standard', 1.6000, 'global', true, 'Default growth standard for royalty targets. Admin-only setting; franchise users do not see or edit it.')
        ON CONFLICT (name) DO NOTHING
    """)

    op.execute("""
        INSERT INTO event_subscriptions (name, event_type, handler, description, is_active)
        VALUES
        ('royalty-recalculated', 'royalty.recalculated', 'royalty_management', 'Record and publish royalty recalculation results.', true),
        ('royalty-needs-review', 'royalty.needs_review', 'royalty_management', 'Track royalty rows that require Admin/Finance review.', true)
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade():
    op.drop_table("royalty_overrides")
    op.drop_table("royalty_calculation_snapshots")
    op.drop_table("royalty_agreement_profiles")
    op.drop_table("royalty_growth_profiles")
