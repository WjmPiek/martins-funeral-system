from datetime import datetime
from decimal import Decimal
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app.audit import log_action
from app.extensions import db
from app.franchise_context import get_accessible_franchises, get_selected_franchise, is_franchise_view_mode, is_privileged_user
from app.models import Franchise, FranchiseTarget, MonthlyFigure

leaderboard_bp = Blueprint("leaderboard", __name__, url_prefix="/leaderboard")

MONTHS = [
    (1, "January"), (2, "February"), (3, "March"), (4, "April"),
    (5, "May"), (6, "June"), (7, "July"), (8, "August"),
    (9, "September"), (10, "October"), (11, "November"), (12, "December"),
]

METRICS = {
    "gross_turnover": {"label": "Gross Turnover", "field": MonthlyFigure.gross_turnover, "format": "money", "weight": Decimal("0.40")},
    "sales": {"label": "Sales", "field": MonthlyFigure.sales, "format": "money", "weight": Decimal("0.20")},
    "insurance_joinings": {"label": "Insurance Joinings", "field": MonthlyFigure.insurance_joinings, "format": "number", "weight": Decimal("0.15")},
    "mf_files": {"label": "MF Files", "field": MonthlyFigure.mf_files, "format": "number", "weight": Decimal("0.10")},
    "royalty_amount": {"label": "Royalty Amount", "field": MonthlyFigure.royalty_amount, "format": "money", "weight": Decimal("0.15")},
}


def permission_required(code):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.has_permission(code):
                abort(403)
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def selected_period():
    now = datetime.now()
    try:
        month = int(request.args.get("month", now.month))
    except (TypeError, ValueError):
        month = now.month
    try:
        year = int(request.args.get("year", now.year))
    except (TypeError, ValueError):
        year = now.year
    if month < 1 or month > 12:
        month = now.month
    if year < 2000 or year > 2100:
        year = now.year
    return month, year


def previous_month(month, year):
    if month == 1:
        return 12, year - 1
    return month - 1, year


def comparison_period(month, year, compare_to):
    if compare_to == "same_month_last_year":
        return month, year - 1
    return previous_month(month, year)


def month_label(month, year):
    return f"{dict(MONTHS).get(month, month)} {year}"


def reporting_years():
    current_year = datetime.now().year
    years = [row[0] for row in db.session.query(MonthlyFigure.year).distinct().order_by(MonthlyFigure.year.desc()).all()]
    if current_year not in years:
        years.insert(0, current_year)
    return years


def accessible_franchise_ids():
    """Return the leaderboard ranking scope.

    The leaderboard is a company-wide comparison: franchise users must see all
    active franchise users and have their own franchise highlighted. This does
    not change detailed franchise access elsewhere in the system.
    """
    return [
        franchise.id
        for franchise in Franchise.query.filter(Franchise.is_performance_active == True)
        .order_by(Franchise.business_name)
        .all()
    ]


def money_to_decimal(value):
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def query_metric_totals(month, year, franchise_ids):
    if not franchise_ids:
        return {}
    columns = [MonthlyFigure.franchise_id]
    for metric_key, config in METRICS.items():
        columns.append(func.coalesce(func.sum(config["field"]), 0).label(metric_key))
    rows = (
        db.session.query(*columns)
        .filter(MonthlyFigure.month == month, MonthlyFigure.year == year)
        .filter(MonthlyFigure.franchise_id.in_(franchise_ids))
        .group_by(MonthlyFigure.franchise_id)
        .all()
    )
    totals = {}
    for row in rows:
        item = {metric_key: money_to_decimal(getattr(row, metric_key)) for metric_key in METRICS}
        totals[row.franchise_id] = item
    return totals


def query_targets(month, year, franchise_ids):
    if not franchise_ids:
        return {}
    rows = FranchiseTarget.query.filter(
        FranchiseTarget.franchise_id.in_(franchise_ids),
        FranchiseTarget.year == year,
        FranchiseTarget.month == month,
    ).all()
    targets = {}
    for row in rows:
        targets.setdefault(row.franchise_id, {})[row.metric] = money_to_decimal(row.target_value)
    return targets


def target_ratio(actual, target):
    actual = money_to_decimal(actual)
    target = money_to_decimal(target)
    if target <= 0:
        return Decimal("0")
    return (actual / target) * Decimal("100")


def weighted_score(actuals, targets):
    score = Decimal("0")
    has_target = False
    for metric_key, config in METRICS.items():
        target = targets.get(metric_key, Decimal("0"))
        actual = actuals.get(metric_key, Decimal("0"))
        if target > 0:
            has_target = True
            # Cap each metric at 150% so one exceptional number does not hide weak areas.
            capped = min(target_ratio(actual, target), Decimal("150"))
            score += capped * config["weight"]
    if has_target:
        return score
    # Fallback while targets are still being captured: rank from gross turnover.
    return actuals.get("gross_turnover", Decimal("0"))


def build_rankings(month, year, franchise_ids):
    franchises = Franchise.query.filter(Franchise.id.in_(franchise_ids)).order_by(Franchise.business_name.asc()).all() if franchise_ids else []
    actuals = query_metric_totals(month, year, franchise_ids)
    targets = query_targets(month, year, franchise_ids)
    rows = []
    for franchise in franchises:
        franchise_actuals = actuals.get(franchise.id, {metric: Decimal("0") for metric in METRICS})
        franchise_targets = targets.get(franchise.id, {})
        score = weighted_score(franchise_actuals, franchise_targets)
        gross_target = franchise_targets.get("gross_turnover", Decimal("0"))
        rows.append({
            "franchise_id": franchise.id,
            "franchise_name": franchise.business_name or "Unnamed Franchise",
            "actuals": franchise_actuals,
            "targets": franchise_targets,
            "gross_target": gross_target,
            "gross_target_percent": target_ratio(franchise_actuals.get("gross_turnover", 0), gross_target),
            "score": score,
            "rank": 0,
        })
    rows.sort(key=lambda item: (item["score"], item["actuals"].get("gross_turnover", Decimal("0"))), reverse=True)
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def attach_rank_movement(current_rows, previous_rows):
    previous_rank_by_id = {row["franchise_id"]: row["rank"] for row in previous_rows}
    for row in current_rows:
        old_rank = previous_rank_by_id.get(row["franchise_id"])
        row["previous_rank"] = old_rank
        if old_rank is None:
            row["movement"] = "same"
            row["movement_label"] = "Same"
            row["movement_class"] = "same"
            row["movement_delta"] = 0
        else:
            delta = old_rank - row["rank"]
            row["movement_delta"] = delta
            if delta > 0:
                row["movement"] = "up"
                row["movement_label"] = "Up"
                row["movement_class"] = "up"
            elif delta < 0:
                row["movement"] = "down"
                row["movement_label"] = "Down"
                row["movement_class"] = "down"
            else:
                row["movement"] = "same"
                row["movement_label"] = "Same"
                row["movement_class"] = "same"
    return current_rows


def build_dashboard_leaderboard_snapshot(franchise_id, month=None, year=None):
    """Return one franchise's current leaderboard position for dashboard cards.

    This uses the same ranking logic as the main leaderboard, so the dashboard
    and leaderboard page always agree.
    """
    now = datetime.now()
    month = month or now.month
    year = year or now.year
    franchise_ids = accessible_franchise_ids()
    if franchise_id not in franchise_ids:
        return None
    prev_month, prev_year = previous_month(month, year)
    rows = attach_rank_movement(
        build_rankings(month, year, franchise_ids),
        build_rankings(prev_month, prev_year, franchise_ids),
    )
    my_row = next((row for row in rows if row["franchise_id"] == franchise_id), None)
    if not my_row:
        return None
    return {
        "rank": my_row["rank"],
        "total": len(rows),
        "franchise_name": my_row["franchise_name"],
        "movement_label": my_row["movement_label"],
        "movement_class": my_row["movement_class"],
        "movement_delta": my_row["movement_delta"],
        "score": my_row["score"],
        "gross_target_percent": my_row["gross_target_percent"],
        "period_label": month_label(month, year),
    }


@leaderboard_bp.route("/")
@login_required
@permission_required("leaderboard:view")
def index():
    month, year = selected_period()
    compare_to = request.args.get("compare_to", "previous_month")
    if compare_to not in {"previous_month", "same_month_last_year"}:
        compare_to = "previous_month"
    prev_month, prev_year = comparison_period(month, year, compare_to)
    franchise_ids = accessible_franchise_ids()
    current_rows = build_rankings(month, year, franchise_ids)
    previous_rows = build_rankings(prev_month, prev_year, franchise_ids)
    rows = attach_rank_movement(current_rows, previous_rows)
    selected_franchise = get_selected_franchise()
    my_row = None
    if selected_franchise:
        my_row = next((row for row in rows if row["franchise_id"] == selected_franchise.id), None)
    elif not is_privileged_user() and rows:
        my_row = rows[0]
    return render_template(
        "leaderboard/index.html",
        rows=rows,
        my_row=my_row,
        month_options=MONTHS,
        year_options=reporting_years(),
        selected_month=month,
        selected_year=year,
        selected_period_label=month_label(month, year),
        comparison_period_label=month_label(prev_month, prev_year),
        compare_to=compare_to,
        metrics=METRICS,
        show_manage_targets=current_user.has_permission("leaderboard:manage_targets"),
    )


@leaderboard_bp.route("/targets", methods=["GET", "POST"])
@login_required
@permission_required("leaderboard:manage_targets")
def targets():
    month, year = selected_period()
    franchise_ids = accessible_franchise_ids()
    franchises = Franchise.query.filter(Franchise.id.in_(franchise_ids)).order_by(Franchise.business_name.asc()).all() if franchise_ids else []

    if request.method == "POST":
        saved = 0
        for franchise in franchises:
            for metric_key in METRICS:
                field_name = f"target_{franchise.id}_{metric_key}"
                raw_value = (request.form.get(field_name) or "0").replace("R", "").replace(",", "").strip()
                try:
                    value = Decimal(raw_value or "0")
                except Exception:
                    value = Decimal("0")
                target = FranchiseTarget.query.filter_by(
                    franchise_id=franchise.id,
                    metric=metric_key,
                    year=year,
                    month=month,
                ).first()
                if not target:
                    target = FranchiseTarget(franchise_id=franchise.id, metric=metric_key, year=year, month=month)
                    db.session.add(target)
                target.target_value = value
                saved += 1
        log_action("Leaderboard", "Updated franchise targets", f"Targets saved: {saved}; Period: {month_label(month, year)}")
        db.session.commit()
        flash("Leaderboard targets saved.", "success")
        return redirect(url_for("leaderboard.targets", month=month, year=year))

    target_values = query_targets(month, year, franchise_ids)
    return render_template(
        "leaderboard/targets.html",
        franchises=franchises,
        target_values=target_values,
        metrics=METRICS,
        month_options=MONTHS,
        year_options=reporting_years(),
        selected_month=month,
        selected_year=year,
        selected_period_label=month_label(month, year),
    )
