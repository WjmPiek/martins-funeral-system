"""Core business repair for Data Integrity and Franchise Code workflow

Revision ID: v106_core_business_repair
Revises: v105_two_imports_franchise_code
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "v106_core_business_repair"
down_revision = "v105_two_imports_franchise_code"
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

    _ensure_column(bind, "franchises", "franchise_code", sa.Column("franchise_code", sa.String(length=80), nullable=True, server_default=""))
    _ensure_column(bind, "franchises", "province", sa.Column("province", sa.String(length=120), nullable=True, server_default="Unassigned"))
    _ensure_column(bind, "franchises", "region", sa.Column("region", sa.String(length=120), nullable=True, server_default=""))
    _ensure_column(bind, "franchises", "district", sa.Column("district", sa.String(length=120), nullable=True, server_default=""))
    _ensure_column(bind, "franchises", "municipality", sa.Column("municipality", sa.String(length=120), nullable=True, server_default=""))
    _ensure_column(bind, "franchises", "regional_manager_email", sa.Column("regional_manager_email", sa.String(length=255), nullable=True, server_default=""))
    _ensure_column(bind, "franchises", "finance_manager_email", sa.Column("finance_manager_email", sa.String(length=255), nullable=True, server_default=""))

    _ensure_index(bind, "franchises", "ix_franchises_franchise_code", ["franchise_code"])
    _ensure_index(bind, "franchises", "ix_franchises_province", ["province"])
    _ensure_index(bind, "franchises", "ix_franchises_region", ["region"])

    bind.execute(sa.text("UPDATE franchises SET province = 'Unassigned' WHERE COALESCE(province, '') = ''"))
    bind.execute(sa.text("UPDATE franchises SET region = province WHERE COALESCE(region, '') = '' AND COALESCE(province, '') <> ''"))

    # Allocate stable MF### codes to records that do not yet have one.
    rows = bind.execute(sa.text("SELECT id FROM franchises WHERE COALESCE(franchise_code, '') = '' ORDER BY business_name, id")).fetchall()
    used = {str(row[0]).upper() for row in bind.execute(sa.text("SELECT franchise_code FROM franchises WHERE COALESCE(franchise_code, '') <> ''")).fetchall()}
    next_number = 1
    for row in rows:
        while True:
            code = f"MF{next_number:03d}"
            next_number += 1
            if code not in used:
                used.add(code)
                break
        bind.execute(sa.text("UPDATE franchises SET franchise_code = :code WHERE id = :id"), {"code": code, "id": row[0]})


def downgrade():
    pass
