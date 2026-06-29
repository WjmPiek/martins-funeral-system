from decimal import Decimal
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.audit import log_action
from app.extensions import db
from app.franchise_context import get_accessible_franchises, get_selected_franchise, is_privileged_user
from app.models import Franchise, FranchiseTarget, PerformanceGrowthBracket
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
    rebuild_performance_results,
    target_plan_for_period,
    save_growth_bracket_targets,
    annual_budget_plan_for_period,
    save_annual_budget_targets,
    franchise_dashboard,
    metric_page_summary,
    metric_trend_summary,
    graph_engine_payload,
    leaderboard_decision_centre,
    executive_dashboard,
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
    mode = request.args.get("target_mode", "growth_bracket")
    return mode if mode in TARGET_MODES else "manual"


def request_growth():
    try:
        return Decimal(str(request.args.get("growth", DEFAULT_GROWTH_PERCENT)))
    except Exception:
        return DEFAULT_GROWTH_PERCENT


@performance_bp.route("/dashboard")
@login_required
@permission_required("performance:view")
def dashboard():
    month, year = selected_period_from_request(request.args)
    mode = request_mode()
    growth = request_growth()
    ids = accessible_franchise_ids()
    selected = get_selected_franchise()
    franchise_id = selected.id if selected else (ids[0] if ids else None)
    if not franchise_id:
        flash("No franchise is available for your user access.", "warning")
        return redirect(url_for("performance.index", month=month, year=year))
    if franchise_id not in ids:
        abort(403)
    franchise = Franchise.query.get_or_404(franchise_id)
    dashboard_data = franchise_dashboard(franchise_id, month, year, mode, growth)
    return render_template(
        "performance/dashboard.html",
        franchise=franchise,
        dashboard=dashboard_data,
        metrics=PERFORMANCE_METRICS,
        target_modes=TARGET_MODES,
        target_mode=mode,
        growth=growth,
        month_options=MONTHS,
        year_options=reporting_years(),
        selected_month=month,
        selected_year=year,
        selected_period_label=month_label(month, year),
    )


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


@performance_bp.route("/kpi/<metric_key>")
@login_required
@permission_required("performance:view")
def kpi(metric_key):
    if metric_key not in PERFORMANCE_METRICS:
        abort(404)
    month, year = selected_period_from_request(request.args)
    mode = request_mode()
    growth = request_growth()
    ids = accessible_franchise_ids()
    summary = metric_page_summary(metric_key, month, year, ids, mode, growth)
    selected = get_selected_franchise()
    my_row = None
    chart_data = None
    if selected and selected.id in ids:
        my_row = next((row for row in summary["rows"] if row["franchise_id"] == selected.id), None)
        chart_data = trend_series(selected.id, metric_key, month, year, 12, mode, growth)
        graph_data = graph_engine_payload(selected.id, metric_key, month, year, 12, mode, growth)
    elif not is_privileged_user() and ids:
        first_id = ids[0]
        my_row = next((row for row in summary["rows"] if row["franchise_id"] == first_id), None)
        chart_data = trend_series(first_id, metric_key, month, year, 12, mode, growth)
        graph_data = graph_engine_payload(first_id, metric_key, month, year, 12, mode, growth)
    graph_data = locals().get("graph_data")
    return render_template(
        "performance/kpi.html",
        summary=summary,
        my_row=my_row,
        chart_data=chart_data or [],
        graph_data=graph_data,
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
    graph_data = graph_engine_payload(franchise_id, chart_metric, month, year, 12, mode, growth)
    snapshot = dashboard_snapshot(franchise_id, month, year, mode, growth)
    return render_template(
        "performance/franchise.html",
        franchise=franchise,
        metric_rows=metric_rows,
        chart_metric=chart_metric,
        chart_data=chart_data,
        graph_data=graph_data,
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






@performance_bp.route("/executive")
@login_required
@permission_required("performance:view")
def executive():
    month, year = selected_period_from_request(request.args)
    mode = request_mode()
    growth = request_growth()
    ids = accessible_franchise_ids()
    dashboard = executive_dashboard(month, year, ids, mode, growth)
    return render_template(
        "performance/executive.html",
        executive=dashboard,
        metrics=PERFORMANCE_METRICS,
        target_modes=TARGET_MODES,
        target_mode=mode,
        growth=growth,
        month_options=MONTHS,
        year_options=reporting_years(),
        selected_month=month,
        selected_year=year,
        selected_period_label=month_label(month, year),
    )


@performance_bp.route("/leaderboards")
@login_required
@permission_required("performance:view")
def leaderboards():
    month, year = selected_period_from_request(request.args)
    mode = request_mode()
    growth = request_growth()
    ids = accessible_franchise_ids()
    boards = leaderboard_decision_centre(month, year, ids, mode, growth)
    return render_template(
        "performance/leaderboards.html",
        boards=boards,
        metrics=PERFORMANCE_METRICS,
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
    auto_values = targets_for_period(month, year, ids, "growth_bracket", DEFAULT_GROWTH_PERCENT)
    bracket_plan = target_plan_for_period(month, year, ids)
    return render_template(
        "performance/targets.html",
        franchises=franchises,
        target_values=values,
        auto_values=auto_values,
        bracket_plan=bracket_plan,
        metrics=PERFORMANCE_METRICS,
        month_options=MONTHS,
        year_options=reporting_years(),
        selected_month=month,
        selected_year=year,
        selected_period_label=month_label(month, year),
    )


@performance_bp.route("/targets/generate", methods=["POST"])
@login_required
@permission_required("performance:manage_targets")
def generate_targets():
    month, year = selected_period_from_request(request.form)
    saved = save_growth_bracket_targets(month, year, accessible_franchise_ids())
    log_action("Performance", "Generated fair bracket targets", f"Targets generated: {saved}; Period: {month_label(month, year)}")
    flash(f"Generated {saved} fair growth-bracket targets for {month_label(month, year)}.", "success")
    return redirect(url_for("performance.targets", month=month, year=year))


@performance_bp.route("/annual-budget", methods=["GET", "POST"])
@login_required
@permission_required("performance:manage_targets")
def annual_budget():
    try:
        target_year = int(request.values.get("year") or selected_period_from_request(request.args)[1])
    except Exception:
        target_year = selected_period_from_request(request.args)[1]
    ids = accessible_franchise_ids()
    franchises = Franchise.query.filter(Franchise.id.in_(ids)).order_by(Franchise.business_name.asc()).all() if ids else []
    if request.method == "POST":
        saved = save_annual_budget_targets(target_year, ids)
        log_action("Performance", "Generated annual performance budget", f"Targets generated: {saved}; Year: {target_year}")
        flash(f"Generated {saved} monthly budget targets for {target_year}.", "success")
        return redirect(url_for("performance.annual_budget", year=target_year))
    plan = annual_budget_plan_for_period(target_year, ids)
    return render_template(
        "performance/annual_budget.html",
        franchises=franchises,
        plan=plan,
        metrics=PERFORMANCE_METRICS,
        month_options=MONTHS,
        year_options=reporting_years(),
        selected_year=target_year,
    )


@performance_bp.route("/growth-brackets", methods=["GET", "POST"])
@login_required
@permission_required("performance:manage_targets")
def growth_brackets():
    if request.method == "POST":
        updated = 0
        for metric_key in PERFORMANCE_METRICS:
            for index in range(1, 8):
                from_raw = (request.form.get(f"{metric_key}_{index}_from") or "").replace("R", "").replace(",", "").strip()
                to_raw = (request.form.get(f"{metric_key}_{index}_to") or "").replace("R", "").replace(",", "").strip()
                pct_raw = (request.form.get(f"{metric_key}_{index}_percent") or "").replace("%", "").strip()
                if not from_raw and not pct_raw:
                    continue
                try:
                    amount_from = Decimal(from_raw or "0")
                    amount_to = Decimal(to_raw) if to_raw else None
                    growth_percent = Decimal(pct_raw or "0")
                except Exception:
                    continue
                bracket_id = request.form.get(f"{metric_key}_{index}_id")
                bracket = PerformanceGrowthBracket.query.get(int(bracket_id)) if bracket_id else None
                if not bracket:
                    bracket = PerformanceGrowthBracket(metric=metric_key)
                    db.session.add(bracket)
                bracket.amount_from = amount_from
                bracket.amount_to = amount_to
                bracket.growth_percent = growth_percent
                bracket.basis_metric = metric_key
                bracket.is_active = True
                updated += 1
        db.session.commit()
        log_action("Performance", "Updated growth brackets", f"Growth brackets updated: {updated}")
        flash("Growth target brackets saved.", "success")
        return redirect(url_for("performance.growth_brackets"))

    existing = {}
    for bracket in PerformanceGrowthBracket.query.filter_by(is_active=True).order_by(
        PerformanceGrowthBracket.metric.asc(), PerformanceGrowthBracket.amount_from.asc()
    ).all():
        existing.setdefault(bracket.metric, []).append(bracket)
    return render_template(
        "performance/growth_brackets.html",
        metrics=PERFORMANCE_METRICS,
        existing=existing,
    )


@performance_bp.route("/recalculate", methods=["POST"])
@login_required
@permission_required("performance:manage_targets")
def recalculate():
    month, year = selected_period_from_request(request.form)
    saved = rebuild_performance_results(month, year, accessible_franchise_ids(), "growth_bracket")
    log_action("Performance", "Recalculated performance results", f"Rows saved: {saved}; Period: {month_label(month, year)}")
    flash(f"Performance results recalculated for {month_label(month, year)}.", "success")
    return redirect(url_for("performance.index", month=month, year=year, target_mode="growth_bracket"))
