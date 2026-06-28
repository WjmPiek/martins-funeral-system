from decimal import Decimal
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.audit import log_action
from app.extensions import db
from app.franchise_context import get_accessible_franchises, get_selected_franchise, is_privileged_user
from app.models import Franchise, FranchiseTarget
from app.performance.service import (
    DEFAULT_GROWTH_PERCENT,
    MONTHS,
    PERFORMANCE_METRICS,
    TARGET_MODES,
    accessible_franchise_ids,
    attach_movement,
    dashboard_snapshot,
    franchise_metric_summary,
    month_label,
    previous_month,
    ranked_performance,
    reporting_years,
    selected_period_from_request,
    stored_targets,
    targets_for_period,
    to_decimal,
    trend_series,
)

performance_bp = Blueprint("performance", __name__, url_prefix="/performance")


def permission_required(code):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.has_permission(code):
                abort(403)
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def request_mode():
    mode = request.args.get("target_mode", "manual")
    return mode if mode in TARGET_MODES else "manual"


def request_growth():
    try:
        return Decimal(str(request.args.get("growth", DEFAULT_GROWTH_PERCENT)))
    except Exception:
        return DEFAULT_GROWTH_PERCENT


@performance_bp.route("/")
@login_required
@permission_required("performance:view")
def index():
    month, year = selected_period_from_request(request.args)
    mode = request_mode()
    growth = request_growth()
    metric_key = request.args.get("metric", "overall")
    if metric_key != "overall" and metric_key not in PERFORMANCE_METRICS:
        metric_key = "overall"
    ids = accessible_franchise_ids()
    previous_m, previous_y = previous_month(month, year)
    rows = attach_movement(
        ranked_performance(month, year, ids, mode, growth, metric_key),
        ranked_performance(previous_m, previous_y, ids, mode, growth, metric_key),
    )
    selected = get_selected_franchise()
    my_row = None
    if selected:
        my_row = next((row for row in rows if row["franchise_id"] == selected.id), None)
    elif not is_privileged_user() and rows:
        my_row = rows[0]
    return render_template(
        "performance/index.html",
        rows=rows,
        my_row=my_row,
        metrics=PERFORMANCE_METRICS,
        metric_key=metric_key,
        target_modes=TARGET_MODES,
        target_mode=mode,
        growth=growth,
        month_options=MONTHS,
        year_options=reporting_years(),
        selected_month=month,
        selected_year=year,
        selected_period_label=month_label(month, year),
        show_manage_targets=current_user.has_permission("performance:manage_targets"),
    )


@performance_bp.route("/franchise/<int:franchise_id>")
@login_required
@permission_required("performance:view")
def franchise(franchise_id):
    if franchise_id not in accessible_franchise_ids():
        abort(403)
    month, year = selected_period_from_request(request.args)
    mode = request_mode()
    growth = request_growth()
    franchise = Franchise.query.get_or_404(franchise_id)
    metric_rows = franchise_metric_summary(franchise_id, month, year, mode, growth)
    chart_metric = request.args.get("chart_metric", "cash")
    if chart_metric not in PERFORMANCE_METRICS:
        chart_metric = "cash"
    chart_data = trend_series(franchise_id, chart_metric, month, year, 12, mode, growth)
    snapshot = dashboard_snapshot(franchise_id, month, year, mode, growth)
    return render_template(
        "performance/franchise.html",
        franchise=franchise,
        metric_rows=metric_rows,
        chart_metric=chart_metric,
        chart_data=chart_data,
        metrics=PERFORMANCE_METRICS,
        snapshot=snapshot,
        target_modes=TARGET_MODES,
        target_mode=mode,
        growth=growth,
        month_options=MONTHS,
        year_options=reporting_years(),
        selected_month=month,
        selected_year=year,
        selected_period_label=month_label(month, year),
    )


@performance_bp.route("/targets", methods=["GET", "POST"])
@login_required
@permission_required("performance:manage_targets")
def targets():
    month, year = selected_period_from_request(request.args)
    ids = accessible_franchise_ids()
    franchises = Franchise.query.filter(Franchise.id.in_(ids)).order_by(Franchise.business_name.asc()).all() if ids else []
    if request.method == "POST":
        saved = 0
        for franchise in franchises:
            for metric_key in PERFORMANCE_METRICS:
                field = f"target_{franchise.id}_{metric_key}"
                raw_value = (request.form.get(field) or "0").replace("R", "").replace(",", "").strip()
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
        log_action("Performance", "Updated performance targets", f"Targets saved: {saved}; Period: {month_label(month, year)}")
        db.session.commit()
        flash("Performance targets saved.", "success")
        return redirect(url_for("performance.targets", month=month, year=year))
    values = stored_targets(month, year, ids)
    auto_values = targets_for_period(month, year, ids, "previous_year_growth", DEFAULT_GROWTH_PERCENT)
    return render_template(
        "performance/targets.html",
        franchises=franchises,
        target_values=values,
        auto_values=auto_values,
        metrics=PERFORMANCE_METRICS,
        month_options=MONTHS,
        year_options=reporting_years(),
        selected_month=month,
        selected_year=year,
        selected_period_label=month_label(month, year),
    )
