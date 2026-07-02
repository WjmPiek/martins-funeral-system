"""Enterprise insight explanation engine

Revision ID: v98_insights_engine
Revises: v97_business_intelligence
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "v98_insights_engine"
down_revision = "v97_business_intelligence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "insight_narratives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("narrative_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(220), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(30), nullable=False, server_default="info"),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
        sa.Column("province", sa.String(120), nullable=True),
        sa.Column("source", sa.String(120), nullable=False, server_default="insights_engine"),
        sa.Column("source_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_insight_narratives_period", "insight_narratives", ["year", "month"])
    op.create_index("ix_insight_narratives_type", "insight_narratives", ["narrative_type"])
    op.create_index("ix_insight_narratives_severity", "insight_narratives", ["severity"])
    op.create_index("ix_insight_narratives_franchise", "insight_narratives", ["franchise_id"])
    op.create_index("ix_insight_narratives_province", "insight_narratives", ["province"])


def downgrade():
    op.drop_index("ix_insight_narratives_province", table_name="insight_narratives")
    op.drop_index("ix_insight_narratives_franchise", table_name="insight_narratives")
    op.drop_index("ix_insight_narratives_severity", table_name="insight_narratives")
    op.drop_index("ix_insight_narratives_type", table_name="insight_narratives")
    op.drop_index("ix_insight_narratives_period", table_name="insight_narratives")
    op.drop_table("insight_narratives")
