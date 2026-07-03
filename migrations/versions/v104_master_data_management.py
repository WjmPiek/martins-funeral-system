"""Master data management workbook and readiness reporting

Revision ID: v104_master_data_management
Revises: v103_data_integrity_master
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "v104_master_data_management"
down_revision = "v103_data_integrity_master"
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


def upgrade():
    bind = op.get_bind()
    if _table_exists(bind, "franchises"):
        _ensure_column(bind, "franchises", "province", sa.Column("province", sa.String(length=120), nullable=True, server_default=""))
        _ensure_column(bind, "franchises", "region", sa.Column("region", sa.String(length=120), nullable=True, server_default=""))
        _ensure_column(bind, "franchises", "district", sa.Column("district", sa.String(length=120), nullable=True, server_default=""))
        _ensure_column(bind, "franchises", "municipality", sa.Column("municipality", sa.String(length=120), nullable=True, server_default=""))
        _ensure_column(bind, "franchises", "regional_manager_email", sa.Column("regional_manager_email", sa.String(length=255), nullable=True, server_default=""))
        _ensure_column(bind, "franchises", "finance_manager_email", sa.Column("finance_manager_email", sa.String(length=255), nullable=True, server_default=""))
        bind.execute(sa.text("""
            UPDATE franchises
               SET province = COALESCE(NULLIF(province, ''), 'Unassigned'),
                   region = COALESCE(NULLIF(region, ''), COALESCE(NULLIF(province, ''), 'Unassigned'))
        """))


def downgrade():
    pass
