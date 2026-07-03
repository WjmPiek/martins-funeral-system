"""Data integrity and Franchise Master workbook fields

Revision ID: v103_data_integrity_master
Revises: v102_schema_reconciliation
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "v103_data_integrity_master"
down_revision = "v102_schema_reconciliation"
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
    indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes(table)}
    if index_name not in indexes:
        op.create_index(index_name, table, columns, unique=False)


def upgrade():
    bind = op.get_bind()
    if _table_exists(bind, "franchises"):
        _ensure_column(bind, "franchises", "province", sa.Column("province", sa.String(length=120), nullable=True, server_default=""))
        _ensure_column(bind, "franchises", "region", sa.Column("region", sa.String(length=120), nullable=True, server_default=""))
        _ensure_column(bind, "franchises", "district", sa.Column("district", sa.String(length=120), nullable=True, server_default=""))
        _ensure_column(bind, "franchises", "municipality", sa.Column("municipality", sa.String(length=120), nullable=True, server_default=""))
        _ensure_index(bind, "franchises", "ix_franchises_province", ["province"])
        _ensure_index(bind, "franchises", "ix_franchises_region", ["region"])
        _ensure_index(bind, "franchises", "ix_franchises_district", ["district"])
        _ensure_index(bind, "franchises", "ix_franchises_municipality", ["municipality"])
        bind.execute(sa.text("""
            UPDATE franchises
               SET province = COALESCE(NULLIF(province, ''), 'Unassigned'),
                   region = COALESCE(NULLIF(region, ''), COALESCE(NULLIF(province, ''), 'Unassigned'))
        """))


def downgrade():
    bind = op.get_bind()
    if _table_exists(bind, "franchises"):
        for idx in ("ix_franchises_municipality", "ix_franchises_district", "ix_franchises_region"):
            try:
                op.drop_index(idx, table_name="franchises")
            except Exception:
                pass
        existing = _columns(bind, "franchises")
        with op.batch_alter_table("franchises") as batch_op:
            for col in ("municipality", "district", "region"):
                if col in existing:
                    batch_op.drop_column(col)
