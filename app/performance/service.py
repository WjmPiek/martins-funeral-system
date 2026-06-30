from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from flask import g, has_request_context
from sqlalchemy import func

from app.extensions import db
from app.franchise_context import get_accessible_franchises, get_selected_franchise, is_franchise_view_mode
from app.models import Franchise, FranchiseTarget, MonthlyFigure, PerformanceGrowthBracket, PerformanceResult, PerformanceSnapshot

MONTHS = [
    (1, "January"), (2, "February"), (3, "March"), (4, "April"),
    (5, "May"), (6, "June"), (7, "July"), (8, "August"),
    (9, "September"), (10, "October"), (11, "November"), (12, "December"),
]
MONTH_NAME = dict(MONTHS)

# The business KPI names match the requested dashboard language.
# source_field points to the existing monthly_figures table column.
PERFORMANCE_METRICS = {
    "cash": {
        "label": "Cash",
        "source_field": "cash",
        "format": "money",
        "weight": Decimal("0.30"),
        "higher_is_better": True,
    },
    "sales": {
        "label": "Sales",
        "source_field": "sales",
        "format": "money",
        "weight": Decimal("0.25"),
        "higher_is_better": True,
    },
    "insurance_premiums": {
        "label": "Insurance Premiums",
        "source_field": "insurance_receipts",
        "format": "money",
        "weight": Decimal("0.20"),
        "higher_is_better": True,
    },
    "joinings": {
        "label": "Joinings",
        "source_field": "insurance_joinings",
        "format": "number",
        "weight": Decimal("0.15"),
        "higher_is_better": True,
    },
    "funerals": {
        "label": "Funerals",
        "source_field": "number_of_funerals",
        "format": "number",
        "weight": Decimal("0.10"),
        "higher_is_better": True,
    },
}

TARGET_MODES = {
    "manual": "Manual Head Office Target",
    "previous_year": "Same Month Previous Year",
    "previous_year_growth": "Previous Year + Growth %",
    "three_year_average": "3-Year Same Month Average",
    "three_year_growth": "3-Year Average + Growth %",
    "growth_bracket": "Fair Growth Bracket",
    "annual_gross_scale": "SA GDP Growth Standard",
}

DEFAULT_GROWTH_PERCENT = Decimal("1.60")
DEFAULT_SA_GDP_GROWTH_PERCENT = Decimal("1.60")
SCORE_CAP_PERCENT = Decimal("150")


def _performance_cache():
    """Small per-request cache for expensive analytics queries.

    Performance pages often call the same monthly aggregate repeatedly while
    building KPI cards, graphs, leaderboards and target explanations. Keeping
    the cache on Flask's request context avoids stale data across requests while
    removing dozens/hundreds of duplicate SQL queries from a single page load.
    """
    if not has_request_context():
        return None
    cache = getattr(g, "performance_cache", None)
    if cache is None:
        cache = {}
        g.performance_cache = cache
    return cache


def _cached_value(key, factory):
    cache = _performance_cache()
    if cache is None:
        return factory()
    if key not in cache:
        cache[key] = factory()
    return cache[key]


def _ids_key(franchise_ids):
    return tuple(sorted(int(fid) for fid in franchise_ids or []))


def _metrics_key(metric_keys):
    return tuple(metric_keys or PERFORMANCE_METRICS.keys())


def to_decimal(value):
    if value is None:
        return Decimal("0")
    return Decimal(str(value))



def growth_rate(value, baseline):
    value = to_decimal(value)
    baseline = to_decimal(baseline)
    if baseline <= 0:
        return Decimal("0")
    return ((value - baseline) / baseline * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)




def growth_status(growth_percent):
    """Traffic-light status for franchise growth.

    Green = growing greater than 10%, yellow = stable 0-10%, red = declining below 0%.
    """
    growth = to_decimal(growth_percent)
    if growth > Decimal("10"):
        return {"label": "Growing", "colour": "green", "class": "success"}
    if growth >= Decimal("0"):
        return {"label": "Stable", "colour": "yellow", "class": "warning"}
    return {"label": "Declining", "colour": "red", "class": "danger"}


def ytd_actual(franchise_id, metric_key, month, year):
    total = Decimal("0")
    for m in range(1, month + 1):
        total += period_actuals(m, year, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
    return round_money(total)


def monthly_growth_percent(franchise_id, metric_key, month, year):
    actual = period_actuals(month, year, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
    prev_m, prev_y = previous_month(month, year)
    previous = period_actuals(prev_m, prev_y, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
    return growth_rate(actual, previous)


def year_to_date_growth_percent(franchise_id, metric_key, month, year):
    current_ytd = ytd_actual(franchise_id, metric_key, month, year)
    previous_ytd = ytd_actual(franchise_id, metric_key, month, year - 1)
    return growth_rate(current_ytd, previous_ytd)


def annual_growth_percent_formula(franchise_id, metric_key, year):
    current_year = annual_actual(franchise_id, metric_key, year)
    previous_year = annual_actual(franchise_id, metric_key, year - 1)
    return growth_rate(current_year, previous_year)


def average_monthly_growth_percent(franchise_id, metric_key, end_month, end_year, periods=12):
    growth_values = []
    m, y = end_month, end_year
    for _ in range(periods):
        actual = period_actuals(m, y, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
        prev_m, prev_y = previous_month(m, y)
        previous = period_actuals(prev_m, prev_y, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
        if previous > 0:
            growth_values.append(growth_rate(actual, previous))
        m, y = prev_m, prev_y
    return safe_average(growth_values).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if growth_values else Decimal("0")


def three_year_growth_percent(franchise_id, metric_key, month, year):
    current = period_actuals(month, year, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
    base = period_actuals(month, year - 3, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
    return growth_rate(current, base)

def safe_average(values):
    values = [to_decimal(value) for value in values if to_decimal(value) > 0]
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def default_basis_metric(metric_key):
    # Money KPIs use their own value. Count KPIs use themselves so joinings and funerals can have realistic count brackets.
    return metric_key if metric_key in PERFORMANCE_METRICS else "cash"


def historical_basis_value(franchise_id, metric_key, month, year):
    """Return the baseline used to select a fair growth bracket.

    The target bracket is based on historical business size, not a single percentage for everybody.
    Prefer same month last year, then previous month, then a 3-year same-month average.
    """
    last_year = comparison_value(franchise_id, metric_key, month, year, "same_month_last_year")
    if last_year > 0:
        return last_year
    prev = comparison_value(franchise_id, metric_key, month, year, "previous_month")
    if prev > 0:
        return prev
    return comparison_value(franchise_id, metric_key, month, year, "three_year_average")


def bracket_growth_percent(franchise_id, metric_key, month, year):
    basis_metric = default_basis_metric(metric_key)
    basis_value = historical_basis_value(franchise_id, basis_metric, month, year)
    brackets = active_growth_brackets(metric_key)
    if not brackets:
        # Fallback keeps Phase 1 safe before Head Office edits brackets.
        if metric_key in ("joinings", "funerals"):
            return Decimal("10")
        if basis_value < Decimal("150000"):
            return Decimal("15")
        if basis_value < Decimal("300000"):
            return Decimal("12")
        if basis_value < Decimal("500000"):
            return Decimal("10")
        if basis_value < Decimal("750000"):
            return Decimal("8")
        if basis_value < Decimal("1200000"):
            return Decimal("6")
        return Decimal("5")
    for bracket in brackets:
        low = to_decimal(bracket.amount_from)
        high = bracket.amount_to
        high = to_decimal(high) if high is not None else None
        if basis_value >= low and (high is None or basis_value < high):
            return to_decimal(bracket.growth_percent)
    return to_decimal(brackets[-1].growth_percent)





def active_growth_brackets(metric_key):
    cache_key = ("active_growth_brackets", metric_key)

    def load():
        return (
            PerformanceGrowthBracket.query
            .filter_by(metric=metric_key, is_active=True)
            .order_by(PerformanceGrowthBracket.amount_from.asc())
            .all()
        )

    return _cached_value(cache_key, load)


def growth_bracket_label(bracket):
    if not bracket:
        return "Default bracket"
    low = to_decimal(bracket.amount_from)
    high = bracket.amount_to
    if high is None:
        return f"{low:,.2f}+"
    return f"{low:,.2f} - {to_decimal(high):,.2f}"


def selected_growth_bracket(franchise_id, metric_key, month, year):
    """Return the exact bracket used for a franchise metric target.

    Phase 2 makes the bracket engine transparent: users can see why a target
    was selected, which baseline was used, and the growth percentage applied.
    """
    basis_metric = default_basis_metric(metric_key)
    basis_value = historical_basis_value(franchise_id, basis_metric, month, year)
    brackets = active_growth_brackets(metric_key)
    for bracket in brackets:
        low = to_decimal(bracket.amount_from)
        high = to_decimal(bracket.amount_to) if bracket.amount_to is not None else None
        if basis_value >= low and (high is None or basis_value < high):
            return bracket, basis_value, basis_metric
    return (brackets[-1] if brackets else None), basis_value, basis_metric


def bracket_target_details(franchise_id, metric_key, month, year):
    bracket, basis_value, basis_metric = selected_growth_bracket(franchise_id, metric_key, month, year)
    growth_percent = to_decimal(bracket.growth_percent) if bracket else bracket_growth_percent(franchise_id, metric_key, month, year)
    target_value = round_money(basis_value * (Decimal("1") + growth_percent / Decimal("100")))
    return {
        "metric": metric_key,
        "metric_label": PERFORMANCE_METRICS[metric_key]["label"],
        "basis_metric": basis_metric,
        "basis_metric_label": PERFORMANCE_METRICS.get(basis_metric, {}).get("label", basis_metric),
        "basis_value": round_money(basis_value),
        "growth_percent": growth_percent,
        "target_value": target_value,
        "bracket_id": bracket.id if bracket else None,
        "bracket_label": growth_bracket_label(bracket),
        "formula": "Target = Previous comparable value x (1 + bracket growth %)",
        "growth_formula": "Growth % = (Current Period - Previous Period) / Previous Period x 100",
        "growth_status": growth_status(growth_percent),
    }


def target_plan_for(franchise_id, month, year, metric_keys=None):
    metric_keys = metric_keys or list(PERFORMANCE_METRICS.keys())
    return [bracket_target_details(franchise_id, metric_key, month, year) for metric_key in metric_keys]


def target_plan_for_period(month, year, franchise_ids, metric_keys=None):
    result = {}
    metric_keys = metric_keys or list(PERFORMANCE_METRICS.keys())
    for franchise_id in franchise_ids:
        items = [annual_gross_scale_details(franchise_id, metric_key, month, year) for metric_key in metric_keys]
        result[franchise_id] = {item["metric"]: item for item in items}
    return result


def save_growth_bracket_targets(month, year, franchise_ids, metric_keys=None):
    """Capture current bracket-generated targets as Head Office targets.

    This lets management generate fair targets from brackets and then keep
    those exact values stable for reporting, while still allowing manual edits.
    """
    metric_keys = metric_keys or list(PERFORMANCE_METRICS.keys())
    saved = 0
    for franchise_id in franchise_ids:
        for detail in [annual_gross_scale_details(franchise_id, metric_key, month, year) for metric_key in (metric_keys or list(PERFORMANCE_METRICS.keys()))]:
            target = FranchiseTarget.query.filter_by(
                franchise_id=franchise_id,
                metric=detail["metric"],
                year=year,
                month=month,
            ).first()
            if not target:
                target = FranchiseTarget(franchise_id=franchise_id, metric=detail["metric"], year=year, month=month)
                db.session.add(target)
            target.target_value = detail["target_value"]
            saved += 1
    db.session.commit()
    return saved



def annual_gross_turnover(franchise_id, year):
    total = (
        db.session.query(func.coalesce(func.sum(MonthlyFigure.gross_turnover), 0))
        .filter(MonthlyFigure.franchise_id == franchise_id, MonthlyFigure.year == year)
        .scalar()
    )
    return round_money(total)

def annual_gross_average(franchise_id, year):
    return round_money(annual_gross_turnover(franchise_id, year) / Decimal("12"))

def annual_gross_scale_percent(franchise_id, target_year):
    # The following year's target uses the prior year's average monthly gross turnover
    # to choose a fair scale percentage. Example: 2026 uses 2025 gross turnover / 12.
    basis_value = annual_gross_average(franchise_id, target_year - 1)
    brackets = active_growth_brackets("gross_turnover")
    if not brackets:
        defaults = [
            (Decimal("0"), Decimal("100000"), DEFAULT_SA_GDP_GROWTH_PERCENT),
            (Decimal("100000"), Decimal("200000"), DEFAULT_SA_GDP_GROWTH_PERCENT),
            (Decimal("200000"), Decimal("400000"), DEFAULT_SA_GDP_GROWTH_PERCENT),
            (Decimal("400000"), Decimal("700000"), DEFAULT_SA_GDP_GROWTH_PERCENT),
            (Decimal("700000"), Decimal("1200000"), DEFAULT_SA_GDP_GROWTH_PERCENT),
            (Decimal("1200000"), None, DEFAULT_SA_GDP_GROWTH_PERCENT),
        ]
        for low, high, pct in defaults:
            if basis_value >= low and (high is None or basis_value < high):
                return pct, basis_value, None
        return DEFAULT_SA_GDP_GROWTH_PERCENT, basis_value, None
    for bracket in brackets:
        low = to_decimal(bracket.amount_from)
        high = to_decimal(bracket.amount_to) if bracket.amount_to is not None else None
        if basis_value >= low and (high is None or basis_value < high):
            return to_decimal(bracket.growth_percent), basis_value, bracket
    return to_decimal(brackets[-1].growth_percent), basis_value, brackets[-1]

def annual_gross_scale_target(franchise_id, metric_key, month, target_year):
    # Formula: prior-year same-month actual + prior-year same-month actual * scale %.
    # The scale % is selected from prior-year annual gross turnover / 12.
    prior_value = period_actuals(month, target_year - 1, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
    pct, basis_value, bracket = annual_gross_scale_percent(franchise_id, target_year)
    growth_amount = prior_value * pct / Decimal("100")
    return round_money(prior_value + growth_amount)

def annual_gross_scale_details(franchise_id, metric_key, month, target_year):
    prior_value = period_actuals(month, target_year - 1, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
    pct, basis_value, bracket = annual_gross_scale_percent(franchise_id, target_year)
    growth_amount = round_money(prior_value * pct / Decimal("100"))
    return {
        "metric": metric_key,
        "metric_label": PERFORMANCE_METRICS[metric_key]["label"],
        "basis_metric": "gross_turnover",
        "basis_metric_label": "Gross Turnover",
        "basis_value": basis_value,
        "growth_percent": pct,
        "growth_amount": growth_amount,
        "prior_year_value": round_money(prior_value),
        "target_value": round_money(prior_value + growth_amount),
        "bracket_id": bracket.id if bracket else None,
        "bracket_label": growth_bracket_label(bracket) if bracket else f"{basis_value:,.2f}",
        "formula": "Target = same month previous year + (same month previous year x SA GDP growth %)",
        "scale_formula": "Growth % defaults to the South Africa GDP growth standard. Admin may edit the scale table only from the Admin portal.",
        "growth_status": growth_status(pct),
    }

def round_money(value):
    return to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def percent(actual, target):
    actual = to_decimal(actual)
    target = to_decimal(target)
    if target <= 0:
        return Decimal("0")
    return (actual / target * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def month_label(month, year):
    return f"{MONTH_NAME.get(month, month)} {year}"


def previous_month(month, year):
    return (12, year - 1) if month == 1 else (month - 1, year)


def same_month_last_year(month, year):
    return month, year - 1


def previous_years(month, year, count=3):
    return [(month, year - index) for index in range(1, count + 1)]


def is_franchise_performance_active(franchise):
    return bool(getattr(franchise, "is_performance_active", True))


def filter_active_franchise_ids(franchise_ids, include_inactive=False):
    if include_inactive or not franchise_ids:
        return franchise_ids
    rows = Franchise.query.filter(Franchise.id.in_(franchise_ids)).all()
    return [franchise.id for franchise in rows if is_franchise_performance_active(franchise)]


def accessible_franchise_ids(include_inactive=False):
    selected = get_selected_franchise()
    if selected and is_franchise_view_mode():
        ids = [selected.id]
    else:
        ids = [franchise.id for franchise in get_accessible_franchises()]
    return filter_active_franchise_ids(ids, include_inactive=include_inactive)




def active_leaderboard_franchise_ids(include_inactive=False):
    """Return the franchise scope used for public leaderboard ranking.

    Franchise users must be able to see where they rank against all active
    franchise users, while their detailed graphs/KPI pages remain scoped by
    accessible_franchise_ids().
    """
    query = Franchise.query.order_by(Franchise.business_name)
    if not include_inactive:
        query = query.filter(Franchise.is_performance_active == True)
    return [franchise.id for franchise in query.all()]

def previous_periods_including(month, year, count=3):
    periods = []
    m, y = month, year
    for _ in range(count):
        periods.append((m, y))
        m, y = previous_month(m, y)
    return periods


def has_recent_performance_data(franchise_id, month, year, periods=3):
    period_pairs = previous_periods_including(month, year, periods)
    if not period_pairs:
        return False
    conditions = []
    for m, y in period_pairs:
        conditions.append((MonthlyFigure.month == m) & (MonthlyFigure.year == y))
    total_columns = [func.coalesce(func.sum(metric_field(metric_key)), 0) for metric_key in PERFORMANCE_METRICS]
    row = (
        db.session.query(*total_columns)
        .filter(MonthlyFigure.franchise_id == franchise_id)
        .filter(db.or_(*conditions))
        .first()
    )
    if not row:
        return False
    return any(to_decimal(value) > 0 for value in row)


def inactive_franchise_candidates(month, year, franchise_ids=None):
    ids = franchise_ids if franchise_ids is not None else accessible_franchise_ids(include_inactive=True)
    franchises = Franchise.query.filter(Franchise.id.in_(ids)).order_by(Franchise.business_name.asc()).all() if ids else []
    rows = []
    for franchise in franchises:
        has_data = has_recent_performance_data(franchise.id, month, year, 3)
        rows.append({
            "franchise": franchise,
            "has_recent_data": has_data,
            "is_performance_active": is_franchise_performance_active(franchise),
            "status": "active" if is_franchise_performance_active(franchise) else "hidden",
            "reason": getattr(franchise, "performance_inactive_reason", "") or "No Cash, Sales, Insurance, Joinings or Funerals data in the last 3 months",
        })
    return rows


def auto_hide_inactive_franchises(month, year, franchise_ids=None, changed_by_id=None):
    ids = franchise_ids if franchise_ids is not None else accessible_franchise_ids(include_inactive=True)
    changed = 0
    for item in inactive_franchise_candidates(month, year, ids):
        franchise = item["franchise"]
        if item["has_recent_data"]:
            continue
        if not is_franchise_performance_active(franchise):
            continue
        franchise.is_performance_active = False
        franchise.performance_inactive_at = datetime.now(timezone.utc)
        franchise.performance_inactive_reason = f"Auto-hidden: no imported KPI data for the 3 months ending {month_label(month, year)}."
        changed += 1
    if changed:
        db.session.commit()
    return changed


def reactivate_franchise_performance(franchise_id, user_id=None):
    franchise = Franchise.query.get(franchise_id)
    if not franchise:
        return None
    franchise.is_performance_active = True
    franchise.performance_reactivated_at = datetime.now(timezone.utc)
    franchise.performance_reactivated_by_id = user_id
    franchise.performance_inactive_reason = ""
    db.session.commit()
    return franchise


def selected_period_from_request(args):
    now = datetime.now()
    default_month, default_year = previous_month(now.month, now.year)
    try:
        month = int(args.get("month", default_month))
    except Exception:
        month = default_month
    try:
        year = int(args.get("year", default_year))
    except Exception:
        year = default_year
    if month < 1 or month > 12:
        month = default_month
    if year < 2000 or year > 2100:
        year = default_year
    return month, year


def reporting_years():
    def load():
        current_year = datetime.now().year
        years = [row[0] for row in db.session.query(MonthlyFigure.year).distinct().order_by(MonthlyFigure.year.desc()).all()]
        if current_year not in years:
            years.insert(0, current_year)
        return years
    return _cached_value(("reporting_years",), load)


def metric_field(metric_key):
    return getattr(MonthlyFigure, PERFORMANCE_METRICS[metric_key]["source_field"])


def period_actuals(month, year, franchise_ids, metric_keys=None):
    franchise_ids = filter_active_franchise_ids(franchise_ids)
    metric_keys = list(metric_keys or PERFORMANCE_METRICS.keys())
    if not franchise_ids:
        return {}

    cache_key = ("period_actuals", int(month), int(year), _ids_key(franchise_ids), _metrics_key(metric_keys))

    def load():
        columns = [MonthlyFigure.franchise_id]
        for metric_key in metric_keys:
            columns.append(func.coalesce(func.sum(metric_field(metric_key)), 0).label(metric_key))
        rows = (
            db.session.query(*columns)
            .filter(MonthlyFigure.franchise_id.in_(franchise_ids))
            .filter(MonthlyFigure.month == month, MonthlyFigure.year == year)
            .group_by(MonthlyFigure.franchise_id)
            .all()
        )
        return {
            row.franchise_id: {metric_key: to_decimal(getattr(row, metric_key)) for metric_key in metric_keys}
            for row in rows
        }

    return _cached_value(cache_key, load)



def stored_results_for_period(month, year, franchise_ids, metric_keys=None):
    """Return pre-calculated performance rows from performance_results.

    This is the fast path used by dashboards and graphs.  Heavy calculations are
    done once by rebuild_performance_results() after import/recalculate; page
    requests should mainly read these rows.
    """
    franchise_ids = filter_active_franchise_ids(franchise_ids)
    metric_keys = list(metric_keys or PERFORMANCE_METRICS.keys())
    if not franchise_ids:
        return {}
    cache_key = ("stored_results_for_period", int(month), int(year), _ids_key(franchise_ids), _metrics_key(metric_keys))

    def load():
        rows = PerformanceResult.query.filter(
            PerformanceResult.franchise_id.in_(franchise_ids),
            PerformanceResult.year == year,
            PerformanceResult.month == month,
            PerformanceResult.metric.in_(metric_keys),
        ).all()
        data = {}
        for row in rows:
            data.setdefault(row.franchise_id, {})[row.metric] = row
        return data

    return _cached_value(cache_key, load)


def period_has_stored_results(month, year, franchise_ids, metric_keys=None):
    metric_keys = list(metric_keys or PERFORMANCE_METRICS.keys())
    franchise_ids = filter_active_franchise_ids(franchise_ids)
    if not franchise_ids:
        return False
    stored = stored_results_for_period(month, year, franchise_ids, metric_keys)
    expected = len(franchise_ids) * len(metric_keys)
    found = sum(1 for fid in franchise_ids for metric in metric_keys if stored.get(fid, {}).get(metric))
    return found >= expected


def ensure_performance_results(month, year, franchise_ids=None, mode="growth_bracket"):
    """Create missing cache rows for a period, but never block on repeated reads.

    For normal page loads this function is intentionally conservative: if there
    are already rows for the period it returns immediately.  Imports and the
    recalculate button call rebuild_performance_results() for a full refresh.
    """
    franchise_ids = filter_active_franchise_ids(franchise_ids or accessible_franchise_ids())
    if not franchise_ids:
        return 0
    if period_has_stored_results(month, year, franchise_ids):
        return 0
    return rebuild_performance_results(month, year, franchise_ids, mode)

def stored_targets(month, year, franchise_ids, metric_keys=None):
    metric_keys = list(metric_keys or PERFORMANCE_METRICS.keys())
    franchise_ids = list(franchise_ids or [])
    if not franchise_ids:
        return {}

    cache_key = ("stored_targets", int(month), int(year), _ids_key(franchise_ids), _metrics_key(metric_keys))

    def load():
        rows = FranchiseTarget.query.filter(
            FranchiseTarget.franchise_id.in_(franchise_ids),
            FranchiseTarget.year == year,
            FranchiseTarget.month == month,
            FranchiseTarget.metric.in_(metric_keys),
        ).all()
        targets = {}
        for row in rows:
            targets.setdefault(row.franchise_id, {})[row.metric] = to_decimal(row.target_value)
        return targets

    return _cached_value(cache_key, load)


def auto_target_for(franchise_id, metric_key, month, year, mode="previous_year_growth", growth_percent=DEFAULT_GROWTH_PERCENT):
    mode = mode if mode in TARGET_MODES else "previous_year_growth"
    growth_percent = to_decimal(growth_percent)
    if mode == "previous_year":
        source = period_actuals(month, year - 1, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
        return round_money(source)
    if mode == "previous_year_growth":
        source = period_actuals(month, year - 1, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
        return round_money(source * (Decimal("1") + growth_percent / Decimal("100")))
    if mode == "three_year_average" or mode == "three_year_growth":
        values = []
        for m, y in previous_years(month, year, 3):
            value = period_actuals(m, y, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
            if value > 0:
                values.append(value)
        average = sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")
        if mode == "three_year_growth":
            average = average * (Decimal("1") + growth_percent / Decimal("100"))
        return round_money(average)
    if mode == "growth_bracket":
        return bracket_target_details(franchise_id, metric_key, month, year)["target_value"]
    if mode == "annual_gross_scale":
        return annual_gross_scale_target(franchise_id, metric_key, month, year)
    return Decimal("0")


def targets_for_period(month, year, franchise_ids, mode="manual", growth_percent=DEFAULT_GROWTH_PERCENT, metric_keys=None):
    franchise_ids = filter_active_franchise_ids(franchise_ids)
    metric_keys = metric_keys or list(PERFORMANCE_METRICS.keys())
    manual = stored_targets(month, year, franchise_ids, metric_keys)
    result = {}
    for franchise_id in franchise_ids:
        result[franchise_id] = {}
        for metric_key in metric_keys:
            manual_value = manual.get(franchise_id, {}).get(metric_key)
            if mode == "manual" and manual_value is not None:
                result[franchise_id][metric_key] = manual_value
            elif manual_value is not None and manual_value > 0:
                # Manually captured Head Office targets always win when present.
                result[franchise_id][metric_key] = manual_value
            else:
                result[franchise_id][metric_key] = auto_target_for(franchise_id, metric_key, month, year, mode, growth_percent)
    return result


def comparison_value(franchise_id, metric_key, month, year, comparison):
    if comparison == "previous_month":
        m, y = previous_month(month, year)
    elif comparison == "same_month_last_year":
        m, y = same_month_last_year(month, year)
    elif comparison == "three_year_average":
        values = []
        for m, y in previous_years(month, year, 3):
            value = period_actuals(m, y, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
            if value > 0:
                values.append(value)
        return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")
    else:
        return Decimal("0")
    return period_actuals(m, y, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))


def franchise_metric_summary(franchise_id, month, year, mode="manual", growth_percent=DEFAULT_GROWTH_PERCENT):
    stored_rows = stored_results_for_period(month, year, [franchise_id]).get(franchise_id, {})
    use_stored = bool(stored_rows)
    if not use_stored:
        actuals = period_actuals(month, year, [franchise_id]).get(franchise_id, {})
        targets = targets_for_period(month, year, [franchise_id], mode, growth_percent).get(franchise_id, {})
    rows = []
    for metric_key, config in PERFORMANCE_METRICS.items():
        bracket_details = bracket_target_details(franchise_id, metric_key, month, year)
        if use_stored and metric_key in stored_rows:
            result = stored_rows[metric_key]
            actual = to_decimal(result.actual_value)
            target = to_decimal(result.target_value)
            previous = to_decimal(result.previous_month_value)
            last_year = to_decimal(result.same_month_last_year_value)
            three_year = to_decimal(result.three_year_average_value)
            mom_growth = growth_rate(actual, previous)
            yoy_growth = growth_rate(actual, last_year)
            ytd_growth = Decimal("0")
            annual_growth = Decimal("0")
            average_growth = Decimal("0")
            three_year_growth = growth_rate(actual, three_year)
        else:
            actual = actuals.get(metric_key, Decimal("0"))
            target = targets.get(metric_key, Decimal("0"))
            previous = comparison_value(franchise_id, metric_key, month, year, "previous_month")
            last_year = comparison_value(franchise_id, metric_key, month, year, "same_month_last_year")
            three_year = comparison_value(franchise_id, metric_key, month, year, "three_year_average")
            mom_growth = growth_rate(actual, previous)
            yoy_growth = growth_rate(actual, last_year)
            ytd_growth = year_to_date_growth_percent(franchise_id, metric_key, month, year)
            annual_growth = annual_growth_percent_formula(franchise_id, metric_key, year)
            average_growth = average_monthly_growth_percent(franchise_id, metric_key, month, year, 12)
            three_year_growth = three_year_growth_percent(franchise_id, metric_key, month, year)
        rows.append({
            "key": metric_key,
            "label": config["label"],
            "format": config["format"],
            "actual": actual,
            "target": target,
            "target_percent": percent(actual, target),
            "target_difference": actual - target,
            "previous_month": previous,
            "previous_month_difference": actual - previous,
            "previous_month_percent": percent(actual, previous),
            "monthly_growth_percent": mom_growth,
            "monthly_growth_status": growth_status(mom_growth),
            "same_month_last_year": last_year,
            "same_month_last_year_difference": actual - last_year,
            "same_month_last_year_percent": percent(actual, last_year),
            "same_month_last_year_growth_percent": yoy_growth,
            "same_month_last_year_growth_status": growth_status(yoy_growth),
            "ytd_growth_percent": ytd_growth,
            "ytd_growth_status": growth_status(ytd_growth),
            "annual_growth_percent": annual_growth,
            "annual_growth_status": growth_status(annual_growth),
            "average_monthly_growth_percent": average_growth,
            "average_monthly_growth_status": growth_status(average_growth),
            "three_year_growth_percent": three_year_growth,
            "three_year_growth_status": growth_status(three_year_growth),
            "three_year_average": three_year,
            "three_year_average_difference": actual - three_year,
            "three_year_average_percent": percent(actual, three_year),
            "growth_target_percent": bracket_details["growth_percent"],
            "growth_basis_value": bracket_details["basis_value"],
            "growth_basis_metric": bracket_details["basis_metric"],
            "growth_basis_metric_label": bracket_details["basis_metric_label"],
            "growth_bracket_label": bracket_details["bracket_label"],
        })
    return rows


def metric_score(actual, target):
    if to_decimal(target) <= 0:
        return Decimal("0")
    return min(percent(actual, target), SCORE_CAP_PERCENT)


def performance_score(actuals, targets):
    total = Decimal("0")
    weight_total = Decimal("0")
    for metric_key, config in PERFORMANCE_METRICS.items():
        target = targets.get(metric_key, Decimal("0"))
        if target > 0:
            total += metric_score(actuals.get(metric_key, Decimal("0")), target) * config["weight"]
            weight_total += config["weight"]
    if weight_total <= 0:
        return Decimal("0")
    return (total / weight_total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ranked_performance(month, year, franchise_ids, mode="manual", growth_percent=DEFAULT_GROWTH_PERCENT, metric_key="overall"):
    franchise_ids = filter_active_franchise_ids(franchise_ids)
    def load_franchises():
        return Franchise.query.filter(Franchise.id.in_(franchise_ids)).order_by(Franchise.business_name.asc()).all() if franchise_ids else []
    franchises = _cached_value(("franchises", _ids_key(franchise_ids)), load_franchises)

    stored_by = stored_results_for_period(month, year, franchise_ids)
    use_stored = any(stored_by.get(franchise.id) for franchise in franchises)
    if not use_stored:
        actuals_by = period_actuals(month, year, franchise_ids)
        targets_by = targets_for_period(month, year, franchise_ids, mode, growth_percent)

    rows = []
    for franchise in franchises:
        if use_stored:
            result_rows = stored_by.get(franchise.id, {})
            if metric_key == "overall":
                actuals = {key: to_decimal(result_rows.get(key).actual_value) for key in PERFORMANCE_METRICS if result_rows.get(key)}
                targets = {key: to_decimal(result_rows.get(key).target_value) for key in PERFORMANCE_METRICS if result_rows.get(key)}
                score = performance_score(actuals, targets)
                actual = sum(actuals.values(), Decimal("0"))
                target = sum(targets.values(), Decimal("0"))
                achievement = score
            else:
                result = result_rows.get(metric_key)
                actual = to_decimal(result.actual_value) if result else Decimal("0")
                target = to_decimal(result.target_value) if result else Decimal("0")
                achievement = to_decimal(result.achievement_percent) if result else Decimal("0")
                score = achievement
        else:
            actuals = actuals_by.get(franchise.id, {})
            targets = targets_by.get(franchise.id, {})
            if metric_key == "overall":
                score = performance_score(actuals, targets)
                actual = sum(actuals.values(), Decimal("0"))
                target = sum(targets.values(), Decimal("0"))
                achievement = score
            else:
                actual = actuals.get(metric_key, Decimal("0"))
                target = targets.get(metric_key, Decimal("0"))
                achievement = percent(actual, target)
                score = achievement
        rows.append({
            "franchise_id": franchise.id,
            "franchise_name": franchise.business_name or "Unnamed Franchise",
            "actual": actual,
            "target": target,
            "achievement": achievement,
            "score": score,
            "rank": 0,
        })
    rows.sort(key=lambda item: (item["score"], item["actual"]), reverse=True)
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def attach_movement(rows, previous_rows):
    previous_rank = {row["franchise_id"]: row["rank"] for row in previous_rows}
    for row in rows:
        old = previous_rank.get(row["franchise_id"])
        row["previous_rank"] = old
        if old is None:
            row["movement"] = "same"
            row["movement_label"] = "Same"
            row["movement_delta"] = 0
        else:
            delta = old - row["rank"]
            row["movement_delta"] = delta
            if delta > 0:
                row["movement"] = "up"
                row["movement_label"] = "Up"
            elif delta < 0:
                row["movement"] = "down"
                row["movement_label"] = "Down"
            else:
                row["movement"] = "same"
                row["movement_label"] = "Same"
    return rows


def trend_series(franchise_id, metric_key, end_month, end_year, periods=12, mode="manual", growth_percent=DEFAULT_GROWTH_PERCENT):
    periods_list = []
    m, y = end_month, end_year
    for _ in range(periods):
        periods_list.append((m, y))
        m, y = previous_month(m, y)
    periods_list.reverse()
    series = []
    for m, y in periods_list:
        stored = stored_results_for_period(m, y, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key)
        if stored:
            actual = to_decimal(stored.actual_value)
            target = to_decimal(stored.target_value)
            achievement = to_decimal(stored.achievement_percent)
        else:
            actual = period_actuals(m, y, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
            target = targets_for_period(m, y, [franchise_id], mode, growth_percent, [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
            achievement = percent(actual, target)
        series.append({
            "label": f"{MONTH_NAME.get(m, m)[:3]} {y}",
            "actual": float(actual),
            "target": float(target),
            "achievement": float(achievement),
        })
    return series


def dashboard_snapshot(franchise_id, month=None, year=None, mode="manual", growth_percent=DEFAULT_GROWTH_PERCENT):
    now = datetime.now()
    month = month or now.month
    year = year or now.year
    ids = accessible_franchise_ids()
    if franchise_id not in ids:
        return None
    rows = attach_movement(
        ranked_performance(month, year, ids, mode, growth_percent, "overall"),
        ranked_performance(*previous_month(month, year), ids, mode, growth_percent, "overall"),
    )
    my_row = next((row for row in rows if row["franchise_id"] == franchise_id), None)
    if not my_row:
        return None
    metric_rows = franchise_metric_summary(franchise_id, month, year, mode, growth_percent)
    return {
        "rank": my_row["rank"],
        "total": len(rows),
        "franchise_name": my_row["franchise_name"],
        "movement_label": my_row["movement_label"],
        "movement": my_row["movement"],
        "movement_delta": my_row["movement_delta"],
        "score": my_row["score"],
        "period_label": month_label(month, year),
        "metrics": metric_rows,
    }


def forecast_value(franchise_id, metric_key, month, year):
    # Phase 1 conservative forecast: use current actual until daily PDF import dates are available.
    return period_actuals(month, year, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))


def rebuild_performance_results(month, year, franchise_ids=None, mode="growth_bracket"):
    franchise_ids = filter_active_franchise_ids(franchise_ids or accessible_franchise_ids())
    actuals_by = period_actuals(month, year, franchise_ids)
    targets_by = targets_for_period(month, year, franchise_ids, mode, DEFAULT_GROWTH_PERCENT)
    saved = 0
    for franchise_id in franchise_ids:
        actuals = actuals_by.get(franchise_id, {})
        targets = targets_by.get(franchise_id, {})
        for metric_key in PERFORMANCE_METRICS:
            actual = actuals.get(metric_key, Decimal("0"))
            target = targets.get(metric_key, Decimal("0"))
            previous = comparison_value(franchise_id, metric_key, month, year, "previous_month")
            last_year = comparison_value(franchise_id, metric_key, month, year, "same_month_last_year")
            three_year = comparison_value(franchise_id, metric_key, month, year, "three_year_average")
            result = PerformanceResult.query.filter_by(
                franchise_id=franchise_id, metric=metric_key, year=year, month=month
            ).first()
            if not result:
                result = PerformanceResult(franchise_id=franchise_id, metric=metric_key, year=year, month=month)
                db.session.add(result)
            # Automatically persist generated targets per franchise/user when Head Office
            # has not captured a manual target for this month yet.  This keeps the
            # target history stable after each PDF/monthly import or recalculation.
            existing_target = FranchiseTarget.query.filter_by(
                franchise_id=franchise_id, metric=metric_key, year=year, month=month
            ).first()
            if not existing_target and target > 0:
                db.session.add(FranchiseTarget(
                    franchise_id=franchise_id, metric=metric_key, year=year, month=month, target_value=round_money(target)
                ))

            result.actual_value = round_money(actual)
            result.target_value = round_money(target)
            result.achievement_percent = percent(actual, target)
            result.growth_percent = growth_rate(actual, previous)
            result.previous_month_value = round_money(previous)
            result.same_month_last_year_value = round_money(last_year)
            result.three_year_average_value = round_money(three_year)
            result.forecast_value = round_money(forecast_value(franchise_id, metric_key, month, year))
            saved += 1
    db.session.commit()
    return saved


def months_in_year():
    return [month for month, _name in MONTHS]


def annual_actual(franchise_id, metric_key, year):
    total = Decimal("0")
    for month in months_in_year():
        total += period_actuals(month, year, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
    return round_money(total)


def seasonal_weights(franchise_id, metric_key, target_year, history_years=3):
    """Return month -> seasonal weight based on previous years.

    If there is not enough historical data, distribute the annual target evenly.
    This lets Phase 3 generate a realistic month-by-month budget from the
    franchise's own historical pattern instead of forcing every month to be 1/12.
    """
    monthly_totals = {month: Decimal("0") for month in months_in_year()}
    grand_total = Decimal("0")
    for year in range(target_year - history_years, target_year):
        for month in months_in_year():
            value = period_actuals(month, year, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal("0"))
            if value > 0:
                monthly_totals[month] += value
                grand_total += value
    if grand_total <= 0:
        return {month: (Decimal("1") / Decimal("12")) for month in months_in_year()}
    return {month: (monthly_totals[month] / grand_total) for month in months_in_year()}


def annual_growth_percent(franchise_id, metric_key, target_year):
    # Use December as the target-year anchor because it considers the most recent
    # previous-year monthly business size for the bracket engine.
    return bracket_growth_percent(franchise_id, metric_key, 12, target_year)


def annual_budget_plan(franchise_id, target_year, metric_keys=None, history_years=3):
    metric_keys = metric_keys or list(PERFORMANCE_METRICS.keys())
    plan = []
    for metric_key in metric_keys:
        previous_year_total = annual_actual(franchise_id, metric_key, target_year - 1)
        three_year_values = [annual_actual(franchise_id, metric_key, target_year - offset) for offset in range(1, history_years + 1)]
        usable_values = [value for value in three_year_values if value > 0]
        baseline = safe_average(usable_values) if usable_values else previous_year_total
        growth_percent_value = annual_growth_percent(franchise_id, metric_key, target_year)
        annual_target = round_money(baseline * (Decimal("1") + growth_percent_value / Decimal("100")))
        weights = seasonal_weights(franchise_id, metric_key, target_year, history_years)
        monthly_targets = []
        allocated = Decimal("0")
        for month in months_in_year():
            if month == 12:
                monthly_target = round_money(annual_target - allocated)
            else:
                monthly_target = round_money(annual_target * weights[month])
                allocated += monthly_target
            monthly_targets.append({
                "month": month,
                "month_name": MONTH_NAME[month],
                "weight_percent": (weights[month] * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "target_value": monthly_target,
            })
        plan.append({
            "metric": metric_key,
            "metric_label": PERFORMANCE_METRICS[metric_key]["label"],
            "format": PERFORMANCE_METRICS[metric_key]["format"],
            "previous_year_total": previous_year_total,
            "baseline": round_money(baseline),
            "growth_percent": growth_percent_value,
            "annual_target": annual_target,
            "monthly_targets": monthly_targets,
        })
    return plan


def annual_budget_plan_for_period(target_year, franchise_ids, metric_keys=None, history_years=3):
    return {
        franchise_id: annual_budget_plan(franchise_id, target_year, metric_keys, history_years)
        for franchise_id in franchise_ids
    }


def save_annual_budget_targets(target_year, franchise_ids, metric_keys=None, history_years=3):
    metric_keys = metric_keys or list(PERFORMANCE_METRICS.keys())
    saved = 0
    for franchise_id in franchise_ids:
        for metric_plan in annual_budget_plan(franchise_id, target_year, metric_keys, history_years):
            metric_key = metric_plan["metric"]
            for month_target in metric_plan["monthly_targets"]:
                target = FranchiseTarget.query.filter_by(
                    franchise_id=franchise_id,
                    metric=metric_key,
                    year=target_year,
                    month=month_target["month"],
                ).first()
                if not target:
                    target = FranchiseTarget(franchise_id=franchise_id, metric=metric_key, year=target_year, month=month_target["month"])
                    db.session.add(target)
                target.target_value = month_target["target_value"]
                saved += 1
    db.session.commit()
    return saved

# Phase 4: franchise dashboard helpers

def achievement_status(achievement_percent):
    achievement_percent = to_decimal(achievement_percent)
    if achievement_percent >= Decimal("100"):
        return "good"
    if achievement_percent >= Decimal("90"):
        return "warning"
    return "danger"


def health_score_from_metrics(metric_rows):
    total = Decimal("0")
    weight_total = Decimal("0")
    for row in metric_rows:
        config = PERFORMANCE_METRICS.get(row["key"], {})
        weight = config.get("weight", Decimal("0"))
        if row.get("target", Decimal("0")) > 0:
            total += min(to_decimal(row.get("target_percent", 0)), Decimal("120")) * weight
            weight_total += weight
    if weight_total <= 0:
        return Decimal("0")
    return (total / weight_total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def health_label(score):
    score = to_decimal(score)
    if score >= Decimal("100"):
        return "Excellent"
    if score >= Decimal("90"):
        return "On Track"
    if score >= Decimal("75"):
        return "Needs Attention"
    return "Critical"


def dashboard_decision_insights(metric_rows):
    insights = []
    for row in metric_rows:
        label = row["label"]
        achievement = to_decimal(row.get("target_percent", 0))
        prev_change = to_decimal(row.get("previous_month_difference", 0))
        last_year_change = to_decimal(row.get("same_month_last_year_difference", 0))
        if achievement >= Decimal("100"):
            insights.append({"status": "good", "text": f"{label} is above target at {achievement}%."})
        elif achievement >= Decimal("90"):
            insights.append({"status": "warning", "text": f"{label} is close to target at {achievement}%."})
        else:
            insights.append({"status": "danger", "text": f"{label} is below target at {achievement}%."})
        if prev_change > 0 and last_year_change > 0:
            insights.append({"status": "good", "text": f"{label} is improving against both last month and last year."})
        elif prev_change < 0 and last_year_change < 0:
            insights.append({"status": "danger", "text": f"{label} is down against both last month and last year."})
    return insights[:8]


def franchise_dashboard(franchise_id, month, year, mode="growth_bracket", growth_percent=DEFAULT_GROWTH_PERCENT):
    metric_rows = franchise_metric_summary(franchise_id, month, year, mode, growth_percent)
    score = health_score_from_metrics(metric_rows)
    snapshot = dashboard_snapshot(franchise_id, month, year, mode, growth_percent)
    return {
        "snapshot": snapshot,
        "metrics": [dict(row, status=achievement_status(row.get("target_percent", 0))) for row in metric_rows],
        "health_score": score,
        "health_label": health_label(score),
        "insights": dashboard_decision_insights(metric_rows),
    }

# Phase 5: dedicated KPI page helpers

def metric_direction_label(value):
    value = to_decimal(value)
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "same"


def metric_page_summary(metric_key, month, year, franchise_ids, mode="growth_bracket", growth_percent=DEFAULT_GROWTH_PERCENT):
    """Build one KPI decision page for Cash, Sales, Insurance, Joinings or Funerals."""
    if metric_key not in PERFORMANCE_METRICS:
        metric_key = "cash"
    rows = ranked_performance(month, year, franchise_ids, mode, growth_percent, metric_key)
    previous_m, previous_y = previous_month(month, year)
    rows = attach_movement(
        rows,
        ranked_performance(previous_m, previous_y, franchise_ids, mode, growth_percent, metric_key),
    )
    stored = stored_results_for_period(month, year, franchise_ids, [metric_key])
    if any(stored.get(fid, {}).get(metric_key) for fid in franchise_ids):
        total_actual = sum((to_decimal(stored.get(fid, {}).get(metric_key).actual_value) for fid in franchise_ids if stored.get(fid, {}).get(metric_key)), Decimal("0"))
        total_target = sum((to_decimal(stored.get(fid, {}).get(metric_key).target_value) for fid in franchise_ids if stored.get(fid, {}).get(metric_key)), Decimal("0"))
        previous_total = sum((to_decimal(stored.get(fid, {}).get(metric_key).previous_month_value) for fid in franchise_ids if stored.get(fid, {}).get(metric_key)), Decimal("0"))
        last_year_total = sum((to_decimal(stored.get(fid, {}).get(metric_key).same_month_last_year_value) for fid in franchise_ids if stored.get(fid, {}).get(metric_key)), Decimal("0"))
        three_year_avg = safe_average([to_decimal(stored.get(fid, {}).get(metric_key).three_year_average_value) for fid in franchise_ids if stored.get(fid, {}).get(metric_key)])
    else:
        actuals_by = period_actuals(month, year, franchise_ids, [metric_key])
        targets_by = targets_for_period(month, year, franchise_ids, mode, growth_percent, [metric_key])
        total_actual = sum((actuals_by.get(fid, {}).get(metric_key, Decimal("0")) for fid in franchise_ids), Decimal("0"))
        total_target = sum((targets_by.get(fid, {}).get(metric_key, Decimal("0")) for fid in franchise_ids), Decimal("0"))
        previous_total = sum((period_actuals(previous_m, previous_y, [fid], [metric_key]).get(fid, {}).get(metric_key, Decimal("0")) for fid in franchise_ids), Decimal("0"))
        last_year_total = sum((period_actuals(month, year - 1, [fid], [metric_key]).get(fid, {}).get(metric_key, Decimal("0")) for fid in franchise_ids), Decimal("0"))
        three_year_values = []
        for m, y in previous_years(month, year, 3):
            total = sum((period_actuals(m, y, [fid], [metric_key]).get(fid, {}).get(metric_key, Decimal("0")) for fid in franchise_ids), Decimal("0"))
            if total > 0:
                three_year_values.append(total)
        three_year_avg = safe_average(three_year_values)
    top_rows = rows[:10]
    bottom_rows = list(reversed(rows[-10:])) if len(rows) > 10 else rows[-5:]
    return {
        "metric_key": metric_key,
        "metric": PERFORMANCE_METRICS[metric_key],
        "total_actual": round_money(total_actual),
        "total_target": round_money(total_target),
        "target_percent": percent(total_actual, total_target),
        "target_difference": round_money(total_actual - total_target),
        "previous_month": round_money(previous_total),
        "previous_month_difference": round_money(total_actual - previous_total),
        "previous_month_growth": growth_rate(total_actual, previous_total),
        "last_year": round_money(last_year_total),
        "last_year_difference": round_money(total_actual - last_year_total),
        "last_year_growth": growth_rate(total_actual, last_year_total),
        "three_year_average": round_money(three_year_avg),
        "three_year_difference": round_money(total_actual - three_year_avg),
        "three_year_growth": growth_rate(total_actual, three_year_avg),
        "rows": rows,
        "top_rows": top_rows,
        "bottom_rows": bottom_rows,
        "status": achievement_status(percent(total_actual, total_target)),
    }


def metric_trend_summary(franchise_id, metric_key, month, year, months=12, mode="growth_bracket", growth_percent=DEFAULT_GROWTH_PERCENT):
    series = trend_series(franchise_id, metric_key, month, year, months, mode, growth_percent)
    return {
        "labels": [item["label"] for item in series],
        "actuals": [float(item["actual"]) for item in series],
        "targets": [float(item["target"]) for item in series],
    }


# Phase 6: Graph Engine helpers

def _series_periods(end_month, end_year, periods=12):
    result = []
    m, y = end_month, end_year
    for _ in range(periods):
        result.append((m, y))
        m, y = previous_month(m, y)
    return list(reversed(result))


def previous_year_series(franchise_id, metric_key, end_month, end_year, periods=12):
    series = []
    for m, y in _series_periods(end_month, end_year, periods):
        current = period_actuals(m, y, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal('0'))
        previous = period_actuals(m, y - 1, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal('0'))
        series.append({
            'label': f"{MONTH_NAME.get(m, m)[:3]} {y}",
            'actual': float(current),
            'previous_year': float(previous),
            'growth_percent': float(growth_rate(current, previous)),
        })
    return series


def rolling_12_series(franchise_id, metric_key, end_month, end_year, periods=12):
    series = []
    all_periods = _series_periods(end_month, end_year, periods)
    for m, y in all_periods:
        total = Decimal('0')
        tm, ty = m, y
        for _ in range(12):
            total += period_actuals(tm, ty, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal('0'))
            tm, ty = previous_month(tm, ty)
        series.append({'label': f"{MONTH_NAME.get(m, m)[:3]} {y}", 'rolling_total': float(round_money(total))})
    return series


def forecast_series(franchise_id, metric_key, end_month, end_year, periods=12, mode='growth_bracket', growth_percent=DEFAULT_GROWTH_PERCENT):
    series = []
    for m, y in _series_periods(end_month, end_year, periods):
        actual = period_actuals(m, y, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal('0'))
        target = targets_for_period(m, y, [franchise_id], mode, growth_percent, [metric_key]).get(franchise_id, {}).get(metric_key, Decimal('0'))
        previous = comparison_value(franchise_id, metric_key, m, y, 'previous_month')
        same_last_year = comparison_value(franchise_id, metric_key, m, y, 'same_month_last_year')
        projected = actual
        if actual <= 0:
            projected = safe_average([previous, same_last_year, target])
        elif target > 0 and actual < target:
            projected = safe_average([actual, target, previous if previous > 0 else actual])
        series.append({
            'label': f"{MONTH_NAME.get(m, m)[:3]} {y}",
            'actual': float(round_money(actual)),
            'target': float(round_money(target)),
            'forecast': float(round_money(projected)),
            'forecast_percent': float(percent(projected, target)),
        })
    return series


def growth_trend_series(franchise_id, metric_key, end_month, end_year, periods=12):
    series = []
    for m, y in _series_periods(end_month, end_year, periods):
        actual = period_actuals(m, y, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal('0'))
        last_year = period_actuals(m, y - 1, [franchise_id], [metric_key]).get(franchise_id, {}).get(metric_key, Decimal('0'))
        previous = comparison_value(franchise_id, metric_key, m, y, 'previous_month')
        baseline = last_year if last_year > 0 else previous
        series.append({'label': f"{MONTH_NAME.get(m, m)[:3]} {y}", 'growth_percent': float(growth_rate(actual, baseline))})
    return series



def aggregate_trend_series(franchise_ids, metric_key, end_month, end_year, periods=12, mode="manual", growth_percent=DEFAULT_GROWTH_PERCENT):
    franchise_ids = filter_active_franchise_ids(franchise_ids or [])
    series = []
    for m, y in _series_periods(end_month, end_year, periods):
        actuals = period_actuals(m, y, franchise_ids, [metric_key])
        targets = targets_for_period(m, y, franchise_ids, mode, growth_percent, [metric_key])
        actual = sum((actuals.get(fid, {}).get(metric_key, Decimal('0')) for fid in franchise_ids), Decimal('0'))
        target = sum((targets.get(fid, {}).get(metric_key, Decimal('0')) for fid in franchise_ids), Decimal('0'))
        series.append({
            'label': f"{MONTH_NAME.get(m, m)[:3]} {y}",
            'actual': float(round_money(actual)),
            'target': float(round_money(target)),
            'achievement': float(percent(actual, target)),
        })
    return series


def aggregate_previous_year_series(franchise_ids, metric_key, end_month, end_year, periods=12):
    franchise_ids = filter_active_franchise_ids(franchise_ids or [])
    series = []
    for m, y in _series_periods(end_month, end_year, periods):
        current_rows = period_actuals(m, y, franchise_ids, [metric_key])
        previous_rows = period_actuals(m, y - 1, franchise_ids, [metric_key])
        current = sum((current_rows.get(fid, {}).get(metric_key, Decimal('0')) for fid in franchise_ids), Decimal('0'))
        previous = sum((previous_rows.get(fid, {}).get(metric_key, Decimal('0')) for fid in franchise_ids), Decimal('0'))
        series.append({
            'label': f"{MONTH_NAME.get(m, m)[:3]} {y}",
            'actual': float(round_money(current)),
            'previous_year': float(round_money(previous)),
            'growth_percent': float(growth_rate(current, previous)),
        })
    return series


def aggregate_rolling_12_series(franchise_ids, metric_key, end_month, end_year, periods=12):
    franchise_ids = filter_active_franchise_ids(franchise_ids or [])
    series = []
    for m, y in _series_periods(end_month, end_year, periods):
        total = Decimal('0')
        tm, ty = m, y
        for _ in range(12):
            rows = period_actuals(tm, ty, franchise_ids, [metric_key])
            total += sum((rows.get(fid, {}).get(metric_key, Decimal('0')) for fid in franchise_ids), Decimal('0'))
            tm, ty = previous_month(tm, ty)
        series.append({'label': f"{MONTH_NAME.get(m, m)[:3]} {y}", 'rolling_total': float(round_money(total))})
    return series


def aggregate_forecast_series(franchise_ids, metric_key, end_month, end_year, periods=12, mode='growth_bracket', growth_percent=DEFAULT_GROWTH_PERCENT):
    franchise_ids = filter_active_franchise_ids(franchise_ids or [])
    series = []
    for m, y in _series_periods(end_month, end_year, periods):
        actuals = period_actuals(m, y, franchise_ids, [metric_key])
        targets = targets_for_period(m, y, franchise_ids, mode, growth_percent, [metric_key])
        actual = sum((actuals.get(fid, {}).get(metric_key, Decimal('0')) for fid in franchise_ids), Decimal('0'))
        target = sum((targets.get(fid, {}).get(metric_key, Decimal('0')) for fid in franchise_ids), Decimal('0'))
        previous_rows = period_actuals(*previous_month(m, y), franchise_ids, [metric_key])
        previous = sum((previous_rows.get(fid, {}).get(metric_key, Decimal('0')) for fid in franchise_ids), Decimal('0'))
        same_last_year_rows = period_actuals(m, y - 1, franchise_ids, [metric_key])
        same_last_year = sum((same_last_year_rows.get(fid, {}).get(metric_key, Decimal('0')) for fid in franchise_ids), Decimal('0'))
        projected = actual
        if actual <= 0:
            projected = safe_average([previous, same_last_year, target])
        elif target > 0 and actual < target:
            projected = safe_average([actual, target, previous if previous > 0 else actual])
        series.append({
            'label': f"{MONTH_NAME.get(m, m)[:3]} {y}",
            'actual': float(round_money(actual)),
            'target': float(round_money(target)),
            'forecast': float(round_money(projected)),
            'forecast_percent': float(percent(projected, target)),
        })
    return series


def aggregate_growth_trend_series(franchise_ids, metric_key, end_month, end_year, periods=12):
    franchise_ids = filter_active_franchise_ids(franchise_ids or [])
    series = []
    for m, y in _series_periods(end_month, end_year, periods):
        current_rows = period_actuals(m, y, franchise_ids, [metric_key])
        last_year_rows = period_actuals(m, y - 1, franchise_ids, [metric_key])
        prev_m, prev_y = previous_month(m, y)
        previous_rows = period_actuals(prev_m, prev_y, franchise_ids, [metric_key])
        actual = sum((current_rows.get(fid, {}).get(metric_key, Decimal('0')) for fid in franchise_ids), Decimal('0'))
        last_year = sum((last_year_rows.get(fid, {}).get(metric_key, Decimal('0')) for fid in franchise_ids), Decimal('0'))
        previous = sum((previous_rows.get(fid, {}).get(metric_key, Decimal('0')) for fid in franchise_ids), Decimal('0'))
        baseline = last_year if last_year > 0 else previous
        series.append({'label': f"{MONTH_NAME.get(m, m)[:3]} {y}", 'growth_percent': float(growth_rate(actual, baseline))})
    return series


def graph_engine_payload_for_franchises(franchise_ids, metric_key, month, year, periods=12, mode='growth_bracket', growth_percent=DEFAULT_GROWTH_PERCENT):
    franchise_ids = filter_active_franchise_ids(franchise_ids or [])
    return {
        'metric_key': metric_key,
        'metric_label': PERFORMANCE_METRICS[metric_key]['label'],
        'actual_vs_target': aggregate_trend_series(franchise_ids, metric_key, month, year, periods, mode, growth_percent),
        'previous_year': aggregate_previous_year_series(franchise_ids, metric_key, month, year, periods),
        'rolling_12': aggregate_rolling_12_series(franchise_ids, metric_key, month, year, periods),
        'forecast': aggregate_forecast_series(franchise_ids, metric_key, month, year, periods, mode, growth_percent),
        'growth_trend': aggregate_growth_trend_series(franchise_ids, metric_key, month, year, periods),
    }

def graph_engine_payload(franchise_id, metric_key, month, year, periods=12, mode='growth_bracket', growth_percent=DEFAULT_GROWTH_PERCENT):
    actual_target = trend_series(franchise_id, metric_key, month, year, periods, mode, growth_percent)
    return {
        'metric_key': metric_key,
        'metric_label': PERFORMANCE_METRICS[metric_key]['label'],
        'actual_vs_target': actual_target,
        'previous_year': previous_year_series(franchise_id, metric_key, month, year, periods),
        'rolling_12': rolling_12_series(franchise_id, metric_key, month, year, periods),
        'forecast': forecast_series(franchise_id, metric_key, month, year, periods, mode, growth_percent),
        'growth_trend': growth_trend_series(franchise_id, metric_key, month, year, periods),
    }

# Phase 7: Leaderboard decision centre helpers

def movement_text(row):
    delta = abs(int(row.get('movement_delta') or 0))
    movement = row.get('movement') or 'same'
    if movement == 'up' and delta:
        return f"Up by {delta}"
    if movement == 'down' and delta:
        return f"Down by {delta}"
    return 'Same'


def _ytd_metric_rows(metric_key, month, year, franchise_ids, mode='growth_bracket', growth_percent=DEFAULT_GROWTH_PERCENT):
    """Rank franchises by year-to-date actuals against accumulated current-year targets."""
    franchise_ids = filter_active_franchise_ids(franchise_ids)
    franchises = {item.id: item for item in Franchise.query.filter(Franchise.id.in_(franchise_ids)).all()} if franchise_ids else {}
    actual_totals = {fid: Decimal('0') for fid in franchise_ids}
    target_totals = {fid: Decimal('0') for fid in franchise_ids}
    for period_month in range(1, int(month) + 1):
        actuals = period_actuals(period_month, year, franchise_ids, [metric_key])
        targets = targets_for_period(period_month, year, franchise_ids, mode, growth_percent, [metric_key])
        for fid in franchise_ids:
            actual_totals[fid] += actuals.get(fid, {}).get(metric_key, Decimal('0'))
            target_totals[fid] += targets.get(fid, {}).get(metric_key, Decimal('0'))

    rows = []
    for fid in franchise_ids:
        actual = actual_totals.get(fid, Decimal('0'))
        target = target_totals.get(fid, Decimal('0'))
        score = percent(actual, target) if target > 0 else Decimal('0')
        rows.append({
            'franchise_id': fid,
            'franchise_name': franchises.get(fid).business_name if franchises.get(fid) else f'Franchise {fid}',
            'actual': round_money(actual),
            'target': round_money(target),
            'achievement_percent': score,
            'score': score,
        })
    rows.sort(key=lambda item: (item['score'], item['actual']), reverse=True)
    for index, row in enumerate(rows, 1):
        row['rank'] = index
    return rows


def leaderboard_rows(metric_key, month, year, franchise_ids, mode='growth_bracket', growth_percent=DEFAULT_GROWTH_PERCENT):
    """Return leaderboard rows ranked on YTD actuals vs accumulated current-year targets."""
    if metric_key != 'overall' and metric_key not in PERFORMANCE_METRICS:
        metric_key = 'overall'
    if metric_key == 'overall':
        return ranked_performance(month, year, franchise_ids, mode, growth_percent, metric_key)
    prev_m, prev_y = previous_month(month, year)
    current_rows = _ytd_metric_rows(metric_key, month, year, franchise_ids, mode, growth_percent)
    previous_rows = _ytd_metric_rows(metric_key, prev_m, prev_y, franchise_ids, mode, growth_percent)
    rows = attach_movement(current_rows, previous_rows)
    rows.sort(key=lambda item: item['rank'])
    for row in rows:
        row['movement_text'] = movement_text(row)
        if row.get('movement') == 'up':
            row['decision_label'] = 'Improving'
        elif row.get('movement') == 'down':
            row['decision_label'] = 'Needs attention'
        else:
            row['decision_label'] = 'Stable'
    return rows


def leaderboard_decision_centre(month, year, franchise_ids, mode='growth_bracket', growth_percent=DEFAULT_GROWTH_PERCENT):
    """Build overall and KPI-specific leaderboards for Phase 7."""
    boards = []
    board_keys = [('overall', {'label': 'Overall Performance'})] + list(PERFORMANCE_METRICS.items())
    for key, config in board_keys:
        rows = leaderboard_rows(key, month, year, franchise_ids, mode, growth_percent)
        climbers = [row for row in rows if row.get('movement') == 'up']
        climbers.sort(key=lambda row: abs(row.get('movement_delta') or 0), reverse=True)
        droppers = [row for row in rows if row.get('movement') == 'down']
        droppers.sort(key=lambda row: abs(row.get('movement_delta') or 0), reverse=True)
        boards.append({
            'key': key,
            'label': config.get('label', 'Overall Performance') if isinstance(config, dict) else str(config),
            'rows': rows,
            'top_10': rows[:10],
            'bottom_10': rows[-10:] if len(rows) > 10 else rows[-5:],
            'biggest_climbers': climbers[:5],
            'biggest_droppers': droppers[:5],
        })
    return boards


# Phase 8: Executive dashboard helpers

def executive_dashboard(month, year, franchise_ids, mode='growth_bracket', growth_percent=DEFAULT_GROWTH_PERCENT):
    """Head Office executive view across all accessible franchises.

    This keeps figures available for internal calculations, but presents decision
    items clearly: top performers, lowest performers, growth, decline, forecast
    risk and branch health.
    """
    overall_rows = leaderboard_rows('overall', month, year, franchise_ids, mode, growth_percent)
    kpi_summaries = []
    for metric_key, metric in PERFORMANCE_METRICS.items():
        summary = metric_page_summary(metric_key, month, year, franchise_ids, mode, growth_percent)
        kpi_summaries.append({
            'key': metric_key,
            'label': metric['label'],
            'format': metric['format'],
            'total_actual': summary['total_actual'],
            'total_target': summary['total_target'],
            'target_percent': summary['target_percent'],
            'previous_month_growth': summary['previous_month_growth'],
            'last_year_growth': summary['last_year_growth'],
            'status': summary['status'],
            'top_rows': summary['top_rows'][:5],
            'bottom_rows': summary['bottom_rows'][:5],
        })

    branch_health = []
    for row in overall_rows:
        metrics = franchise_metric_summary(row['franchise_id'], month, year, mode, growth_percent)
        health = health_score_from_metrics(metrics)
        below_target = [item for item in metrics if to_decimal(item.get('target_percent')) < Decimal('90')]
        branch_health.append({
            'franchise_id': row['franchise_id'],
            'franchise_name': row['franchise_name'],
            'rank': row['rank'],
            'movement': row.get('movement'),
            'movement_text': row.get('movement_text') or movement_text(row),
            'health_score': health,
            'health_label': health_label(health),
            'below_target_count': len(below_target),
            'below_target_labels': ', '.join(item['label'] for item in below_target[:3]),
            'score': row.get('score'),
        })

    branch_health.sort(key=lambda item: item['health_score'], reverse=True)
    needs_attention = sorted(branch_health, key=lambda item: (item['health_score'], -item['below_target_count']))[:10]

    biggest_climbers = [row for row in overall_rows if row.get('movement') == 'up']
    biggest_climbers.sort(key=lambda row: abs(row.get('movement_delta') or 0), reverse=True)
    biggest_droppers = [row for row in overall_rows if row.get('movement') == 'down']
    biggest_droppers.sort(key=lambda row: abs(row.get('movement_delta') or 0), reverse=True)

    forecast_risk = []
    for metric in kpi_summaries:
        for row in metric['bottom_rows']:
            if to_decimal(row.get('achievement')) < Decimal('90'):
                forecast_risk.append({
                    'metric_key': metric['key'],
                    'metric_label': metric['label'],
                    'franchise_id': row['franchise_id'],
                    'franchise_name': row['franchise_name'],
                    'rank': row['rank'],
                    'achievement': row.get('achievement'),
                    'movement': row.get('movement'),
                    'movement_text': row.get('movement_text') or movement_text(row),
                })
    forecast_risk.sort(key=lambda item: to_decimal(item['achievement']))

    return {
        'period_label': month_label(month, year),
        'overall_rows': overall_rows,
        'top_performers': overall_rows[:10],
        'lowest_performers': overall_rows[-10:] if len(overall_rows) > 10 else overall_rows[-5:],
        'biggest_climbers': biggest_climbers[:10],
        'biggest_droppers': biggest_droppers[:10],
        'kpi_summaries': kpi_summaries,
        'branch_health': branch_health[:10],
        'needs_attention': needs_attention,
        'forecast_risk': forecast_risk[:15],
        'total_franchises': len(overall_rows),
    }


# Phase 9: Performance intelligence insights

def _insight_severity(status):
    if status in ('critical', 'danger'):
        return 'danger'
    if status in ('warning', 'watch'):
        return 'warning'
    return 'good'


def consecutive_metric_direction(franchise_id, metric_key, month, year, mode='growth_bracket', growth_percent=DEFAULT_GROWTH_PERCENT, periods=6):
    """Return consecutive improvement/decline streak for a metric based on actual values."""
    series = trend_series(franchise_id, metric_key, month, year, periods, mode, growth_percent)
    if len(series) < 2:
        return {'direction': 'same', 'count': 0}
    values = [to_decimal(item.get('actual')) for item in series]
    direction = 'same'
    count = 0
    for idx in range(len(values) - 1, 0, -1):
        current = values[idx]
        previous = values[idx - 1]
        if current > previous:
            step = 'up'
        elif current < previous:
            step = 'down'
        else:
            step = 'same'
        if direction == 'same':
            direction = step
            count = 1 if step != 'same' else 0
        elif step == direction:
            count += 1
        else:
            break
    return {'direction': direction, 'count': count}


def record_month_check(franchise_id, metric_key, month, year, lookback=36):
    current = actual_value(franchise_id, metric_key, month, year)
    if current <= 0:
        return False
    values = []
    current_m, current_y = month, year
    for _ in range(lookback):
        current_m, current_y = previous_month(current_m, current_y)
        value = actual_value(franchise_id, metric_key, current_m, current_y)
        if value > 0:
            values.append(value)
    return bool(values) and current >= max(values)


def franchise_insights(franchise_id, month, year, mode='growth_bracket', growth_percent=DEFAULT_GROWTH_PERCENT):
    """Build user-friendly decision insights for one franchise."""
    franchise = Franchise.query.get(franchise_id)
    rows = franchise_metric_summary(franchise_id, month, year, mode, growth_percent)
    insights = []
    for row in rows:
        metric_key = row['metric_key']
        label = row['label']
        actual = to_decimal(row.get('actual'))
        target = to_decimal(row.get('target'))
        target_percent = to_decimal(row.get('target_percent'))
        prev_growth = to_decimal(row.get('previous_month_growth'))
        year_growth = to_decimal(row.get('last_year_growth'))
        streak = consecutive_metric_direction(franchise_id, metric_key, month, year, mode, growth_percent)
        if target > 0 and target_percent < Decimal('80'):
            insights.append({
                'severity': 'danger',
                'metric_key': metric_key,
                'metric_label': label,
                'title': f'{label} is far below target',
                'message': f'{label} is at {target_percent}% of target for {month_label(month, year)}. Review activity urgently and compare with the previous three months.',
                'action': 'Immediate support required',
            })
        elif target > 0 and target_percent < Decimal('95'):
            insights.append({
                'severity': 'warning',
                'metric_key': metric_key,
                'metric_label': label,
                'title': f'{label} is close but below target',
                'message': f'{label} is at {target_percent}% of target. A focused push before month-end can still close the gap.',
                'action': 'Monitor weekly',
            })
        elif target > 0 and target_percent >= Decimal('110'):
            insights.append({
                'severity': 'good',
                'metric_key': metric_key,
                'metric_label': label,
                'title': f'{label} is ahead of target',
                'message': f'{label} is at {target_percent}% of target. Capture what worked so it can be repeated next month.',
                'action': 'Recognise and repeat',
            })
        if prev_growth <= Decimal('-10'):
            insights.append({
                'severity': 'warning',
                'metric_key': metric_key,
                'metric_label': label,
                'title': f'{label} dropped versus last month',
                'message': f'{label} is {abs(prev_growth)}% down from the previous month.',
                'action': 'Check month-on-month causes',
            })
        if year_growth <= Decimal('-10'):
            insights.append({
                'severity': 'danger',
                'metric_key': metric_key,
                'metric_label': label,
                'title': f'{label} is down versus last year',
                'message': f'{label} is {abs(year_growth)}% lower than the same month last year.',
                'action': 'Investigate annual decline',
            })
        if streak['direction'] == 'down' and streak['count'] >= 3:
            insights.append({
                'severity': 'danger',
                'metric_key': metric_key,
                'metric_label': label,
                'title': f'{label} has declined for {streak["count"]} months',
                'message': f'{label} shows a consecutive downward trend. This is a branch health risk.',
                'action': 'Schedule branch support',
            })
        if streak['direction'] == 'up' and streak['count'] >= 3:
            insights.append({
                'severity': 'good',
                'metric_key': metric_key,
                'metric_label': label,
                'title': f'{label} has improved for {streak["count"]} months',
                'message': f'{label} is building momentum over consecutive months.',
                'action': 'Keep current strategy',
            })
        if record_month_check(franchise_id, metric_key, month, year):
            insights.append({
                'severity': 'good',
                'metric_key': metric_key,
                'metric_label': label,
                'title': f'Record month for {label}',
                'message': f'{franchise.business_name if franchise else "This franchise"} produced its strongest {label} result in the recent history window.',
                'action': 'Celebrate and document process',
            })
    priority = {'danger': 0, 'warning': 1, 'good': 2}
    insights.sort(key=lambda item: (priority.get(item['severity'], 9), item['metric_label']))
    return insights[:25]


def executive_insights(month, year, franchise_ids, mode='growth_bracket', growth_percent=DEFAULT_GROWTH_PERCENT):
    """Build Head Office insights across all accessible franchises."""
    insights = []
    executive = executive_dashboard(month, year, franchise_ids, mode, growth_percent)
    for item in executive.get('forecast_risk', [])[:10]:
        insights.append({
            'severity': 'danger' if to_decimal(item.get('achievement')) < Decimal('80') else 'warning',
            'franchise_id': item['franchise_id'],
            'franchise_name': item['franchise_name'],
            'metric_label': item['metric_label'],
            'title': f'{item["franchise_name"]}: {item["metric_label"]} target risk',
            'message': f'{item["metric_label"]} is only at {item["achievement"]}% achievement and ranked #{item["rank"]}.',
            'action': 'Review with franchise owner',
        })
    for row in executive.get('biggest_droppers', [])[:5]:
        insights.append({
            'severity': 'warning',
            'franchise_id': row['franchise_id'],
            'franchise_name': row['franchise_name'],
            'metric_label': 'Overall',
            'title': f'{row["franchise_name"]} dropped on the leaderboard',
            'message': f'Current rank is #{row["rank"]}; movement shows {row.get("movement_text", "Down")}.',
            'action': 'Compare KPI detail',
        })
    for row in executive.get('biggest_climbers', [])[:5]:
        insights.append({
            'severity': 'good',
            'franchise_id': row['franchise_id'],
            'franchise_name': row['franchise_name'],
            'metric_label': 'Overall',
            'title': f'{row["franchise_name"]} is improving',
            'message': f'Current rank is #{row["rank"]}; movement shows {row.get("movement_text", "Up")}.',
            'action': 'Recognise improvement',
        })
    for summary in executive.get('kpi_summaries', []):
        if to_decimal(summary.get('target_percent')) < Decimal('90'):
            insights.append({
                'severity': 'warning',
                'franchise_id': None,
                'franchise_name': 'Group',
                'metric_label': summary['label'],
                'title': f'Group {summary["label"]} is below target',
                'message': f'Group achievement is {summary["target_percent"]}% for {month_label(month, year)}.',
                'action': 'Prioritise this KPI nationally',
            })
    priority = {'danger': 0, 'warning': 1, 'good': 2}
    insights.sort(key=lambda item: (priority.get(item['severity'], 9), item.get('franchise_name') or ''))
    return {
        'period_label': month_label(month, year),
        'items': insights[:30],
        'counts': {
            'danger': sum(1 for item in insights if item['severity'] == 'danger'),
            'warning': sum(1 for item in insights if item['severity'] == 'warning'),
            'good': sum(1 for item in insights if item['severity'] == 'good'),
        },
    }


# Phase 10: Decision Centre

def _decision_priority(item):
    order = {'danger': 0, 'warning': 1, 'good': 2}
    return order.get(item.get('severity'), 9)


def decision_centre(month, year, franchise_ids, mode='growth_bracket', growth_percent=DEFAULT_GROWTH_PERCENT):
    """Combine executive KPIs, leaderboards, health and insights into one action centre.

    Phase 10 is intentionally a read-only decision layer. It does not create new
    tables; it reuses the Phase 1-9 engine so Head Office has one place to see
    what needs action after every monthly PDF/import cycle.
    """
    executive = executive_dashboard(month, year, franchise_ids, mode, growth_percent)
    insights = executive_insights(month, year, franchise_ids, mode, growth_percent)
    boards = leaderboard_decision_centre(month, year, franchise_ids, mode, growth_percent)

    urgent_actions = []
    for item in insights.get('items', []):
        if item.get('severity') in ('danger', 'warning'):
            urgent_actions.append({
                'severity': item.get('severity'),
                'franchise_id': item.get('franchise_id'),
                'franchise_name': item.get('franchise_name') or 'Group',
                'metric_label': item.get('metric_label') or 'Overall',
                'title': item.get('title'),
                'message': item.get('message'),
                'action': item.get('action') or 'Review',
            })

    watchlist = []
    for row in executive.get('needs_attention', [])[:15]:
        status = 'danger' if to_decimal(row.get('health_score')) < Decimal('75') else 'warning'
        watchlist.append({
            'severity': status,
            'franchise_id': row['franchise_id'],
            'franchise_name': row['franchise_name'],
            'rank': row.get('rank'),
            'health_score': row.get('health_score'),
            'health_label': row.get('health_label'),
            'below_target_count': row.get('below_target_count'),
            'below_target_labels': row.get('below_target_labels'),
        })

    wins = []
    for row in executive.get('biggest_climbers', [])[:5]:
        wins.append({
            'type': 'Movement',
            'franchise_id': row['franchise_id'],
            'franchise_name': row['franchise_name'],
            'title': f"{row['franchise_name']} moved up",
            'message': row.get('movement_text') or 'Up',
        })
    for row in executive.get('top_performers', [])[:5]:
        wins.append({
            'type': 'Performance',
            'franchise_id': row['franchise_id'],
            'franchise_name': row['franchise_name'],
            'title': f"#{row.get('rank')} {row['franchise_name']}",
            'message': f"Overall score {row.get('score')}%",
        })

    kpi_focus = []
    for summary in executive.get('kpi_summaries', []):
        target_percent = to_decimal(summary.get('target_percent'))
        if target_percent < Decimal('90'):
            decision = 'Immediate attention'
        elif target_percent < Decimal('100'):
            decision = 'Watch closely'
        else:
            decision = 'On track'
        kpi_focus.append({
            'key': summary['key'],
            'label': summary['label'],
            'status': summary['status'],
            'target_percent': summary['target_percent'],
            'previous_month_growth': summary['previous_month_growth'],
            'last_year_growth': summary['last_year_growth'],
            'decision': decision,
        })

    urgent_actions.sort(key=_decision_priority)
    watchlist.sort(key=lambda item: to_decimal(item.get('health_score')))

    return {
        'period_label': month_label(month, year),
        'executive': executive,
        'leaderboards': boards,
        'insights': insights,
        'urgent_actions': urgent_actions[:20],
        'watchlist': watchlist[:15],
        'wins': wins[:10],
        'kpi_focus': kpi_focus,
        'counts': {
            'urgent': len([item for item in urgent_actions if item.get('severity') == 'danger']),
            'watch': len([item for item in urgent_actions if item.get('severity') == 'warning']),
            'wins': len(wins),
            'franchises': executive.get('total_franchises', 0),
        },
    }


def capture_performance_history(month, year, franchise_ids, mode="growth_bracket", growth=DEFAULT_GROWTH_PERCENT, captured_by_id=None):
    """Freeze the current period into performance_snapshots.

    Snapshots are created from the same calculation engine used by the live
    dashboard, but once saved they become the historical record.  Re-running the
    capture updates the same period/metric rows rather than duplicating them.
    """
    rows_by_metric = {}
    overall_rows = attach_movement(
        ranked_performance(month, year, franchise_ids, mode, growth, "overall"),
        ranked_performance(*previous_month(month, year), franchise_ids, mode, growth, "overall"),
    )
    overall_lookup = {row["franchise_id"]: row for row in overall_rows}

    for metric_key in PERFORMANCE_METRICS:
        rows_by_metric[metric_key] = attach_movement(
            ranked_performance(month, year, franchise_ids, mode, growth, metric_key),
            ranked_performance(*previous_month(month, year), franchise_ids, mode, growth, metric_key),
        )

    saved = 0
    for metric_key, rows in rows_by_metric.items():
        for row in rows:
            franchise_id = row["franchise_id"]
            snapshot = PerformanceSnapshot.query.filter_by(
                franchise_id=franchise_id,
                metric=metric_key,
                year=year,
                month=month,
            ).first()
            if not snapshot:
                snapshot = PerformanceSnapshot(franchise_id=franchise_id, metric=metric_key, year=year, month=month)
                db.session.add(snapshot)
            overall = overall_lookup.get(franchise_id, {})
            snapshot.actual_value = row.get("actual", 0) or 0
            snapshot.target_value = row.get("target", 0) or 0
            snapshot.achievement_percent = row.get("achievement", 0) or 0
            snapshot.growth_percent = row.get("growth", 0) or 0
            snapshot.forecast_value = row.get("forecast", 0) or 0
            snapshot.rank = row.get("rank", 0) or 0
            snapshot.previous_rank = row.get("previous_rank", 0) or 0
            snapshot.movement = row.get("movement", 0) or 0
            snapshot.health_score = overall.get("score", row.get("score", 0)) or 0
            snapshot.source = "performance_results"
            snapshot.captured_by_id = captured_by_id
            saved += 1
    db.session.commit()
    return saved


def performance_history_periods(franchise_ids):
    if not franchise_ids:
        return []
    rows = (
        db.session.query(PerformanceSnapshot.year, PerformanceSnapshot.month)
        .filter(PerformanceSnapshot.franchise_id.in_(franchise_ids))
        .group_by(PerformanceSnapshot.year, PerformanceSnapshot.month)
        .order_by(PerformanceSnapshot.year.desc(), PerformanceSnapshot.month.desc())
        .all()
    )
    return [{"year": year, "month": month, "label": month_label(month, year)} for year, month in rows]


def performance_history(franchise_id, month=None, year=None):
    query = PerformanceSnapshot.query.filter_by(franchise_id=franchise_id)
    if month and year:
        query = query.filter_by(month=month, year=year)
    rows = query.order_by(
        PerformanceSnapshot.year.desc(),
        PerformanceSnapshot.month.desc(),
        PerformanceSnapshot.metric.asc(),
    ).all()
    grouped = {}
    for row in rows:
        key = (row.year, row.month)
        grouped.setdefault(key, {
            "year": row.year,
            "month": row.month,
            "label": month_label(row.month, row.year),
            "metrics": [],
            "health_score": row.health_score,
            "rank": row.rank,
            "movement": row.movement,
            "captured_at": row.captured_at,
        })
        grouped[key]["metrics"].append({
            "metric": row.metric,
            "label": PERFORMANCE_METRICS.get(row.metric, {}).get("label", row.metric),
            "actual": row.actual_value,
            "target": row.target_value,
            "achievement": row.achievement_percent,
            "growth": row.growth_percent,
            "forecast": row.forecast_value,
            "rank": row.rank,
            "previous_rank": row.previous_rank,
            "movement": row.movement,
        })
    return list(grouped.values())


def user_access_summary(user):
    """Return the user's visible modules and franchise scope for admin review."""
    modules = [
        ("Dashboard", "dashboard:view"),
        ("Performance", "performance:view"),
        ("Manage Targets", "performance:manage_targets"),
        ("Monthly Figures", "monthly:view"),
        ("Royalties", "royalties:view"),
        ("Claims", "claims:view"),
        ("Attendance", "attendance:view"),
        ("Heat Map", "heatmap:view"),
        ("Manuals", "manuals:view"),
        ("Users", "users:manage"),
        ("Franchise Management", "franchise_management:view"),
    ]
    visible_modules = [label for label, code in modules if user.has_permission(code)]
    franchises = user.accessible_franchises()
    return {
        "user": user,
        "visible_modules": visible_modules,
        "franchises": franchises,
        "scope_label": "All franchises" if user.has_permission("franchise_management:view") or user.has_permission("franchise_management:manage") else f"{len(franchises)} assigned franchise(s)",
    }
