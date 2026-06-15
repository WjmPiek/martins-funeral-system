"""add heatmap records

Revision ID: v60_heatmap_records
Revises: v58_agreement_sync
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa


revision = "v60_heatmap_records"
down_revision = "v58_agreement_sync"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "heatmap_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
        sa.Column("mf_file", sa.String(length=120), nullable=True),
        sa.Column("deceased_name", sa.String(length=120), nullable=True),
        sa.Column("deceased_surname", sa.String(length=120), nullable=True),
        sa.Column("dod", sa.String(length=50), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("province", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("full_address", sa.String(length=512), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("next_of_kin_name", sa.String(length=120), nullable=True),
        sa.Column("next_of_kin_surname", sa.String(length=120), nullable=True),
        sa.Column("relationship", sa.String(length=120), nullable=True),
        sa.Column("relation", sa.String(length=50), nullable=True),
        sa.Column("contact_number", sa.String(length=120), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_heatmap_records_franchise_id", "heatmap_records", ["franchise_id"])
    op.create_index("ix_heatmap_records_created_by_id", "heatmap_records", ["created_by_id"])
    op.create_index("ix_heatmap_records_mf_file", "heatmap_records", ["mf_file"])
    op.create_index("ix_heatmap_records_city", "heatmap_records", ["city"])
    op.create_index("ix_heatmap_records_province", "heatmap_records", ["province"])


def downgrade():
    op.drop_index("ix_heatmap_records_province", table_name="heatmap_records")
    op.drop_index("ix_heatmap_records_city", table_name="heatmap_records")
    op.drop_index("ix_heatmap_records_mf_file", table_name="heatmap_records")
    op.drop_index("ix_heatmap_records_created_by_id", table_name="heatmap_records")
    op.drop_index("ix_heatmap_records_franchise_id", table_name="heatmap_records")
    op.drop_table("heatmap_records")
