"""Province/region helpers for Martins franchise reporting.

The system receives many franchises by branch/town name only.  This helper keeps
province assignment deterministic so Executive Dashboard, BI, Insights and
Performance Graph province filters do not depend on heatmap rows being present.
"""
from __future__ import annotations

import re
from typing import Iterable

PROVINCES = [
    "Eastern Cape",
    "Free State",
    "Gauteng",
    "KwaZulu-Natal",
    "Limpopo",
    "Mpumalanga",
    "North West",
    "Northern Cape",
    "Western Cape",
]

# Ordered from more specific to less specific.  The names are intentionally
# branch/town-focused because franchise records often only contain business_name.
PROVINCE_KEYWORDS = {
    "Western Cape": [
        "cape town", "kaapstad", "athlone", "bellville", "belhar", "blue downs", "brackenfell",
        "cape gate", "claremont", "durbanville", "elsies river", "fish hoek", "goodwood",
        "gugulethu", "kraaifontein", "kuils river", "langa", "mitchells plain", "mowbray",
        "paarl", "parow", "pinelands", "stellenbosch", "strand", "somerset west", "table view",
        "tygerberg", "wynberg", "worcester", "george", "mossel bay", "mosselbaai", "oudtshoorn",
        "knysna", "plettenberg", "plettenberg bay", "beaufort west", "ceres", "malmesbury",
        "saldanha", "vredenburg", "velddrif", "hopefield", "caledon", "hermanus", "robertson",
        "swellendam", "wellington", "worchester", "stellenbosch", "grabouw", "ladismith",
    ],
    "Eastern Cape": [
        "gqeberha", "port elizabeth", "qeberha", "east london", "mthatha", "umtata", "queenstown",
        "komani", "grahamstown", "makhanda", "jeffreys bay", "jeffreysbaai", "jeffreys baai",
        "humansdorp", "uitenhage", "kariega", "king william", "bhisho", "butterworth", "cradock",
        "graaff-reinet", "graaff reinet", "fort beaufort", "alice", "stutterheim", "uitenhage",
    ],
    "KwaZulu-Natal": [
        "durban", "pinetown", "phoenix", "umlazi", "umhlanga", "chatsworth", "isipingo",
        "kwamashu", "verulam", "tongaat", "pietermaritzburg", "pm b", "empangeni", "richards bay",
        "ladysmith", "newcastle", "estcourt", "kokstad", "port shepstone", "margate", "ixopo",
        "greytown", "vryheid", "eshowe", "ulundi", "mandeni", "stanger", "kwadukuza", "mooi river",
        "hibberdene", "howick", "hillcrest", "ballito", "mtubatuba", "melmoth",
    ],
    "Gauteng": [
        "johannesburg", "joburg", "jozi", "soweto", "sandton", "randburg", "roodepoort",
        "krugersdorp", "mogale", "alberton", "benoni", "boksburg", "brakpan", "springs", "edenvale",
        "kempton park", "germiston", "katlehong", "vosloorus", "tsakane", "tokoza", "thokoza",
        "tembisa", "tembisa", "midrand", "pretoria", "tshwane", "mamelodi", "soshanguve",
        "sochanguve", "atteridgeville", "centurion", "akasia", "olivenhoutbosch", "garankuwa",
        "ga-rankuwa", "hammanskraal", "vereeniging", "vanderbijlpark", "meyerton", "sasolburg",
        "sebokeng", "orange farm", "lenasia", "ennerdale", "three rivers", "florida", "fountainbleau",
        "carletonville", "westonaria", "randfontein", "diepsloot", "alexandra", "ivory park", "pretoria stad",
    ],
    "Mpumalanga": [
        "mbombela", "nelspruit", "witbank", "emalahleni", "middelburg", "secunda", "evander",
        "bethal", "ermelo", "piet retief", "mkhondo", "barberton", "lydenburg", "mashishing",
        "white river", "hazyview", "komatipoort", "standerton", "volksrust", "delmas", "kriel",
        "hendrina", "balfour", "acornhoek", "bushbuckridge", "graskop", "sabie",
    ],
    "Limpopo": [
        "polokwane", "pietersburg", "tzaneen", "mokopane", "potgietersrus", "mookgophong",
        "mookgopong", "naboomspruit", "modimolle", "nylstroom", "bela-bela", "belabela",
        "thohoyandou", "louis trichardt", "makhado", "giyani", "phalaborwa", "lephalale", "ellisras",
        "musina", "mankweng", "seshego", "lebowakgomo", "mokopane", "warmbaths",
    ],
    "North West": [
        "rustenburg", "klerksdorp", "potchefstroom", "mahikeng", "mafikeng", "brits", "lichtenburg",
        "vryburg", "orkney", "stilfontein", "hartbeespoort", "zeerust", "taung", "wolmaransstad",
        "schweizer-reneke", "schweizer reneke", "christiana", "mmabatho", "delareyville",
    ],
    "Free State": [
        "bloemfontein", "welkom", "bethlehem", "kroonstad", "sasolsburg", "sasolburg", "virginia",
        "harrismith", "parys", "ficksburg", "phuthaditjhaba", "botshabelo", "ladybrand", "senekal",
        "heilbron", "theunissen", "ventersburg", "clocolan", "reitz", "frankfort", "deneysville",
    ],
    "Northern Cape": [
        "kimberley", "upington", "kuruman", "springbok", "de aar", "postmasburg", "kathu", "hartswater",
        "colesberg", "calvinia", "prieska", "douglas", "jan kempdorp", "barkly west", "warrenton",
        "hopetown", "keimoes", "kakamas", "pofadder", "groblershoop",
    ],
}

_PROVINCE_ALIASES = {
    "kzn": "KwaZulu-Natal",
    "kwazulu natal": "KwaZulu-Natal",
    "kwa-zulu natal": "KwaZulu-Natal",
    "gp": "Gauteng",
    "wc": "Western Cape",
    "ec": "Eastern Cape",
    "fs": "Free State",
    "nw": "North West",
    "nc": "Northern Cape",
}


def normalize_region_text(value: object) -> str:
    text = str(value or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_province(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    norm = normalize_region_text(raw)
    if norm in _PROVINCE_ALIASES:
        return _PROVINCE_ALIASES[norm]
    for province in PROVINCES:
        if norm == normalize_region_text(province):
            return province
    return raw


def infer_province_from_franchise_name(name: object) -> str:
    norm = normalize_region_text(name)
    if not norm:
        return "Unassigned"

    # If the province name itself appears in the franchise name, use that first.
    for province in PROVINCES:
        p_norm = normalize_region_text(province)
        if re.search(rf"(^|\s){re.escape(p_norm)}($|\s)", norm):
            return province

    for province, keywords in PROVINCE_KEYWORDS.items():
        for keyword in keywords:
            k = normalize_region_text(keyword)
            if not k:
                continue
            if re.search(rf"(^|\s){re.escape(k)}($|\s)", norm):
                return province
    return "Unassigned"


def province_options_from_names(names: Iterable[object]) -> list[str]:
    provinces = {infer_province_from_franchise_name(name) for name in names}
    provinces.discard("")
    provinces.discard("Unassigned")
    return sorted(provinces, key=lambda value: PROVINCES.index(value) if value in PROVINCES else 999)
