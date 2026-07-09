"""Master Import source-of-truth fields

Revision ID: v107_master_import_source_of_truth
Revises: v106_core_business_repair
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa

revision = "v107_master_import_source_of_truth"
down_revision = "v106_core_business_repair"
branch_labels = None
depends_on = None


def _table_exists(bind, name):
    return sa.inspect(bind).has_table(name)


def _columns(bind, table):
    try:
        return {c["name"] for c in sa.inspect(bind).get_columns(table)}
    except Exception:
        return set()


def _ensure_column(bind, table, column_name, column):
    if column_name not in _columns(bind, table):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(column)


def _ensure_index(bind, table, index_name, columns):
    try:
        indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes(table)}
    except Exception:
        indexes = set()
    if index_name not in indexes:
        op.create_index(index_name, table, columns, unique=False)


def upgrade():
    bind = op.get_bind()
    if not _table_exists(bind, "franchises"):
        return
    _ensure_column(bind, "franchises", "master_import_id", sa.Column("master_import_id", sa.String(length=80), nullable=True, server_default=""))
    _ensure_column(bind, "franchises", "standardized_town", sa.Column("standardized_town", sa.String(length=160), nullable=True, server_default=""))
    _ensure_column(bind, "franchises", "province_code", sa.Column("province_code", sa.String(length=20), nullable=True, server_default=""))
    _ensure_column(bind, "franchises", "district_code", sa.Column("district_code", sa.String(length=20), nullable=True, server_default=""))
    _ensure_column(bind, "franchises", "municipality_code", sa.Column("municipality_code", sa.String(length=30), nullable=True, server_default=""))
    _ensure_index(bind, "franchises", "ix_franchises_master_import_id", ["master_import_id"])
    _ensure_index(bind, "franchises", "ix_franchises_standardized_town", ["standardized_town"])
    _ensure_index(bind, "franchises", "ix_franchises_province_code", ["province_code"])
    _ensure_index(bind, "franchises", "ix_franchises_district_code", ["district_code"])
    _ensure_index(bind, "franchises", "ix_franchises_municipality_code", ["municipality_code"])


def downgrade():
    pass
