from decimal import Decimal
import re
from types import SimpleNamespace

from app.extensions import db
from app.models import Franchise, MonthlyFigure, User, user_franchises


FRANCHISE_SIDE_ROLES = {"Franchise User", "Franchise Manager", "Read Only User"}
SUM_MONEY_FIELDS = (
    "funeral_receipts",
    "claim_receipts",
    "society_receipts",
    "cash_sales",
    "tombstone_receipts",
    "obo_service_receipts",
    "insurance_receipts",
    "insurance_payover",
)
SUM_COUNT_FIELDS = ("insurance_joinings", "mf_files", "number_of_funerals")


def _identity_key(value):
    text = (value or "").strip().lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\b(martins?|funerals?|franchise|branch|user|system|pty|ltd)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def _user_identity_keys(user):
    values = [
        getattr(user, "business_name", None),
        getattr(user, "full_name", None),
        getattr(user, "name", None),
        getattr(user, "username", None),
    ]
    email = getattr(user, "email", None)
    if email and "@" in email:
        values.append(email.split("@", 1)[0])
    keys = {_identity_key(value) for value in values if value}
    return {key for key in keys if len(key) >= 3}


def _identity_matched_main_franchise(user, linked):
    user_keys = _user_identity_keys(user)
    if not user_keys:
        return None
    for franchise in linked:
        franchise_key = _identity_key(getattr(franchise, "business_name", None))
        if not franchise_key:
            continue
        if franchise_key in user_keys:
            return franchise
        if any(len(key) >= 5 and (franchise_key in key or key in franchise_key) for key in user_keys):
            return franchise
    return None


def identity_main_franchise_for_user(user, candidates=None):
    candidates = list(candidates or [])
    main = _identity_matched_main_franchise(user, candidates)
    if main:
        return main
    all_franchises = Franchise.query.order_by(Franchise.business_name).all()
    return _identity_matched_main_franchise(user, all_franchises)


def _ordered_linked_franchises_for_user(user):
    linked = list(getattr(user, "assigned_franchises", []) or [])
    primary_id = db.session.execute(
        db.select(user_franchises.c.franchise_id)
        .where(user_franchises.c.user_id == user.id)
        .where(user_franchises.c.is_primary == True)
    ).scalar()
    linked_sorted = sorted(linked, key=lambda item: item.business_name or "")
    identity_main = identity_main_franchise_for_user(user, linked_sorted)
    if identity_main:
        rest = [item for item in linked_sorted if item.id != identity_main.id]
        return [identity_main] + rest
    if primary_id:
        primary = [item for item in linked_sorted if item.id == primary_id]
        rest = [item for item in linked_sorted if item.id != primary_id]
        return primary + rest
    return linked_sorted


def ordered_linked_franchises_for_user(user):
    return _ordered_linked_franchises_for_user(user)


def normalise_franchise_user_links(user, selected_franchises):
    """Keep a franchise user's Business Name franchise as the main grouped branch."""
    selected = list(selected_franchises or [])
    main = identity_main_franchise_for_user(user, selected)
    if not main:
        return sorted(selected, key=lambda item: item.business_name or ""), None
    rest = sorted([item for item in selected if item.id != main.id], key=lambda item: item.business_name or "")
    return [main] + rest, main


def mark_primary_franchise_link(user, main_franchise):
    if not user or not main_franchise:
        return
    db.session.flush()
    db.session.execute(user_franchises.update().where(user_franchises.c.user_id == user.id).values(is_primary=False))
    db.session.execute(
        user_franchises.update()
        .where(user_franchises.c.user_id == user.id)
        .where(user_franchises.c.franchise_id == main_franchise.id)
        .values(is_primary=True)
    )


def grouped_franchise_sets(touched_franchise_ids=None):
    touched = {int(item) for item in (touched_franchise_ids or []) if item}
    groups = []
    users = User.query.all()
    for user in users:
        role_names = {role.name for role in getattr(user, "roles", [])}
        if not (role_names & FRANCHISE_SIDE_ROLES):
            continue
        linked = _ordered_linked_franchises_for_user(user)
        if len(linked) < 2:
            continue
        linked_ids = {franchise.id for franchise in linked}
        if touched and not (linked_ids & touched):
            continue
        groups.append({"user": user, "main": linked[0], "linked": linked})
    return groups


def _money_total(rows, field):
    return sum((Decimal(getattr(row, field, 0) or 0) for row in rows), Decimal("0"))


def _count_total(rows, field):
    return sum(int(getattr(row, field, 0) or 0) for row in rows)


def _append_note(row, note):
    existing = (getattr(row, "notes", "") or "").strip()
    if note in existing:
        return
    row.notes = f"{existing}\n{note}".strip() if existing else note


def apply_grouped_royalties_for_period(month, year, touched_franchise_ids=None):
    """Calculate branch rows without replacing them with grouped totals.

    Grouped totals are built as virtual rows in the monthly/royalty views so
    each franchise still shows its own imported figures and calculated royalty.
    """
    from app.royalty_engine import calculate_monthly_figure

    updated = 0
    grouped = 0
    for group in grouped_franchise_sets(touched_franchise_ids):
        main = group["main"]
        linked = group["linked"]
        linked_ids = [franchise.id for franchise in linked]
        rows = MonthlyFigure.query.filter(
            MonthlyFigure.month == month,
            MonthlyFigure.year == year,
            MonthlyFigure.franchise_id.in_(linked_ids),
        ).all()
        if not rows:
            continue

        rows_by_franchise = {row.franchise_id: row for row in rows}
        for row in rows:
            calculate_monthly_figure(row)
            updated += 1

        grouped += 1
    return {"groups": grouped, "rows": updated}
