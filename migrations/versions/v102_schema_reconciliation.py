"""Merge stabilization branches and reconcile franchise region schema

Revision ID: v102_schema_reconciliation
Revises: v100_platform_stabilization, v100_region_ui_stabilization
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa


revision = "v102_schema_reconciliation"
down_revision = ("v100_platform_stabilization", "v100_region_ui_stabilization")
branch_labels = None
depends_on = None

PROVINCE_TERMS = {
    "Gauteng": ["alberton", "benoni", "boksburg", "brakpan", "springs", "edenvale", "germiston", "katlehong", "vosloorus", "tsakane", "thokoza", "tokoza", "tembisa", "midrand", "pretoria", "soshanguve", "sochanguve", "mamelodi", "atteridgeville", "centurion", "hammanskraal", "vereeniging", "vanderbijlpark", "meyerton", "sebokeng", "orange farm", "lenasia", "three rivers", "florida", "fountainbleau", "carletonville", "randfontein", "krugersdorp", "roodepoort", "soweto", "sandton", "randburg", "johannesburg"],
    "Western Cape": ["cape town", "brackenfell", "bellville", "paarl", "parow", "kraaifontein", "kuils river", "durbanville", "table view", "stellenbosch", "strand", "somerset west", "worcester", "george", "mossel bay", "mosselbaai", "oudtshoorn", "knysna", "plettenberg", "beaufort west", "malmesbury", "vredenburg", "saldanha", "hermanus", "caledon", "robertson", "wellington"],
    "KwaZulu-Natal": ["durban", "pinetown", "phoenix", "umlazi", "umhlanga", "chatsworth", "isipingo", "kwamashu", "verulam", "tongaat", "pietermaritzburg", "empangeni", "richards bay", "ladysmith", "newcastle", "estcourt", "kokstad", "port shepstone", "margate", "vryheid", "eshowe", "ulundi", "stanger", "kwadukuza", "ballito"],
    "Eastern Cape": ["gqeberha", "port elizabeth", "east london", "mthatha", "umtata", "queenstown", "komani", "jeffreys bay", "jeffreys baai", "jeffreysbaai", "humansdorp", "uitenhage", "kariega", "grahamstown", "makhanda", "cradock", "graaff", "butterworth"],
    "Limpopo": ["polokwane", "pietersburg", "tzaneen", "mokopane", "potgietersrus", "mookgophong", "mookgopong", "modimolle", "nylstroom", "bela-bela", "belabela", "thohoyandou", "louis trichardt", "makhado", "giyani", "phalaborwa", "lephalale", "ellisras", "musina", "seshego"],
    "Mpumalanga": ["mbombela", "nelspruit", "witbank", "emalahleni", "middelburg", "secunda", "evander", "bethal", "ermelo", "piet retief", "barberton", "lydenburg", "white river", "hazyview", "komatipoort", "standerton", "volksrust", "delmas", "kriel"],
    "North West": ["rustenburg", "klerksdorp", "potchefstroom", "mahikeng", "mafikeng", "brits", "lichtenburg", "vryburg", "orkney", "stilfontein", "hartbeespoort", "zeerust", "taung", "wolmaransstad", "christiana"],
    "Free State": ["bloemfontein", "welkom", "bethlehem", "kroonstad", "sasolburg", "sasolsburg", "virginia", "harrismith", "parys", "ficksburg", "phuthaditjhaba", "botshabelo", "ladybrand", "senekal", "heilbron"],
    "Northern Cape": ["kimberley", "upington", "kuruman", "springbok", "de aar", "postmasburg", "kathu", "hartswater", "colesberg", "calvinia", "prieska", "douglas", "jan kempdorp", "barkly west", "warrenton", "hopetown"],
}


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


def _backfill_regions(bind):
    if not _table_exists(bind, "franchises") or "province" not in _columns(bind, "franchises"):
        return
    for province, terms in PROVINCE_TERMS.items():
        for term in terms:
            bind.execute(sa.text("""
                UPDATE franchises
                   SET province = :province
                 WHERE COALESCE(province, '') IN ('', 'Unassigned')
                   AND LOWER(COALESCE(business_name, '')) LIKE :pattern
            """), {"province": province, "pattern": f"%{term.lower()}%"})
    bind.execute(sa.text("UPDATE franchises SET province = 'Unassigned' WHERE COALESCE(province, '') = ''"))


def upgrade():
    bind = op.get_bind()

    # This migration intentionally merges v100_platform_stabilization and
    # v100_region_ui_stabilization into one Alembic head and is also defensive:
    # if a production database missed one branch, ensure the columns/data exist.
    if _table_exists(bind, "franchises"):
        _ensure_column(bind, "franchises", "province", sa.Column("province", sa.String(length=120), nullable=True, server_default=""))
        _ensure_index(bind, "franchises", "ix_franchises_province", ["province"])
        _backfill_regions(bind)

    if _table_exists(bind, "royalty_growth_profiles"):
        bind.execute(sa.text("""
            INSERT INTO royalty_growth_profiles
                (name, source, default_growth_percent, scope_type, is_active, notes, created_at, updated_at)
            VALUES
                ('South Africa GDP Standard', 'SA GDP standard', 1.6000, 'global', TRUE,
                 'Default royalty target growth policy. Admin may change this; franchise users do not see it.',
                 NOW(), NOW())
            ON CONFLICT (name) DO NOTHING
        """))

    if _table_exists(bind, "monthly_figures"):
        cols = _columns(bind, "monthly_figures")
        numeric_cols = [
            "gross_turnover", "cash", "card", "eft", "policies", "sales",
            "payover", "royalty_percentage", "royalty_amount", "number_of_funerals",
            "insurance_joinings", "mf_files", "gross_revenue", "insurance_payover", "admin_fee",
        ]
        assignments = [f"{col} = COALESCE({col}, 0)" for col in numeric_cols if col in cols]
        if assignments:
            bind.execute(sa.text("UPDATE monthly_figures SET " + ", ".join(assignments)))


def downgrade():
    # This is a reconciliation/merge migration. Do not drop repaired columns/data.
    pass
