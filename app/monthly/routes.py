from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
import re
from difflib import SequenceMatcher
import shutil
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
from werkzeug.utils import secure_filename

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file, current_app, session
from flask_login import login_required, current_user

from app.audit import log_action
from app.extensions import db
from app.franchise.routes import get_or_create_franchise
from app.franchise_context import get_selected_franchise, get_accessible_franchises, is_privileged_user, is_franchise_view_mode
from app.models import MonthlyFigure, RoyaltyScale, Franchise, User, Role, user_franchises

monthly_bp = Blueprint("monthly", __name__, url_prefix="/monthly-figures")


MONTHS = [
    (1, "January"), (2, "February"), (3, "March"), (4, "April"),
    (5, "May"), (6, "June"), (7, "July"), (8, "August"),
    (9, "September"), (10, "October"), (11, "November"), (12, "December"),
]


def current_reporting_period():
    now = datetime.now()
    return now.month, now.year


def selected_reporting_period():
    default_month, default_year = current_reporting_period()
    try:
        month = int(request.args.get("month", default_month))
    except (TypeError, ValueError):
        month = default_month
    try:
        year = int(request.args.get("year", default_year))
    except (TypeError, ValueError):
        year = default_year
    if month < 1 or month > 12:
        month = default_month
    if year < 2000 or year > 2100:
        year = default_year
    return month, year


def month_label(month, year):
    month_name = dict(MONTHS).get(int(month), str(month))
    return f"{month_name} {year}"


def reporting_years():
    default_month, current_year = current_reporting_period()
    years = [row[0] for row in db.session.query(MonthlyFigure.year).distinct().order_by(MonthlyFigure.year.desc()).all()]
    if current_year not in years:
        years.insert(0, current_year)
    return years

IMPORT_FIELDS = [
    ("gross_turnover", "GROSS TURNOVER"),
    ("cash", "CASH"),
    ("funeral_receipts", "Funeral Receipts"),
    ("society_receipts", "Society Receipts"),
    ("cash_sales", "Cash Sales"),
    ("tombstone_receipts", "Tombstone Receipts"),
    ("obo_service_receipts", "OBO Services Receipts"),
    ("sales", "SALES"),
    ("insurance_receipts", "INSURANCE RECEIPTS"),
    ("insurance_payover", "INSURANCE PAYOVER"),
    ("admin_fee", "ADMIN FEE"),
    ("insurance_joinings", "INSURANCE JOININGS"),
    ("mf_files", "MF FILES"),
]


def can_import_monthly_figures():
    return current_user.has_permission("monthly_figures:import")


def current_user_role_names():
    return {role.name for role in getattr(current_user, "roles", [])}


def is_current_user_admin():
    return "Admin" in current_user_role_names()


def is_current_user_finance_import_user():
    return bool(current_user_role_names() & {"Finance Manager", "Finance Assistant"})


def can_access_pdf_import():
    return is_current_user_admin() or is_current_user_finance_import_user()


def can_delete_monthly_figures():
    return current_user.has_permission("monthly_figures:approve")



def current_user_role_names():
    return {role.name for role in getattr(current_user, "roles", [])}


def is_franchise_side_user():
    return bool(current_user_role_names() & {"Franchise User", "Franchise Manager", "Read Only User"})


def get_ordered_linked_franchises_for_user(user):
    linked = list(getattr(user, "assigned_franchises", []) or [])
    if not linked:
        return []
    primary_id = db.session.execute(
        db.select(user_franchises.c.franchise_id)
        .where(user_franchises.c.user_id == user.id)
        .where(user_franchises.c.is_primary == True)
    ).scalar()
    linked_sorted = sorted(linked, key=lambda item: item.business_name or "")
    if primary_id:
        primary = [item for item in linked_sorted if item.id == primary_id]
        rest = [item for item in linked_sorted if item.id != primary_id]
        return primary + rest
    return linked_sorted


def get_group_user_for_selected_franchise(selected_franchise):
    """Find the franchise-side user group that contains the selected franchise."""
    if not selected_franchise:
        return None
    selected_id = getattr(selected_franchise, "id", None)
    franchise_side_roles = {"Franchise User", "Franchise Manager", "Read Only User"}
    candidates = []
    for user in User.query.all():
        user_roles = {role.name for role in getattr(user, "roles", [])}
        if not (user_roles & franchise_side_roles):
            continue
        linked = get_ordered_linked_franchises_for_user(user)
        if len(linked) < 2:
            continue
        if any(franchise.id == selected_id for franchise in linked):
            primary = get_primary_franchise_for_user(user, linked)
            candidates.append((0 if primary and primary.id == selected_id else 1, user))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def build_grouped_monthly_totals(figures, main_franchise, selected_month, selected_year):
    if not figures or not main_franchise:
        return None

    def total(field):
        return sum(Decimal(getattr(item, field, 0) or 0) for item in figures)

    grouped = SimpleNamespace()
    grouped.is_grouped = True
    grouped.franchise = main_franchise
    grouped.franchise_id = main_franchise.id
    grouped.month = selected_month
    grouped.year = selected_year
    grouped.period_label = f"{selected_year}-{selected_month:02d}"
    grouped.status = "Grouped Total"
    grouped.source_figures = figures
    grouped.source_branch_names = [getattr(getattr(item, "franchise", None), "business_name", "Unnamed Franchise") for item in figures]

    grouped.funeral_receipts = total("funeral_receipts")
    grouped.society_receipts = total("society_receipts")
    grouped.cash_sales = total("cash_sales")
    grouped.tombstone_receipts = total("tombstone_receipts")
    grouped.obo_service_receipts = total("obo_service_receipts")
    grouped.sales = total("sales")
    grouped.insurance_receipts = total("insurance_receipts")
    grouped.insurance_payover = total("insurance_payover")
    grouped.admin_fee = total("admin_fee")
    grouped.insurance_joinings = sum(int(getattr(item, "insurance_joinings", 0) or 0) for item in figures)
    grouped.mf_files = sum(int(getattr(item, "mf_files", 0) or 0) for item in figures)
    grouped.cash = grouped.sales + grouped.insurance_receipts
    royalty_base, gross_method = calculate_royalty_base(grouped, main_franchise)
    grouped.gross_turnover = royalty_base
    grouped.gross_revenue = royalty_base
    grouped.gross_method = gross_method
    _gross, percentage, royalty_amount, minimum_applied = calculate_royalty(main_franchise, royalty_base)
    grouped.royalty_percentage = percentage
    grouped.royalty_amount = royalty_amount
    grouped.minimum_royalty_applied = minimum_applied
    return grouped

def get_primary_franchise_for_user(user, linked_franchises):
    if not user or not linked_franchises:
        return None
    primary_id = db.session.execute(
        db.select(user_franchises.c.franchise_id)
        .where(user_franchises.c.user_id == user.id)
        .where(user_franchises.c.is_primary == True)
    ).scalar()
    if primary_id:
        for franchise in linked_franchises:
            if franchise.id == primary_id:
                return franchise
    return linked_franchises[0]


def build_figures_by_branch(figures, linked_franchises=None):
    by_id = {}
    for item in figures:
        fid = item.franchise_id
        by_id.setdefault(fid, []).append(item)
    ordered = []
    source_franchises = linked_franchises or [getattr(item, "franchise", None) for item in figures]
    seen = set()
    for franchise in source_franchises:
        if not franchise or franchise.id in seen:
            continue
        seen.add(franchise.id)
        ordered.append({
            "franchise": franchise,
            "figures": by_id.get(franchise.id, []),
        })
    return ordered


def permission_required(code):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.has_permission(code):
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def parse_decimal(value, default="0"):
    try:
        cleaned = (
            str(value or default)
            .replace("R", "")
            .replace(",", "")
            .replace(" ", "")
            .strip()
        )
        return Decimal(cleaned or default)
    except (InvalidOperation, ValueError):
        return Decimal(default)

def parse_int(value, default=0):
    try:
        return int(Decimal(str(value or default).replace(",", "").strip()))
    except (InvalidOperation, TypeError, ValueError):
        return default


def format_currency(value):
    return f"{Decimal(value or 0):,.2f}"


def normalize_gross_method(value):
    """Return canonical royalty gross method: ``new`` or ``old``.

    Older imports/databases may store display text such as ``Gross = Old``,
    ``Gross Old`` or ``Gross = New Gross Method`` instead of only ``old``/``new``.
    Treat those labels as valid before falling back to agreement date.
    """
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text in {"new", "gross new", "new gross", "gross new gross method", "new gross method"}:
        return "new"
    if text in {"old", "gross old", "old gross"}:
        return "old"
    if "new" in text:
        return "new"
    if "old" in text:
        return "old"
    return ""


def get_franchise_gross_method(franchise):
    """Return the franchise's gross method.

    Old Gross = SALES + INSURANCE RECEIPTS.
    New Gross = SALES + ADMIN FEE.
    If an older record has no stored method, fall back to the agreement start date:
    2018 or newer = New; before 2018 or missing = Old.
    """
    stored_method = normalize_gross_method(getattr(franchise, "royalty_gross_method", ""))
    if stored_method in {"new", "old"}:
        return stored_method

    start_date = getattr(franchise, "agreement_start_date", None)
    if start_date and getattr(start_date, "year", 0) >= 2018:
        return "new"
    return "old"


def gross_method_label(method):
    return "Gross = New Gross Method" if method == "new" else "Gross = Old"


def calculate_sales_for_royalty(monthly_figure):
    """Return the SALES component used for royalty calculations.

    SALES must include Society Receipts for both Gross = New and Gross = Old:
    Funeral Receipts + Society Receipts + Cash Sales + Tombstone Receipts + OBO Services Receipts.
    This uses the source fields directly so older records are corrected even if their saved sales field excluded society receipts.
    """
    return (
        Decimal(monthly_figure.funeral_receipts or 0)
        + Decimal(monthly_figure.society_receipts or 0)
        + Decimal(monthly_figure.cash_sales or 0)
        + Decimal(monthly_figure.tombstone_receipts or 0)
        + Decimal(monthly_figure.obo_service_receipts or 0)
    )


def calculate_royalty_base(monthly_figure, franchise):
    method = get_franchise_gross_method(franchise)
    sales = calculate_sales_for_royalty(monthly_figure)
    if method == "new":
        royalty_base = sales + Decimal(monthly_figure.admin_fee or 0)
    else:
        # Old Gross: SALES + INSURANCE RECEIPTS. Blank/zero insurance receipts still gives SALES.
        royalty_base = sales + Decimal(monthly_figure.insurance_receipts or 0)
    if royalty_base < 0:
        royalty_base = Decimal("0")
    return royalty_base, method


def normalize_franchise_name_for_royalties(value):
    text = (value or "").strip().lower()
    text = re.sub(r"\(f\)", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _decimal_from_text(value):
    """Parse money/percentage text such as 'R2 000 000.00' or '2.5'."""
    if value is None:
        return None
    text = str(value).replace("\xa0", " ")
    text = re.sub(r"[^0-9.,-]", "", text).replace(" ", "")
    if not text or text in {"-", ".", ","}:
        return None
    if text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _parse_royalty_scale_text(raw_text):
    """Parse fallback royalty brackets from Franchise.imported_royalty_scale_text.

    This prevents the royalty percentage from staying at 0.00% when the raw
    contract-summary text exists but the structured royalty_scales rows were not
    created or were linked to a slightly different branch name.
    """
    rows = []
    if not raw_text:
        return rows
    for row_number, line in enumerate(str(raw_text).replace(";", "\n").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        percent_match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", line)
        if not percent_match:
            continue
        percentage = _decimal_from_text(percent_match.group(1)) or Decimal("0")
        before_percent = line[:percent_match.start()]
        amount_tokens = re.findall(r"R?\s*\d[\d\s.,]*", before_percent, flags=re.I)
        amounts = [_decimal_from_text(token) for token in amount_tokens]
        amounts = [amount for amount in amounts if amount is not None]
        if len(amounts) >= 2:
            amount_from, amount_to = amounts[0], amounts[1]
        elif len(amounts) == 1:
            if re.search(r"or more|meer", line, re.I):
                amount_from, amount_to = amounts[0], Decimal("999999999")
            else:
                amount_from, amount_to = Decimal("0"), amounts[0]
        else:
            amount_from, amount_to = Decimal("0"), Decimal("999999999")
        rows.append(SimpleNamespace(
            row_number=row_number,
            amount_from=amount_from,
            amount_to=amount_to,
            percentage=percentage,
        ))
    return rows


def _normalise_royalty_scale_rows(scales):
    """Return usable royalty brackets, keeping open-ended final brackets.

    Amount To of 0/blank is treated as open-ended.  This is important because
    several franchise scale sheets use the last row as "and above" and older
    imports sometimes saved that final Amount To as 0.
    """
    rows = []
    for index, scale in enumerate(scales or [], start=1):
        amount_from = Decimal(getattr(scale, "amount_from", 0) or 0)
        amount_to = Decimal(getattr(scale, "amount_to", 0) or 0)
        percentage = Decimal(getattr(scale, "percentage", 0) or 0)
        if percentage <= 0:
            continue
        if amount_to <= 0:
            amount_to = Decimal("999999999999")
        if amount_to < amount_from:
            continue
        rows.append(SimpleNamespace(
            row_number=getattr(scale, "row_number", index) or index,
            amount_from=amount_from,
            amount_to=amount_to,
            percentage=percentage,
        ))
    return sorted(rows, key=lambda item: (item.amount_from, item.amount_to, item.row_number))


def get_royalty_scales_for_franchise(franchise):
    """Return the bracket scale that belongs to the selected franchise.

    Priority is now:
    1. This franchise user's structured RoyaltyScale rows.
    2. This franchise user's imported raw scale text.
    3. A matching franchise record's structured/raw scale rows.
    4. This franchise user's imported single percentage as a last resort.

    The previous fallback could use imported_royalty_percentage before checking
    matching structured brackets, which caused some franchise users to calculate
    one flat percentage instead of the correct bracket percentage.
    """
    if not franchise:
        return []

    own_scales = RoyaltyScale.query.filter_by(franchise_id=franchise.id).order_by(
        RoyaltyScale.row_number,
        RoyaltyScale.amount_from,
        RoyaltyScale.id,
    ).all()
    own_valid_scales = _normalise_royalty_scale_rows(own_scales)
    if own_valid_scales:
        return own_valid_scales

    parsed_raw = _normalise_royalty_scale_rows(
        _parse_royalty_scale_text(getattr(franchise, "imported_royalty_scale_text", ""))
    )
    if parsed_raw:
        return parsed_raw

    wanted = normalize_franchise_name_for_royalties(getattr(franchise, "business_name", ""))
    if wanted:
        candidates = []
        for candidate in Franchise.query.all():
            if candidate.id == franchise.id:
                continue
            key = normalize_franchise_name_for_royalties(candidate.business_name)
            if not key:
                continue
            ratio = SequenceMatcher(None, wanted, key).ratio()
            if key == wanted or wanted in key or key in wanted or ratio >= 0.84:
                candidates.append((ratio, candidate))

        for _ratio, candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
            candidate_scales = RoyaltyScale.query.filter_by(franchise_id=candidate.id).order_by(
                RoyaltyScale.row_number,
                RoyaltyScale.amount_from,
                RoyaltyScale.id,
            ).all()
            valid_candidate_scales = _normalise_royalty_scale_rows(candidate_scales)
            if valid_candidate_scales:
                return valid_candidate_scales

            parsed_candidate_raw = _normalise_royalty_scale_rows(
                _parse_royalty_scale_text(getattr(candidate, "imported_royalty_scale_text", ""))
            )
            if parsed_candidate_raw:
                return parsed_candidate_raw

    imported_percentage = Decimal(getattr(franchise, "imported_royalty_percentage", 0) or 0)
    if imported_percentage > 0:
        return [SimpleNamespace(
            row_number=1,
            amount_from=Decimal("0"),
            amount_to=Decimal("999999999999"),
            percentage=imported_percentage,
        )]

    return []

def calculate_royalty(franchise, royalty_base):
    if royalty_base < 0:
        royalty_base = Decimal("0")

    scales = get_royalty_scales_for_franchise(franchise)
    percentage = Decimal("0")

    for scale in scales:
        amount_from = Decimal(getattr(scale, "amount_from", 0) or 0)
        amount_to = Decimal(getattr(scale, "amount_to", 0) or 0)
        if amount_to <= 0:
            amount_to = Decimal("999999999999")

        if royalty_base >= amount_from and royalty_base <= amount_to:
            percentage = Decimal(getattr(scale, "percentage", 0) or 0)
            break

    # If the base is above the highest configured bracket, use the final bracket
    # instead of returning 0%. This protects imported scales where the last
    # "or more" row was saved without a high Amount To.
    if percentage == 0 and scales:
        highest = max(scales, key=lambda s: Decimal(getattr(s, "amount_to", 0) or 0))
        if royalty_base >= Decimal(getattr(highest, "amount_from", 0) or 0):
            percentage = Decimal(getattr(highest, "percentage", 0) or 0)

    calculated_royalty = (royalty_base * percentage) / Decimal("100")
    minimum = Decimal(getattr(franchise, "minimum_royalty_amount", 0) or 0)
    minimum_applied = minimum > 0 and calculated_royalty < minimum
    royalty_amount = minimum if minimum_applied else calculated_royalty
    return royalty_base, percentage, royalty_amount, minimum_applied

def recalculate_monthly_figure(monthly_figure):
    franchise = monthly_figure.franchise or Franchise.query.get(monthly_figure.franchise_id) or get_or_create_franchise()

    # Claim Receipts removed from the Monthly Figures workflow.
    monthly_figure.claim_receipts = Decimal("0")

    # SALES for royalty = Funeral Receipts + Society Receipts + Cash Sales + Tombstone Receipts + OBO Services Receipts
    monthly_figure.sales = calculate_sales_for_royalty(monthly_figure)

    # ADMIN FEE = Insurance Receipts - Insurance Payover
    monthly_figure.admin_fee = Decimal(monthly_figure.insurance_receipts or 0) - Decimal(monthly_figure.insurance_payover or 0)
    if monthly_figure.admin_fee < 0:
        monthly_figure.admin_fee = Decimal("0")

    # CASH stays fixed across the system: CASH = SALES + INSURANCE RECEIPTS.
    # GROSS/ROYALTY BASE is automatic from the newest agreement start date:
    # 2018 or newer = New Gross Method = SALES + ADMIN FEE.
    # Before 2018/missing = Old Gross Method = SALES + INSURANCE RECEIPTS.
    sales = Decimal(monthly_figure.sales or 0)
    monthly_figure.cash = sales + Decimal(monthly_figure.insurance_receipts or 0)
    royalty_base, gross_method = calculate_royalty_base(monthly_figure, franchise)
    monthly_figure.gross_turnover = royalty_base
    monthly_figure.gross_method = gross_method
    franchise.royalty_gross_method = gross_method

    # Backward compatibility fields.
    monthly_figure.cash_received = monthly_figure.cash
    monthly_figure.insurance_received = monthly_figure.insurance_receipts
    monthly_figure.payover = monthly_figure.insurance_payover
    monthly_figure.other_income = monthly_figure.admin_fee

    gross, percentage, royalty_amount, minimum_applied = calculate_royalty(franchise, royalty_base)
    monthly_figure.gross_revenue = gross
    monthly_figure.royalty_percentage = percentage
    monthly_figure.royalty_amount = royalty_amount
    monthly_figure.minimum_royalty_applied = minimum_applied


def recalculate_figures_for_display(figures, commit=True):
    """Recalculate visible monthly/royalty rows from the current Franchise Details settings.

    This makes old imported rows update immediately when the franchise agreement
    date or royalty scale brackets change. It also fixes rows that were imported
    before the scale was available.
    """
    changed = False
    for monthly_figure in figures:
        before = (
            Decimal(monthly_figure.sales or 0),
            Decimal(monthly_figure.admin_fee or 0),
            Decimal(monthly_figure.cash or 0),
            Decimal(monthly_figure.gross_turnover or 0),
            Decimal(monthly_figure.gross_revenue or 0),
            Decimal(monthly_figure.royalty_percentage or 0),
            Decimal(monthly_figure.royalty_amount or 0),
            bool(monthly_figure.minimum_royalty_applied),
        )
        recalculate_monthly_figure(monthly_figure)
        after = (
            Decimal(monthly_figure.sales or 0),
            Decimal(monthly_figure.admin_fee or 0),
            Decimal(monthly_figure.cash or 0),
            Decimal(monthly_figure.gross_turnover or 0),
            Decimal(monthly_figure.gross_revenue or 0),
            Decimal(monthly_figure.royalty_percentage or 0),
            Decimal(monthly_figure.royalty_amount or 0),
            bool(monthly_figure.minimum_royalty_applied),
        )
        if before != after:
            changed = True
    if changed and commit:
        db.session.commit()
    return figures


def extract_pdf_text(file_storage):
    suffix = Path(file_storage.filename or "").suffix.lower()
    if suffix != ".pdf":
        raise ValueError("Only PDF files can be imported.")

    tmp_dir = Path(current_app.instance_path) / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / secure_filename(file_storage.filename or "monthly-import.pdf")
    file_storage.save(tmp_path)

    try:
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader
            except ImportError as exc:
                raise RuntimeError("PDF import needs the pypdf package. Run: pip install pypdf") from exc

        reader = PdfReader(str(tmp_path))
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts), tmp_path
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def parse_pdf_month_year(text):
    now = datetime.now()
    year_match = re.search(r"\b(20\d{2})\b", text)
    year = int(year_match.group(1)) if year_match else now.year

    month = now.month
    month_names = {name.lower(): value for value, name in MONTHS}
    lower = text.lower()
    for name, value in month_names.items():
        if name in lower:
            month = value
            break

    return month, year


def normalise_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def amount_after_label(text, label, default="0"):
    pattern = re.escape(label) + r"\s*:?\s*(-?\s*R?\s*\d[\d\s,]*(?:\.\d{1,2})?)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return Decimal(default)
    return parse_decimal(match.group(1))


def int_after_label(text, label, default=0):
    pattern = re.escape(label) + r"\s*:?\s*(\d+)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return default
    return parse_int(match.group(1))


def parse_pdf_values(text):
    """Parser for Martins Month-End Report PDFs using the agreed Monthly Figures mapping.

    System - GROSS TURNOVER: calculated by selected franchise gross method.
    System - CASH: calculated by system.
    System - Funeral Receipts: PDF Funeral Receipts - Claim Refund.
    System - Claim Receipt: removed and forced to zero.
    System - Society Receipts: PDF Society Receipts.
    System - Cash Sales: PDF Cash Sale Receipts.
    System - Tombstone Receipts: PDF Tombstone Receipts.
    System - OBO Services Receipts: PDF MF OBO Receipts.
    System - SALES: Funeral Receipts + OBO Services Receipts + Cash Sales + Tombstone Receipts.
    System - INSURANCE RECEIPTS: PDF Insurance Receipts.
    System - INSURANCE PAYOVER: manual insert after import.
    System - ADMIN FEE: Insurance Receipts - Insurance Payover.
    System - INSURANCE JOININGS: PDF Total Number under NEW JOININGS.
    System - MF FILES: PDF Total MF Files.
    """
    values = {field: Decimal("0") for field, _ in IMPORT_FIELDS}
    values["insurance_joinings"] = 0
    values["mf_files"] = 0

    clean = normalise_text(text)

    values["funeral_receipts"] = amount_after_label(clean, "Funeral Receipts - Claim Refund (R 0.00)")
    if values["funeral_receipts"] == 0:
        match = re.search(
            r"Funeral Receipts\s*-\s*Claim Refund\s*\([^)]*\)\s*(-?\s*R?\s*\d[\d\s,]*(?:\.\d{1,2})?)",
            clean,
            flags=re.IGNORECASE,
        )
        if match:
            values["funeral_receipts"] = parse_decimal(match.group(1))

    values["society_receipts"] = amount_after_label(clean, "Society Receipts")
    values["cash_sales"] = amount_after_label(clean, "Cash Sale Receipts")
    if values["cash_sales"] == 0:
        values["cash_sales"] = amount_after_label(clean, "Cash Sales Receipts")
    values["tombstone_receipts"] = amount_after_label(clean, "Tombstone Receipts")

    # Use the main Insurance Receipts line, excluding the captured-in-period line.
    match = re.search(r"\bInsurance Receipts\s+(-?\s*R?\s*\d[\d\s,]*(?:\.\d{1,2})?)", clean, flags=re.IGNORECASE)
    if match:
        values["insurance_receipts"] = parse_decimal(match.group(1))

    # PDF source for OBO Services Receipts = MF OBO Receipts.
    values["obo_service_receipts"] = amount_after_label(clean, "MF OBO Receipts")

    # Removed field.
    values["claim_receipts"] = Decimal("0")

    # Manual field starts as zero.
    values["insurance_payover"] = Decimal("0")

    values["insurance_joinings"] = int_after_label(clean, "Total Number")
    values["mf_files"] = int_after_label(clean, "(1) Total MF Files")

    # Calculated values.
    values["sales"] = (
        values["funeral_receipts"]
        + values["society_receipts"]
        + values["cash_sales"]
        + values["tombstone_receipts"]
        + values["obo_service_receipts"]
    )
    values["cash"] = (
        values["funeral_receipts"]
        + values["society_receipts"]
        + values["cash_sales"]
        + values["tombstone_receipts"]
        + values["obo_service_receipts"]
        + values["insurance_receipts"]
    )
    values["admin_fee"] = values["insurance_receipts"] - values["insurance_payover"]
    values["gross_turnover"] = values["cash"]

    return values



EXCEL_MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "mei": 5,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "okt": 10,
    "oct": 10,
    "nov": 11,
    "des": 12,
    "dec": 12,
}

EXCEL_VALUE_ROWS = {
    "funeral_receipts": 6,
    "claim_receipts": 7,
    "society_receipts": 8,
    "cash_sales": 9,
    "tombstone_receipts": 10,
    "obo_service_receipts": 11,
    "insurance_receipts": 13,
    "insurance_payover": 14,
    "insurance_joinings": 16,
    "mf_files": 17,
}

# The group Excel workbook layout is column-based:
# - Franchise names are expected in C1:FJ1. Some legacy workbooks store the names
#   in row 2 with row 1 containing franchise numbers, so row 2 is used as a safe fallback.
# - Row B6:B17 contains the headings.
# - Each franchise's monthly values are in the same rows under its franchise column.
# Rows such as SALES and ADMIN FEE are calculated by the system and are not imported.
EXCEL_HEADER_ROWS = (1, 2)
EXCEL_FIRST_FRANCHISE_COLUMN = 3  # C
EXCEL_LAST_FRANCHISE_COLUMN = 166  # FJ
EXCEL_HEADING_COLUMN = 2  # B
EXCEL_DATA_ROWS = set(range(6, 18))
EXCEL_CALCULATED_LABELS = {"sales", "admin fee", "gross turnover", "cash"}
EXCEL_SKIP_NAME_WORDS = {"total", "totals", "data"}
EXCEL_LABEL_TO_FIELD = {
    "funeral receipts": "funeral_receipts",
    "claim receipts": "claim_receipts",
    "societ receipts": "society_receipts",
    "society receipts": "society_receipts",
    "cash sales": "cash_sales",
    "tombstone receipts": "tombstone_receipts",
    "obo services receipts": "obo_service_receipts",
    "obo service receipts": "obo_service_receipts",
    "mf obo receipts": "obo_service_receipts",
    "insurance receipts": "insurance_receipts",
    "insurance payover": "insurance_payover",
    "insurance joinings": "insurance_joinings",
    "mf files": "mf_files",
}


def normalize_excel_label(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def is_number_like(value):
    text = str(value or "").strip()
    if not text:
        return False
    try:
        Decimal(text.replace(",", ""))
        return True
    except (InvalidOperation, ValueError):
        return False


def is_skipped_excel_franchise_name(value):
    cleaned = clean_excel_franchise_name(value)
    if not cleaned:
        return True
    key = normalize_excel_label(cleaned)
    return key in EXCEL_SKIP_NAME_WORDS or any(word in EXCEL_SKIP_NAME_WORDS for word in key.split())


def excel_franchise_name_for_column(rows, column):
    # User requested C1:FJ1 as the franchise-name range. Use row 1 first,
    # but fallback to row 2 for legacy sheets where row 1 is just outlet numbers.
    candidates = [rows.get(1, {}).get(column), rows.get(2, {}).get(column)]
    for candidate in candidates:
        text = clean_excel_franchise_name(candidate)
        if not text:
            continue
        lowered = normalize_excel_label(text)
        if lowered in {"nr", "no", "number", "outlet"}:
            continue
        if is_number_like(text):
            continue
        if is_skipped_excel_franchise_name(text):
            continue
        return text
    return ""


def excel_values_for_franchise_column(rows, column):
    values = {field: Decimal("0") for field in EXCEL_VALUE_ROWS}
    for row_number in range(6, 18):
        label = normalize_excel_label(rows.get(row_number, {}).get(EXCEL_HEADING_COLUMN))
        if not label or label in EXCEL_CALCULATED_LABELS:
            continue
        field = EXCEL_LABEL_TO_FIELD.get(label)
        if field:
            values[field] = rows.get(row_number, {}).get(column)
    return values


def normalize_franchise_key(value):
    text = str(value or "").strip()
    text = re.sub(r"\(\s*f\s*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(text.split())


def clean_excel_franchise_name(value):
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    if normalize_excel_label(text) in EXCEL_SKIP_NAME_WORDS:
        return ""
    text = re.sub(r"\(\s*f\s*\)", "", text, flags=re.IGNORECASE).strip()
    return text


def parse_excel_sheet_period(sheet_name):
    match = re.match(r"\s*([A-Za-zÀ-ÿ]+)\s*'?\s*(\d{2,4})\s*$", str(sheet_name or ""))
    if not match:
        return None, None
    month_key = match.group(1).strip().lower()[:3]
    month = EXCEL_MONTH_NAMES.get(month_key)
    if not month:
        return None, None
    year_value = int(match.group(2))
    year = 2000 + year_value if year_value < 100 else year_value
    return month, year


def excel_decimal(value):
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        if isinstance(value, str):
            value = value.replace("R", "").replace(",", "").replace(" ", "").strip()
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def find_or_create_franchise_from_excel(raw_name):
    cleaned_name = clean_excel_franchise_name(raw_name)
    key = normalize_franchise_key(cleaned_name)
    if not key:
        return None, False

    franchises = Franchise.query.all()
    for franchise in franchises:
        if normalize_franchise_key(franchise.business_name) == key:
            return franchise, False

    franchise = Franchise(
        business_name=cleaned_name,
        franchise_code=re.sub(r"[^A-Z0-9]+", "", cleaned_name.upper())[:20],
    )
    db.session.add(franchise)
    db.session.flush()
    return franchise, True


def excel_slugify_email_part(value):
    value = str(value or "").lower().replace("&", "and")
    value = re.sub(r"\(f\)", "", value)
    value = re.sub(r"[^a-z0-9]+", ".", value)
    value = re.sub(r"\.+", ".", value).strip(".")
    return value or "franchise"


def excel_temporary_password(length=14):
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits + "!@#"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def find_or_create_role(role_name):
    role = Role.query.filter_by(name=role_name).first()
    if role:
        return role
    role = Role(name=role_name, description=f"Imported {role_name} role", is_system_role=True)
    db.session.add(role)
    db.session.flush()
    return role


def find_or_create_franchise_user_for_franchise(franchise):
    email = f"{excel_slugify_email_part(franchise.business_name)}@martinsdirect.com"
    user = User.query.filter(db.func.lower(User.email) == email.lower()).first()
    created = False
    if not user:
        user = User(
            name=franchise.business_name,
            surname="User",
            email=email,
            is_active=True,
            is_active_account=True,
        )
        user.set_password(excel_temporary_password())
        db.session.add(user)
        db.session.flush()
        created = True

    role = find_or_create_role("Franchise User")
    if role not in user.roles:
        user.roles.append(role)

    if franchise not in user.assigned_franchises:
        user.assigned_franchises.append(franchise)

    return user, created


def row_has_excel_data(values):
    return any(excel_decimal(value) != 0 for value in values.values())



XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XLSX_NS = {"a": XLSX_MAIN_NS, "r": XLSX_REL_NS}
XLSX_IMPORT_ROWS = set(EXCEL_HEADER_ROWS) | EXCEL_DATA_ROWS


def excel_column_index(cell_ref):
    match = re.match(r"([A-Z]+)", str(cell_ref or ""))
    if not match:
        return 0
    index = 0
    for char in match.group(1):
        index = index * 26 + ord(char) - 64
    return index


def read_shared_strings(zip_file):
    if "xl/sharedStrings.xml" not in zip_file.namelist():
        return []
    root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall("a:si", XLSX_NS):
        strings.append("".join(text.text or "" for text in item.iter(f"{{{XLSX_MAIN_NS}}}t")))
    return strings


def xlsx_cell_value(cell, shared_strings):
    value_node = cell.find("a:v", XLSX_NS)
    if value_node is None:
        inline_node = cell.find("a:is/a:t", XLSX_NS)
        return inline_node.text if inline_node is not None else ""
    value = value_node.text or ""
    if cell.attrib.get("t") == "s":
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError):
            return ""
    return value


def iter_xlsx_import_sheets(file_storage):
    file_storage.stream.seek(0)
    workbook_bytes = BytesIO(file_storage.read())
    with zipfile.ZipFile(workbook_bytes) as zip_file:
        shared_strings = read_shared_strings(zip_file)
        workbook_root = ET.fromstring(zip_file.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_root}

        for sheet in workbook_root.find("a:sheets", XLSX_NS):
            title = sheet.attrib.get("name", "")
            relationship_id = sheet.attrib.get(f"{{{XLSX_REL_NS}}}id")
            target = rel_map.get(relationship_id)
            if not target:
                continue
            worksheet_path = "xl/" + target.lstrip("/")
            worksheet_root = ET.fromstring(zip_file.read(worksheet_path))
            rows = {}
            for row in worksheet_root.findall("a:sheetData/a:row", XLSX_NS):
                row_number = int(row.attrib.get("r", "0") or 0)
                if row_number not in XLSX_IMPORT_ROWS:
                    continue
                row_values = {}
                for cell in row.findall("a:c", XLSX_NS):
                    column_index = excel_column_index(cell.attrib.get("r"))
                    if column_index:
                        row_values[column_index] = xlsx_cell_value(cell, shared_strings)
                rows[row_number] = row_values
            yield title, rows


def import_monthly_figures_excel_file(file_storage, allocate_users=True):
    suffix = Path(file_storage.filename or "").suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        raise ValueError("Please upload an Excel workbook (.xlsx or .xlsm).")

    imported = 0
    updated = 0
    skipped = 0
    franchises_created = 0
    users_created = 0
    users_linked = 0
    periods = set()
    period_tuples = set()
    franchise_ids_touched = set()
    franchise_names = set()

    for sheet_title, rows in iter_xlsx_import_sheets(file_storage):
        month, year = parse_excel_sheet_period(sheet_title)
        if not month or not year:
            skipped += 1
            continue

        period_has_data = False
        # Imported columns are fixed to C:FJ. This avoids accidentally reading any
        # total/data columns outside the agreed franchise range.
        for column in range(EXCEL_FIRST_FRANCHISE_COLUMN, EXCEL_LAST_FRANCHISE_COLUMN + 1):
            franchise_name = excel_franchise_name_for_column(rows, column)
            if not franchise_name:
                continue

            values = excel_values_for_franchise_column(rows, column)
            if not row_has_excel_data(values):
                skipped += 1
                continue

            franchise, created_franchise = find_or_create_franchise_from_excel(franchise_name)
            if not franchise:
                skipped += 1
                continue
            if created_franchise:
                franchises_created += 1
            franchise_names.add(franchise.business_name)
            franchise_ids_touched.add(franchise.id)
            period_has_data = True

            if allocate_users:
                was_linked = bool(franchise.assigned_users)
                user, created_user = find_or_create_franchise_user_for_franchise(franchise)
                if created_user:
                    users_created += 1
                if not was_linked and franchise in user.assigned_franchises:
                    users_linked += 1

            monthly_figure = MonthlyFigure.query.filter_by(franchise_id=franchise.id, month=month, year=year).first()
            if monthly_figure:
                updated += 1
            else:
                monthly_figure = MonthlyFigure(
                    franchise_id=franchise.id,
                    month=month,
                    year=year,
                    created_by_id=current_user.id,
                    status="Imported",
                )
                db.session.add(monthly_figure)
                imported += 1

            monthly_figure.funeral_receipts = excel_decimal(values.get("funeral_receipts"))
            monthly_figure.claim_receipts = excel_decimal(values.get("claim_receipts"))
            monthly_figure.society_receipts = excel_decimal(values.get("society_receipts"))
            monthly_figure.cash_sales = excel_decimal(values.get("cash_sales"))
            monthly_figure.tombstone_receipts = excel_decimal(values.get("tombstone_receipts"))
            monthly_figure.obo_service_receipts = excel_decimal(values.get("obo_service_receipts"))
            monthly_figure.insurance_receipts = excel_decimal(values.get("insurance_receipts"))
            monthly_figure.insurance_payover = excel_decimal(values.get("insurance_payover"))
            monthly_figure.insurance_joinings = parse_int(values.get("insurance_joinings"))
            monthly_figure.mf_files = parse_int(values.get("mf_files"))
            monthly_figure.notes = (
                f"Imported from Excel workbook: {file_storage.filename}; "
                f"Sheet: {sheet_title}; Franchise: {franchise_name}; Column: {column}"
            )
            if monthly_figure.status == "Draft":
                monthly_figure.status = "Imported"
            recalculate_monthly_figure(monthly_figure)

        if period_has_data:
            periods.add(f"{year}-{month:02d}")
            period_tuples.add((month, year))

    db.session.commit()

    # Performance speed phase: after an Excel import, calculate dashboard and
    # decision-centre rows once so normal page loads only read saved results.
    performance_rows = 0
    try:
        from app.performance.service import rebuild_performance_results
        for perf_month, perf_year in sorted(period_tuples, key=lambda item: (item[1], item[0])):
            performance_rows += rebuild_performance_results(
                perf_month, perf_year, list(franchise_ids_touched), "annual_gross_scale"
            )
    except Exception as exc:
        current_app.logger.exception("Performance pre-calculation failed after monthly Excel import: %s", exc)

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "franchises_created": franchises_created,
        "users_created": users_created,
        "users_linked": users_linked,
        "period_count": len(periods),
        "franchise_count": len(franchise_names),
        "first_period": sorted(periods)[0] if periods else "",
        "last_period": sorted(periods)[-1] if periods else "",
        "performance_rows": performance_rows,
    }


def create_monthly_figure_from_pdf(file_storage, franchise_id=None):
    franchise = None
    if franchise_id:
        candidate = Franchise.query.get(franchise_id)
        if candidate and current_user.can_access_franchise(candidate.id):
            franchise = candidate
            session["selected_franchise_id"] = candidate.id
    if not franchise:
        franchise = get_selected_franchise() or get_or_create_franchise()
    text, tmp_path = extract_pdf_text(file_storage)
    imported = parse_pdf_values(text)
    month, year = parse_pdf_month_year(text)

    monthly_figure = MonthlyFigure(
        franchise_id=franchise.id,
        month=month,
        year=year,
        created_by_id=current_user.id,
        # PDF import needs a manual Insurance Payover before the figures are final.
        status="Pending Payover",
    )

    monthly_figure.funeral_receipts = imported.get("funeral_receipts", Decimal("0"))
    monthly_figure.claim_receipts = Decimal("0")
    monthly_figure.society_receipts = imported.get("society_receipts", Decimal("0"))
    monthly_figure.cash_sales = imported.get("cash_sales", Decimal("0"))
    monthly_figure.tombstone_receipts = imported.get("tombstone_receipts", Decimal("0"))
    monthly_figure.obo_service_receipts = imported.get("obo_service_receipts", Decimal("0"))
    monthly_figure.insurance_receipts = imported.get("insurance_receipts", Decimal("0"))

    # Insurance Payover is manual, so it always starts at zero after import.
    monthly_figure.insurance_payover = Decimal("0")

    monthly_figure.insurance_joinings = imported.get("insurance_joinings", 0)
    monthly_figure.mf_files = imported.get("mf_files", 0)
    monthly_figure.notes = f"Imported from PDF: {file_storage.filename}"

    # Calculate preview values with payover as zero, but keep the record pending
    # until the finance user enters the actual Insurance Payover.
    recalculate_monthly_figure(monthly_figure)

    db.session.add(monthly_figure)
    db.session.commit()

    upload_dir = Path(current_app.instance_path) / "monthly_imports"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = secure_filename(file_storage.filename or "monthly-import.pdf")
    stored_pdf = upload_dir / f"{monthly_figure.id}_{safe_name}"
    shutil.move(str(tmp_path), stored_pdf)

    log_action("Monthly Figures", "Imported PDF monthly figures", f"Period: {monthly_figure.period_label}; File: {safe_name}")
    db.session.commit()
    return monthly_figure


def remove_imported_pdfs(monthly_figure_id):
    upload_dir = Path(current_app.instance_path) / "monthly_imports"
    if not upload_dir.exists():
        return
    for file_path in upload_dir.glob(f"{monthly_figure_id}_*.pdf"):
        try:
            file_path.unlink()
        except OSError:
            pass


@monthly_bp.route("/")
@login_required
@permission_required("monthly_figures:view")
def index():
    accessible_franchises = get_accessible_franchises()
    selected = get_selected_franchise()
    selected_month, selected_year = selected_reporting_period()

    linked_franchises = get_ordered_linked_franchises_for_user(current_user)
    group_user = None
    grouped_view = is_franchise_side_user() and len(linked_franchises) > 1

    # Admin/Finance viewing a selected main branch should also see the linked
    # branches split into separate cards, exactly as the franchise user sees it.
    if not grouped_view and selected and is_franchise_view_mode():
        group_user = get_group_user_for_selected_franchise(selected)
        if group_user:
            linked_franchises = get_ordered_linked_franchises_for_user(group_user)
            grouped_view = len(linked_franchises) > 1

    show_all_franchises = is_privileged_user() and not is_franchise_view_mode() and not grouped_view

    query = MonthlyFigure.query.filter(
        MonthlyFigure.month == selected_month,
        MonthlyFigure.year == selected_year,
    )
    if grouped_view:
        linked_ids = [franchise.id for franchise in linked_franchises]
        query = query.filter(MonthlyFigure.franchise_id.in_(linked_ids)) if linked_ids else query.filter(False)
        selected = get_primary_franchise_for_user(group_user or current_user, linked_franchises)
    elif show_all_franchises:
        accessible_ids = [franchise.id for franchise in accessible_franchises]
        if accessible_ids:
            query = query.filter(MonthlyFigure.franchise_id.in_(accessible_ids))
        else:
            query = query.filter(False)
    elif selected:
        query = query.filter_by(franchise_id=selected.id)

    figures = query.join(Franchise, MonthlyFigure.franchise_id == Franchise.id).order_by(
        Franchise.business_name.asc(),
        MonthlyFigure.id.desc(),
    ).all()
    recalculate_figures_for_display(figures)
    figures_by_branch = build_figures_by_branch(figures, linked_franchises if grouped_view else None)
    grouped_total = build_grouped_monthly_totals(figures, selected, selected_month, selected_year) if grouped_view else None
    return render_template(
        "monthly/index.html",
        figures=figures,
        figures_by_branch=figures_by_branch,
        grouped_total=grouped_total,
        grouped_view=grouped_view,
        linked_group_names=[franchise.business_name for franchise in linked_franchises] if grouped_view else [],
        selected=selected,
        accessible_franchises=accessible_franchises,
        show_all_franchises=show_all_franchises,
        selected_month=selected_month,
        selected_year=selected_year,
        selected_period_label=month_label(selected_month, selected_year),
        month_options=MONTHS,
        year_options=reporting_years(),
    )



@monthly_bp.route("/import-excel", methods=["GET", "POST"])
@login_required
def import_excel():
    if not is_current_user_admin():
        abort(403)
    if request.method == "POST":
        file_storage = request.files.get("excel_file")
        allocate_users = request.form.get("allocate_users") == "yes"
        if not file_storage or not file_storage.filename:
            flash("Please select the Excel workbook to import.", "warning")
            return redirect(url_for("monthly.import_excel"))
        try:
            result = import_monthly_figures_excel_file(file_storage, allocate_users=allocate_users)
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("monthly.import_excel"))

        log_action(
            "Monthly Figures",
            "Imported Excel monthly figures",
            f"New: {result['imported']}, Updated: {result['updated']}, Franchises: {result['franchise_count']}, Periods: {result['period_count']}",
        )
        db.session.commit()
        flash(
            f"Excel import complete. {result['imported']} new records created, {result['updated']} records updated, "
            f"{result['franchise_count']} franchises allocated across {result['period_count']} period(s). "
            f"Performance cache rows prepared: {result.get('performance_rows', 0)}.",
            "success",
        )
        return render_template("monthly/import_excel.html", result=result)

    return render_template("monthly/import_excel.html", result=None)

@monthly_bp.route("/import", methods=["GET", "POST"])
@login_required
def import_pdf():
    if not can_access_pdf_import():
        abort(403)

    if request.method == "POST":
        file_storage = request.files.get("pdf_file")
        if not file_storage or not file_storage.filename:
            flash("Please select a PDF file to import.", "warning")
            return redirect(url_for("monthly.import_pdf"))

        try:
            monthly_figure = create_monthly_figure_from_pdf(file_storage, request.form.get('franchise_id', type=int))
        except Exception as exc:
            flash(str(exc), "danger")
            return redirect(url_for("monthly.import_pdf"))

        flash("PDF imported. Enter the Insurance Payover now, or choose Save for Later if you do not have the payover yet.", "success")
        return redirect(url_for("monthly.edit", figure_id=monthly_figure.id))

    return render_template("monthly/import.html", franchises=get_accessible_franchises(), selected_franchise=get_selected_franchise())


@monthly_bp.route("/new")
@login_required
@permission_required("monthly_figures:import")
def new():
    flash("Monthly Figures cannot be added manually. Please import the PDF file.", "warning")
    return redirect(url_for("monthly.import_pdf"))


@monthly_bp.route("/<int:figure_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("monthly_figures:edit")
def edit(figure_id):
    monthly_figure = MonthlyFigure.query.get_or_404(figure_id)
    if monthly_figure.status == "Locked" and not current_user.has_permission("monthly_figures:approve"):
        flash("Locked monthly figures can only be edited by users with Monthly Figures Approve permission.", "warning")
        return redirect(url_for("monthly.index"))

    if request.method == "POST":
        action = request.form.get("action", "save_calculate")
        monthly_figure.notes = request.form.get("notes", "").strip()

        if action == "save_later":
            monthly_figure.status = "Pending Payover"
            log_action("Monthly Figures", "Saved monthly figures for later payover capture", f"Period: {monthly_figure.period_label}")
            db.session.commit()
            flash("Monthly figures saved for later. Return to this record when you have the Insurance Payover.", "warning")
            return redirect(url_for("monthly.index"))

        monthly_figure.insurance_payover = parse_decimal(request.form.get("insurance_payover"))
        recalculate_monthly_figure(monthly_figure)
        monthly_figure.status = "Calculated"
        log_action("Monthly Figures", "Saved payover and recalculated monthly figures", f"Period: {monthly_figure.period_label}")
        db.session.commit()
        flash("Insurance Payover saved and royalty calculation updated.", "success")
        return redirect(url_for("monthly.index"))

    return render_template("monthly/form.html", monthly_figure=monthly_figure, months=MONTHS, mode="edit")


@monthly_bp.route("/<int:figure_id>/submit", methods=["POST"])
@login_required
@permission_required("monthly_figures:edit")
def submit(figure_id):
    monthly_figure = MonthlyFigure.query.get_or_404(figure_id)
    monthly_figure.status = "Submitted"
    monthly_figure.submitted_at = datetime.now(timezone.utc)
    log_action("Monthly Figures", "Submitted monthly figures", f"Period: {monthly_figure.period_label}")
    db.session.commit()
    flash("Monthly figures submitted.", "success")
    return redirect(url_for("monthly.index"))


@monthly_bp.route("/<int:figure_id>/approve", methods=["POST"])
@login_required
@permission_required("monthly_figures:approve")
def approve(figure_id):
    monthly_figure = MonthlyFigure.query.get_or_404(figure_id)
    monthly_figure.status = "Approved"
    monthly_figure.approved_at = datetime.now(timezone.utc)
    log_action("Monthly Figures", "Approved monthly figures", f"Period: {monthly_figure.period_label}")
    db.session.commit()
    flash("Monthly figures approved.", "success")
    return redirect(url_for("monthly.index"))


@monthly_bp.route("/<int:figure_id>/lock", methods=["POST"])
@login_required
@permission_required("monthly_figures:approve")
def lock(figure_id):
    monthly_figure = MonthlyFigure.query.get_or_404(figure_id)
    monthly_figure.status = "Locked"
    monthly_figure.locked_at = datetime.now(timezone.utc)
    log_action("Monthly Figures", "Locked monthly figures", f"Period: {monthly_figure.period_label}")
    db.session.commit()
    flash("Monthly figures locked.", "success")
    return redirect(url_for("monthly.index"))


@monthly_bp.route("/<int:figure_id>/delete", methods=["POST"])
@login_required
@permission_required("monthly_figures:delete")
def delete(figure_id):

    monthly_figure = MonthlyFigure.query.get_or_404(figure_id)
    period = monthly_figure.period_label
    remove_imported_pdfs(monthly_figure.id)
    db.session.delete(monthly_figure)
    log_action("Monthly Figures", "Deleted imported monthly figures and PDF", f"Period: {period}")
    db.session.commit()

    flash(f"Monthly figures for {period} deleted. Linked audit history and franchise data were kept.", "success")
    return redirect(url_for("monthly.index"))


@monthly_bp.route("/export-pdf")
@login_required
@permission_required("monthly_figures:export")
def export_period_pdf():
    selected_month, selected_year = selected_reporting_period()
    accessible_franchises = get_accessible_franchises()
    selected = get_selected_franchise()
    show_all_franchises = is_privileged_user() and not is_franchise_view_mode()

    query = MonthlyFigure.query.filter(
        MonthlyFigure.month == selected_month,
        MonthlyFigure.year == selected_year,
    )
    if show_all_franchises:
        accessible_ids = [franchise.id for franchise in accessible_franchises]
        if accessible_ids:
            query = query.filter(MonthlyFigure.franchise_id.in_(accessible_ids))
        else:
            query = query.filter(False)
    elif selected:
        query = query.filter_by(franchise_id=selected.id)

    figures = query.join(Franchise, MonthlyFigure.franchise_id == Franchise.id).order_by(
        Franchise.business_name.asc(),
        MonthlyFigure.id.desc(),
    ).all()
    recalculate_figures_for_display(figures)
    from app.reports.pdf import build_monthly_figures_period_pdf
    period_label = month_label(selected_month, selected_year)
    pdf_path = build_monthly_figures_period_pdf(figures, selected, current_user, period_label)
    log_action("Monthly Figures", "Exported monthly figures period PDF", period_label)
    db.session.commit()
    safe_label = period_label.lower().replace(" ", "-")
    return send_file(pdf_path, as_attachment=True, download_name=f"monthly-figures-{safe_label}.pdf")


@monthly_bp.route("/<int:figure_id>/export-pdf")
@login_required
@permission_required("monthly_figures:export")
def export_pdf(figure_id):
    monthly_figure = MonthlyFigure.query.get_or_404(figure_id)
    from app.reports.pdf import build_monthly_figure_pdf
    pdf_path = build_monthly_figure_pdf(monthly_figure, current_user)
    log_action("Monthly Figures", "Exported PDF", f"Period: {monthly_figure.period_label}")
    db.session.commit()
    return send_file(pdf_path, as_attachment=True, download_name=f"monthly-figures-{monthly_figure.period_label}.pdf")
