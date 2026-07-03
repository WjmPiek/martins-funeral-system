"""Region assignment and dashboard text stabilization

Revision ID: v100_region_ui_stabilization
Revises: v99_workflow_engine
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "v100_region_ui_stabilization"
down_revision = "v99_workflow_engine"
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


def upgrade():
    with op.batch_alter_table("franchises") as batch_op:
        batch_op.add_column(sa.Column("province", sa.String(length=120), nullable=True, server_default=""))
    op.create_index("ix_franchises_province", "franchises", ["province"], unique=False)

    conn = op.get_bind()
    for province, terms in PROVINCE_TERMS.items():
        for term in terms:
            conn.execute(sa.text("""
                UPDATE franchises
                   SET province = :province
                 WHERE COALESCE(province, '') = ''
                   AND LOWER(COALESCE(business_name, '')) LIKE :pattern
            """), {"province": province, "pattern": f"%{term.lower()}%"})
    conn.execute(sa.text("UPDATE franchises SET province = 'Unassigned' WHERE COALESCE(province, '') = ''"))


def downgrade():
    op.drop_index("ix_franchises_province", table_name="franchises")
    with op.batch_alter_table("franchises") as batch_op:
        batch_op.drop_column("province")
