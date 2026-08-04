"""Royalty Engine 2.0.

Central business logic for monthly royalty calculations.  This module is kept
outside the Flask route files so every entry point (Excel import, PDF import,
royalty page, diagnostics and manual recalculation) uses the same rules.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from types import SimpleNamespace
import re

from app.models import Franchise, RoyaltyScale

METHOD_CUTOFF_YEAR = 2018
OPEN_ENDED_AMOUNT_TO = Decimal("999999999999")


@dataclass
class RoyaltyResult:
    franchise_id: int | None
    franchise_name: str
    agreement_start_date: str
    agreement_end_date: str
    method: str
    method_label: str
    method_source: str
    royalty_base: Decimal
    royalty_percentage: Decimal
    royalty_amount: Decimal
    minimum_royalty_amount: Decimal
    minimum_royalty_applied: bool
    scale_source_franchise_id: int | None
    scale_source_franchise_name: str
    warnings: list[str]
    blocking_errors: list[str]

    @property
    def is_clean(self) -> bool:
        return not self.blocking_errors

    def to_dict(self) -> dict:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Decimal):
                data[key] = str(value)
        return data


def decimal_value(value, default="0") -> Decimal:
    """Return a safe Decimal for optional numeric inputs.

    Production imports sometimes contain blank cells/None values.  The earlier
    implementation attempted Decimal(None) when both value and default were
    None, which stopped the entire royalty rebuild.  Missing or invalid values
    now safely fall back to 0 unless a different default is supplied.
    """
    fallback = "0" if default is None else default
    if value is None:
        value = fallback
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        try:
            return Decimal(str(fallback))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal("0")


def normalize_gross_method(value) -> str:
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


def method_label(method: str) -> str:
    return "Gross = New Gross Method" if method == "new" else "Gross = Old"


def select_royalty_method(franchise: Franchise | None, *, period_month: int | None = None, period_year: int | None = None):
    """Return (method, source, warnings, blocking_errors).

    Business rule:
    * Agreement start year >= 2018 uses new gross method.
    * Agreement start year before 2018 uses old gross method.
    * Missing agreement date falls back to explicit stored method but is marked
      Needs Review because the contract source-of-truth is incomplete.
    * Expired agreements for the imported period are warned so Finance can check
      whether the branch should still be active.
    """
    warnings: list[str] = []
    blocking_errors: list[str] = []
    if not franchise:
        return "old", "missing_franchise", warnings, ["missing franchise"]

    start_date = getattr(franchise, "agreement_start_date", None)
    end_date = getattr(franchise, "agreement_end_date", None)

    if start_date:
        method = "new" if getattr(start_date, "year", 0) >= METHOD_CUTOFF_YEAR else "old"
        source = "agreement_start_date"
    else:
        stored = normalize_gross_method(getattr(franchise, "royalty_gross_method", ""))
        method = stored if stored in {"new", "old"} else "old"
        source = "stored_method_fallback" if stored else "default_old_missing_agreement"
        blocking_errors.append("missing agreement start date")

    if period_month and period_year:
        try:
            period_date = date(int(period_year), int(period_month), 1)
            if start_date and period_date < date(start_date.year, start_date.month, 1):
                warnings.append("imported period is before agreement start date")
            if end_date and period_date > date(end_date.year, end_date.month, 1):
                warnings.append("imported period is after agreement end date")
        except Exception:
            warnings.append("could not validate imported period against agreement dates")

    return method, source, warnings, blocking_errors


def calculate_sales(monthly_figure) -> Decimal:
    """SALES used by royalty calculations.

    Joining's and Funerals remain count/text values elsewhere and are not part of
    currency formatting or royalty base calculation.
    """
    return (
        decimal_value(getattr(monthly_figure, "funeral_receipts", 0))
        + decimal_value(getattr(monthly_figure, "society_receipts", 0))
        + decimal_value(getattr(monthly_figure, "cash_sales", 0))
        + decimal_value(getattr(monthly_figure, "tombstone_receipts", 0))
        + decimal_value(getattr(monthly_figure, "obo_service_receipts", 0))
    )


def calculate_base(monthly_figure, franchise: Franchise | None, *, method: str | None = None) -> Decimal:
    sales = calculate_sales(monthly_figure)
    selected_method = method or select_royalty_method(franchise)[0]
    if selected_method == "new":
        base = sales + decimal_value(getattr(monthly_figure, "admin_fee", 0))
    else:
        base = sales + decimal_value(getattr(monthly_figure, "insurance_receipts", 0))
    return max(base, Decimal("0"))


def normalize_franchise_name(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"\(f\)", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _decimal_from_text(value):
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


def parse_royalty_scale_text(raw_text):
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
            if re.search(r"or more|meer|and above|above", line, re.I):
                amount_from, amount_to = amounts[0], OPEN_ENDED_AMOUNT_TO
            else:
                amount_from, amount_to = Decimal("0"), amounts[0]
        else:
            amount_from, amount_to = Decimal("0"), OPEN_ENDED_AMOUNT_TO
        rows.append(SimpleNamespace(row_number=row_number, amount_from=amount_from, amount_to=amount_to, percentage=percentage))
    return rows


def normalise_scale_rows(scales):
    rows = []
    for index, scale in enumerate(scales or [], start=1):
        amount_from = decimal_value(getattr(scale, "amount_from", 0))
        amount_to = decimal_value(getattr(scale, "amount_to", 0))
        percentage = decimal_value(getattr(scale, "percentage", 0))
        if percentage <= 0:
            continue
        if amount_to <= 0:
            amount_to = OPEN_ENDED_AMOUNT_TO
        if amount_to < amount_from:
            continue
        rows.append(SimpleNamespace(
            row_number=getattr(scale, "row_number", index) or index,
            amount_from=amount_from,
            amount_to=amount_to,
            percentage=percentage,
        ))
    return sorted(rows, key=lambda item: (item.amount_from, item.amount_to, item.row_number))


def get_royalty_scales(franchise: Franchise | None):
    """Return (scale_rows, source_franchise, source_label)."""
    if not franchise:
        return [], None, "missing_franchise"

    own_scales = RoyaltyScale.query.filter_by(franchise_id=franchise.id).order_by(
        RoyaltyScale.row_number, RoyaltyScale.amount_from, RoyaltyScale.id
    ).all()
    own_valid = normalise_scale_rows(own_scales)
    if own_valid:
        return own_valid, franchise, "structured_scale"

    parsed_raw = normalise_scale_rows(parse_royalty_scale_text(getattr(franchise, "imported_royalty_scale_text", "")))
    if parsed_raw:
        return parsed_raw, franchise, "imported_scale_text"

    wanted = normalize_franchise_name(getattr(franchise, "business_name", ""))
    if wanted:
        candidates = []
        for candidate in Franchise.query.all():
            if candidate.id == franchise.id:
                continue
            key = normalize_franchise_name(candidate.business_name)
            if not key:
                continue
            ratio = SequenceMatcher(None, wanted, key).ratio()
            if key == wanted or wanted in key or key in wanted or ratio >= 0.84:
                candidates.append((ratio, candidate))

        for _ratio, candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
            candidate_scales = RoyaltyScale.query.filter_by(franchise_id=candidate.id).order_by(
                RoyaltyScale.row_number, RoyaltyScale.amount_from, RoyaltyScale.id
            ).all()
            candidate_valid = normalise_scale_rows(candidate_scales)
            if candidate_valid:
                return candidate_valid, candidate, "matched_structured_scale"
            candidate_raw = normalise_scale_rows(parse_royalty_scale_text(getattr(candidate, "imported_royalty_scale_text", "")))
            if candidate_raw:
                return candidate_raw, candidate, "matched_imported_scale_text"

    imported_percentage = decimal_value(getattr(franchise, "imported_royalty_percentage", 0))
    if imported_percentage > 0:
        return [SimpleNamespace(row_number=1, amount_from=Decimal("0"), amount_to=OPEN_ENDED_AMOUNT_TO, percentage=imported_percentage)], franchise, "fallback_imported_percentage"

    return [], franchise, "missing_scale"


def calculate_royalty_amount(franchise: Franchise | None, royalty_base: Decimal):
    royalty_base = max(decimal_value(royalty_base), Decimal("0"))
    scales, source_franchise, source_label = get_royalty_scales(franchise)
    percentage = Decimal("0")
    matched_scale = None
    warnings: list[str] = []
    errors: list[str] = []

    if not scales:
        errors.append("missing royalty scale")
    else:
        for scale in scales:
            amount_from = decimal_value(getattr(scale, "amount_from", 0))
            amount_to = decimal_value(getattr(scale, "amount_to", 0))
            if amount_to <= 0:
                amount_to = OPEN_ENDED_AMOUNT_TO
            if royalty_base >= amount_from and royalty_base <= amount_to:
                percentage = decimal_value(getattr(scale, "percentage", 0))
                matched_scale = scale
                break
        if matched_scale is None:
            highest = max(scales, key=lambda s: decimal_value(getattr(s, "amount_to", 0)))
            if royalty_base >= decimal_value(getattr(highest, "amount_from", 0)):
                percentage = decimal_value(getattr(highest, "percentage", 0))
                matched_scale = highest
                warnings.append("base above configured brackets; final bracket used")
        if percentage <= 0:
            errors.append("no royalty bracket matched")

    calculated = (royalty_base * percentage) / Decimal("100")
    minimum = decimal_value(getattr(franchise, "minimum_royalty_amount", 0)) if franchise else Decimal("0")
    minimum_applied = minimum > 0 and calculated < minimum
    royalty_amount = minimum if minimum_applied else calculated
    return percentage, royalty_amount, minimum, minimum_applied, source_franchise, source_label, warnings, errors


def calculate_monthly_figure(monthly_figure) -> RoyaltyResult:
    franchise = getattr(monthly_figure, "franchise", None) or Franchise.query.get(getattr(monthly_figure, "franchise_id", None))
    method, method_source, method_warnings, method_errors = select_royalty_method(
        franchise,
        period_month=getattr(monthly_figure, "month", None),
        period_year=getattr(monthly_figure, "year", None),
    )

    sales = calculate_sales(monthly_figure)
    admin_fee = decimal_value(getattr(monthly_figure, "insurance_receipts", 0)) - decimal_value(getattr(monthly_figure, "insurance_payover", 0))
    if admin_fee < 0:
        admin_fee = Decimal("0")
    cash = sales + decimal_value(getattr(monthly_figure, "insurance_receipts", 0))

    # Keep compatibility fields synchronized.
    monthly_figure.claim_receipts = Decimal("0")
    monthly_figure.sales = sales
    monthly_figure.admin_fee = admin_fee
    monthly_figure.cash = cash
    monthly_figure.cash_received = cash
    monthly_figure.insurance_received = decimal_value(getattr(monthly_figure, "insurance_receipts", 0))
    monthly_figure.payover = decimal_value(getattr(monthly_figure, "insurance_payover", 0))
    monthly_figure.other_income = admin_fee

    royalty_base = calculate_base(monthly_figure, franchise, method=method)
    percentage, amount, minimum, minimum_applied, scale_source, scale_source_label, scale_warnings, scale_errors = calculate_royalty_amount(franchise, royalty_base)

    monthly_figure.gross_turnover = royalty_base
    monthly_figure.gross_revenue = royalty_base
    monthly_figure.gross_method = method
    monthly_figure.royalty_percentage = percentage
    monthly_figure.royalty_amount = amount
    monthly_figure.minimum_royalty_applied = minimum_applied
    if franchise:
        franchise.royalty_gross_method = method

    warnings = method_warnings + scale_warnings
    errors = method_errors + scale_errors
    if royalty_base > 0 and percentage <= 0:
        if "royalty base has value but royalty percentage is 0" not in errors:
            errors.append("royalty base has value but royalty percentage is 0")

    return RoyaltyResult(
        franchise_id=getattr(franchise, "id", None),
        franchise_name=getattr(franchise, "business_name", "") if franchise else "",
        agreement_start_date=str(getattr(franchise, "agreement_start_date", "") or "") if franchise else "",
        agreement_end_date=str(getattr(franchise, "agreement_end_date", "") or "") if franchise else "",
        method=method,
        method_label=method_label(method),
        method_source=method_source,
        royalty_base=royalty_base,
        royalty_percentage=percentage,
        royalty_amount=amount,
        minimum_royalty_amount=minimum,
        minimum_royalty_applied=minimum_applied,
        scale_source_franchise_id=getattr(scale_source, "id", None),
        scale_source_franchise_name=getattr(scale_source, "business_name", "") if scale_source else "",
        warnings=warnings,
        blocking_errors=errors,
    )


def validate_franchise_for_royalties(franchise: Franchise | None, *, month: int | None = None, year: int | None = None) -> dict:
    if not franchise:
        return {"franchise_id": None, "franchise": "", "warnings": [], "blocking_errors": ["missing franchise"]}
    method, source, warnings, errors = select_royalty_method(franchise, period_month=month, period_year=year)
    scales, source_franchise, source_label = get_royalty_scales(franchise)
    if not scales:
        errors.append("missing royalty scale")
    return {
        "franchise_id": franchise.id,
        "franchise": franchise.business_name,
        "agreement_start_date": str(franchise.agreement_start_date or ""),
        "agreement_end_date": str(franchise.agreement_end_date or ""),
        "method": method,
        "method_label": method_label(method),
        "method_source": source,
        "scale_count": len(scales),
        "scale_source": source_label,
        "scale_source_franchise_id": getattr(source_franchise, "id", None),
        "scale_source_franchise": getattr(source_franchise, "business_name", "") if source_franchise else "",
        "warnings": warnings,
        "blocking_errors": errors,
        "blocking": bool(errors),
    }
