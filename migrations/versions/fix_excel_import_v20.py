"""fix group Excel import and remove accidental total/data franchises v2.0

Revision ID: fix_excel_import_v20
Revises: fix_users_by_franchise_v15
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "fix_excel_import_v20"
down_revision = "fix_users_by_franchise_v15"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    bad_names = ["total", "totals", "data"]
    franchise_rows = conn.execute(sa.text(
        "SELECT id FROM franchises WHERE lower(trim(business_name)) IN :names"
    ).bindparams(sa.bindparam("names", expanding=True)), {"names": bad_names}).fetchall()
    franchise_ids = [row.id for row in franchise_rows]

    if franchise_ids:
        conn.execute(sa.text("DELETE FROM monthly_figures WHERE franchise_id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ), {"ids": franchise_ids})
        conn.execute(sa.text("DELETE FROM royalty_scales WHERE franchise_id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ), {"ids": franchise_ids})
        conn.execute(sa.text("DELETE FROM user_franchises WHERE franchise_id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ), {"ids": franchise_ids})
        conn.execute(sa.text("DELETE FROM franchises WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ), {"ids": franchise_ids})

    bad_emails = ["total@martinsdirect.com", "totals@martinsdirect.com", "data@martinsdirect.com"]
    user_rows = conn.execute(sa.text(
        "SELECT id FROM users WHERE lower(trim(email)) IN :emails"
    ).bindparams(sa.bindparam("emails", expanding=True)), {"emails": bad_emails}).fetchall()
    user_ids = [row.id for row in user_rows]
    if user_ids:
        conn.execute(sa.text("DELETE FROM user_franchises WHERE user_id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ), {"ids": user_ids})
        conn.execute(sa.text("DELETE FROM user_roles WHERE user_id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ), {"ids": user_ids})
        conn.execute(sa.text("DELETE FROM users WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ), {"ids": user_ids})


def downgrade():
    pass
