"""Import contract summary fields

Revision ID: import_contract_summary_v23
Revises: fix_excel_import_v20
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "import_contract_summary_v23"
down_revision = "fix_excel_import_v20"
branch_labels = None
depends_on = None


def _add_column_if_missing(table, column):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {item["name"] for item in inspector.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def upgrade():
    _add_column_if_missing("franchises", sa.Column("ck_business_name", sa.String(length=255), nullable=True, server_default=""))
    _add_column_if_missing("franchises", sa.Column("ck_number", sa.String(length=80), nullable=True, server_default=""))
    _add_column_if_missing("franchises", sa.Column("pty_business_name", sa.String(length=255), nullable=True, server_default=""))
    _add_column_if_missing("franchises", sa.Column("imported_royalty_scale_text", sa.Text(), nullable=True, server_default=""))
    _add_column_if_missing("franchises", sa.Column("imported_royalty_percentage", sa.Numeric(5, 2), nullable=True, server_default="0"))


def downgrade():
    with op.batch_alter_table("franchises") as batch_op:
        for column in ["imported_royalty_percentage", "imported_royalty_scale_text", "pty_business_name", "ck_number", "ck_business_name"]:
            try:
                batch_op.drop_column(column)
            except Exception:
                pass
