"""Enterprise business intelligence health scoring

Revision ID: v97_business_intelligence
Revises: v96_exec_dashboard
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "v97_business_intelligence"
down_revision = "v96_exec_dashboard"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "franchise_health_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("health_score", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("health_status", sa.String(30), nullable=False, server_default="watch"),
        sa.Column("gross_turnover", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("previous_gross_turnover", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("growth_percent", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("target_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("target_achievement_percent", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("royalty_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("royalty_ratio_percent", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("consecutive_growth_months", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_decline_months", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reasons_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_fhs_franchise_period", "franchise_health_snapshots", ["franchise_id", "year", "month"], unique=True)
    op.create_index("ix_fhs_period_status", "franchise_health_snapshots", ["year", "month", "health_status"])
    op.create_index("ix_fhs_health_score", "franchise_health_snapshots", ["health_score"])

    op.create_table(
        "business_insights",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("insight_type", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False, server_default="info"),
        sa.Column("title", sa.String(180), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("data_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_business_insights_period", "business_insights", ["year", "month"])
    op.create_index("ix_business_insights_severity", "business_insights", ["severity"])
    op.create_index("ix_business_insights_type", "business_insights", ["insight_type"])
    op.create_index("ix_business_insights_active", "business_insights", ["is_active"])


def downgrade():
    op.drop_index("ix_business_insights_active", table_name="business_insights")
    op.drop_index("ix_business_insights_type", table_name="business_insights")
    op.drop_index("ix_business_insights_severity", table_name="business_insights")
    op.drop_index("ix_business_insights_period", table_name="business_insights")
    op.drop_table("business_insights")
    op.drop_index("ix_fhs_health_score", table_name="franchise_health_snapshots")
    op.drop_index("ix_fhs_period_status", table_name="franchise_health_snapshots")
    op.drop_index("ix_fhs_franchise_period", table_name="franchise_health_snapshots")
    op.drop_table("franchise_health_snapshots")
