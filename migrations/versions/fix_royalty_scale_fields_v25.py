"""Move imported royalty scale text into structured bracket fields

Revision ID: fix_royalty_scale_fields_v25
Revises: import_contract_summary_v23
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
import re

revision = "fix_royalty_scale_fields_v25"
down_revision = "import_contract_summary_v23"
branch_labels = None
depends_on = None


def _clean(value):
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def _money(value):
    if value is None:
        return None
    text = str(value).replace("\xa0", " ")
    text = re.sub(r"[^0-9.,-]", "", text).replace(" ", "")
    if not text:
        return None
    if text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_line(value):
    raw = _clean(value)
    if not raw:
        return None
    percent_match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", raw)
    if not percent_match:
        return None
    percentage = _money(percent_match.group(1)) or 0
    before_percent = raw[:percent_match.start()].strip(" -")
    money_values = [_money(item) for item in re.findall(r"R\s*[0-9][0-9\s.,]*", before_percent, flags=re.I)]
    money_values = [item for item in money_values if item is not None]
    if len(money_values) >= 2:
        amount_from, amount_to = money_values[0], money_values[1]
    elif len(money_values) == 1:
        if re.search(r"or more|meer", raw, re.I):
            amount_from, amount_to = money_values[0], 999999999
        else:
            amount_from, amount_to = 0, money_values[0]
    else:
        amount_from, amount_to = 0, 999999999
    return amount_from, amount_to, percentage


def _table_exists(bind, table_name):
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name, column_name):
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    if not (_table_exists(bind, "franchises") and _table_exists(bind, "royalty_scales")):
        return
    if not _column_exists(bind, "franchises", "imported_royalty_scale_text"):
        return

    rows = bind.execute(sa.text("""
        SELECT id, imported_royalty_scale_text
        FROM franchises
        WHERE imported_royalty_scale_text IS NOT NULL
          AND TRIM(imported_royalty_scale_text) <> ''
    """)).fetchall()

    for franchise_id, raw_text in rows:
        parsed_rows = []
        for line in str(raw_text or "").splitlines():
            parsed = _parse_line(line)
            if parsed:
                parsed_rows.append(parsed)
        if not parsed_rows:
            continue
        bind.execute(sa.text("DELETE FROM royalty_scales WHERE franchise_id = :franchise_id"), {"franchise_id": franchise_id})
        for row_number, (amount_from, amount_to, percentage) in enumerate(parsed_rows, start=1):
            bind.execute(sa.text("""
                INSERT INTO royalty_scales (franchise_id, row_number, amount_from, amount_to, percentage)
                VALUES (:franchise_id, :row_number, :amount_from, :amount_to, :percentage)
            """), {
                "franchise_id": franchise_id,
                "row_number": row_number,
                "amount_from": amount_from,
                "amount_to": amount_to,
                "percentage": percentage,
            })
        bind.execute(sa.text("""
            UPDATE franchises
            SET imported_royalty_percentage = :percentage
            WHERE id = :franchise_id
        """), {"percentage": parsed_rows[0][2], "franchise_id": franchise_id})


def downgrade():
    pass
