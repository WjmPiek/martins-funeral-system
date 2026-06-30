from decimal import Decimal
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.audit import log_action
from app.extensions import db
from app.franchise_context import get_accessible_franchises, get_selected_franchise, is_privileged_user
from app.models import Franchise, FranchiseTarget, MonthlyFigure, PerformanceGrowthBracket, User
from app.performance.service import (
    DEFAULT_GROWTH_PERCENT,
    MONTHS,
    PERFORMANCE_METRICS,
    TARGET_MODES,
    accessible_franchise_ids,
    active_leaderboard_franchise_ids,
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
    ensure_performance_results,
    target_plan_for_period,
    save_growth_bracket_targets,
    annual_budget_plan_for_period,
    save_annual_budget_targets,
    franchise_dashboard,
    metric_page_summary,
    metric_trend_summary,
    graph_engine_payload,
    graph_engine_payload_for_franchises,
    leaderboard_rows,
    leaderboard_decision_centre,
    executive_dashboard,
    executive_insights,
    franchise_insights,
    decision_centre,
    capture_performance_history,
    performance_history,
    performance_history_periods,
    user_access_summary,
    inactive_franchise_candidates,
    auto_hide_inactive_franchises,
    reactivate_franchise_performance,
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
    ensure_performance_results(month, year, ids, "growth_bracket")
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
    ids = active_leaderboard_franchise_ids()
    ensure_performance_results(month, year, ids, "growth_bracket")
    previous_m, previous_y = previous_month(month, year)
    ensure_performance_results(previous_m, previous_y, ids, "growth_bracket")

    # Live KPI leaderboards shown side-by-side on the Leaderboard tab.
    # This uses all active franchise users so a franchise user can see their
    # own position on the full leaderboard. Detailed graph/KPI pages remain
    # protected by accessible_franchise_ids().
    metric_order = ["cash", "sales", "insurance_premiums", "joinings", "funerals"]
    metric_titles = {
        "cash": "Cash",
        "sales": "Sales",
        "insurance_premiums": "Insurance",
        "joinings": "Joining's",
        "funerals": "Funerals",
    }
    metric_boards = []
    for key in metric_order:
        board_rows = leaderboard_rows(key, month, year, ids, mode, growth)
        metric_boards.append({
            "key": key,
            "title": metric_titles.get(key, PERFORMANCE_METRICS[key]["label"]),
            "rows": board_rows,
        })
    return render_template(
        "performance/index.html",
        metric_boards=metric_boards,
        metrics=PERFORMANCE_METRICS,
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
    ensure_performance_results(month, year, ids, "growth_bracket")
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
    ensure_performance_results(month, year, [franchise_id], "growth_bracket")
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






@performance_bp.route("/graphs")
@login_required
@permission_required("performance:view")
def graphs():
    month, year = selected_period_from_request(request.args)
    mode = request_mode()
    growth = request_growth()
    ids = accessible_franchise_ids()
    ensure_performance_results(month, year, ids, "growth_bracket")
    metric_key = request.args.get("metric", "cash")
    if metric_key not in PERFORMANCE_METRICS:
        metric_key = "cash"
    periods = request.args.get("periods", 12, type=int)
    if periods not in (6, 12, 24, 36):
        periods = 12

    franchises = Franchise.query.filter(Franchise.id.in_(ids)).order_by(Franchise.business_name.asc()).all() if ids else []
    selected_franchise = None
    is_combined_view = False
    selected_label = "No franchise selected"

    raw_franchise_id = (request.args.get("franchise_id") or "").strip().lower()
    if is_privileged_user() and raw_franchise_id in ("", "all", "combined"):
        # Admin / Mother Company users must see all franchise user data combined
        # by default. Selecting a specific franchise switches the page to that
        # franchise only.
        is_combined_view = True
        selected_label = "All Franchise Users Combined"
        graph_data = graph_engine_payload_for_franchises(ids, metric_key, month, year, periods, mode, growth) if ids else None
    else:
        franchise_id = request.args.get("franchise_id", type=int)
        selected = get_selected_franchise()
        if franchise_id and franchise_id not in ids:
            abort(403)
        if not franchise_id:
            franchise_id = selected.id if selected and selected.id in ids else (franchises[0].id if franchises else None)
        selected_franchise = Franchise.query.get(franchise_id) if franchise_id else None
        selected_label = selected_franchise.business_name if selected_franchise else selected_label
        graph_data = graph_engine_payload(franchise_id, metric_key, month, year, periods, mode, growth) if franchise_id else None

    return render_template(
        "performance/graphs.html",
        graph_data=graph_data,
        franchises=franchises,
        selected_franchise=selected_franchise,
        selected_label=selected_label,
        is_combined_view=is_combined_view,
        show_combined_option=is_privileged_user(),
        metrics=PERFORMANCE_METRICS,
        metric_key=metric_key,
        periods=periods,
        target_modes=TARGET_MODES,
        target_mode=mode,
        growth=growth,
        month_options=MONTHS,
        year_options=reporting_years(),
        selected_month=month,
        selected_year=year,
        selected_period_label=month_label(month, year),
    )


@performance_bp.route("/decision-centre")
@login_required
@permission_required("performance:view")
def decision_centre_view():
    month, year = selected_period_from_request(request.args)
    mode = request_mode()
    growth = request_growth()
    ids = accessible_franchise_ids()
    ensure_performance_results(month, year, ids, "growth_bracket")
    centre = decision_centre(month, year, ids, mode, growth)
    return render_template(
        "performance/decision_centre.html",
        centre=centre,
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


@performance_bp.route("/executive")
@login_required
@permission_required("performance:view")
def executive():
    month, year = selected_period_from_request(request.args)
    mode = request_mode()
    growth = request_growth()
    ids = accessible_franchise_ids()
    ensure_performance_results(month, year, ids, "growth_bracket")
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
    ids = active_leaderboard_franchise_ids()
    ensure_performance_results(month, year, ids, "growth_bracket")
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


@performance_bp.route("/insights")
@login_required
@permission_required("performance:view")
def insights():
    month, year = selected_period_from_request(request.args)
    mode = request_mode()
    growth = request_growth()
    ids = accessible_franchise_ids()
    ensure_performance_results(month, year, ids, "growth_bracket")
    selected = get_selected_franchise()
    franchise_id = request.args.get("franchise_id", type=int)
    if franchise_id and franchise_id not in ids:
        abort(403)
    if franchise_id:
        franchise = Franchise.query.get_or_404(franchise_id)
        insight_data = {
            "period_label": month_label(month, year),
            "items": franchise_insights(franchise_id, month, year, mode, growth),
            "counts": {},
            "franchise": franchise,
        }
    elif selected and selected.id in ids and not is_privileged_user():
        insight_data = {
            "period_label": month_label(month, year),
            "items": franchise_insights(selected.id, month, year, mode, growth),
            "counts": {},
            "franchise": selected,
        }
    else:
        insight_data = executive_insights(month, year, ids, mode, growth)
    franchises = Franchise.query.filter(Franchise.id.in_(ids)).order_by(Franchise.business_name.asc()).all() if ids else []
    return render_template(
        "performance/insights.html",
        insights=insight_data,
        franchises=franchises,
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
    hidden = auto_hide_inactive_franchises(month, year, accessible_franchise_ids(include_inactive=True), current_user.id)
    saved = rebuild_performance_results(month, year, accessible_franchise_ids(), "growth_bracket")
    log_action("Performance", "Recalculated performance results", f"Rows saved: {saved}; Hidden inactive: {hidden}; Period: {month_label(month, year)}")
    flash(f"Performance results recalculated for {month_label(month, year)}. Hidden inactive franchises: {hidden}.", "success")
    return redirect(url_for("performance.index", month=month, year=year, target_mode="growth_bracket"))


@performance_bp.route("/recalculate-all", methods=["POST"])
@login_required
@permission_required("performance:manage_targets")
def recalculate_all():
    periods = db.session.query(MonthlyFigure.month, MonthlyFigure.year).distinct().order_by(
        MonthlyFigure.year.asc(), MonthlyFigure.month.asc()
    ).all()
    total_saved = 0
    for period_month, period_year in periods:
        franchise_ids = [
            row[0]
            for row in db.session.query(MonthlyFigure.franchise_id)
            .filter_by(month=period_month, year=period_year)
            .distinct()
            .all()
        ]
        total_saved += rebuild_performance_results(period_month, period_year, franchise_ids, "growth_bracket")
    log_action("Performance", "Recalculated all performance cache rows", f"Rows saved: {total_saved}; Periods: {len(periods)}")
    flash(f"All performance cache rows rebuilt. Rows saved: {total_saved}; periods: {len(periods)}.", "success")
    month, year = selected_period_from_request(request.form)
    return redirect(url_for("performance.index", month=month, year=year, target_mode="growth_bracket"))


@performance_bp.route("/history")
@login_required
@permission_required("performance:view")
def history():
    month, year = selected_period_from_request(request.args)
    ids = accessible_franchise_ids()
    selected = get_selected_franchise()
    franchise_id = request.args.get("franchise_id", type=int)
    if franchise_id and franchise_id not in ids:
        abort(403)
    if not franchise_id:
        franchise_id = selected.id if selected and selected.id in ids else (ids[0] if ids else None)
    if not franchise_id:
        flash("No franchise history is available for your user access.", "warning")
        return redirect(url_for("performance.index"))
    franchise = Franchise.query.get_or_404(franchise_id)
    rows = performance_history(franchise_id, month, year)
    franchises = Franchise.query.filter(Franchise.id.in_(ids)).order_by(Franchise.business_name.asc()).all() if ids else []
    return render_template(
        "performance/history.html",
        franchise=franchise,
        history_rows=rows,
        franchises=franchises,
        periods=performance_history_periods(ids),
        metrics=PERFORMANCE_METRICS,
        month_options=MONTHS,
        year_options=reporting_years(),
        selected_month=month,
        selected_year=year,
        selected_period_label=month_label(month, year),
    )


@performance_bp.route("/history/capture", methods=["POST"])
@login_required
@permission_required("performance:manage_targets")
def capture_history():
    month, year = selected_period_from_request(request.form)
    saved = capture_performance_history(month, year, accessible_franchise_ids(), "growth_bracket", DEFAULT_GROWTH_PERCENT, current_user.id)
    log_action("Performance", "Captured performance history", f"Snapshots saved: {saved}; Period: {month_label(month, year)}")
    flash(f"Captured {saved} performance history snapshots for {month_label(month, year)}.", "success")
    return redirect(url_for("performance.history", month=month, year=year))


@performance_bp.route("/inactive-franchises")
@login_required
@permission_required("performance:manage_inactive")
def inactive_franchises():
    month, year = selected_period_from_request(request.args)
    ids = accessible_franchise_ids(include_inactive=True)
    all_rows = inactive_franchise_candidates(month, year, ids)
    # Old Franchises must only show franchise users/franchises with no KPI data
    # in the last 3 months. Active franchises with recent data are excluded.
    rows = [row for row in all_rows if (not row["has_recent_data"] and not row["is_performance_active"])]
    active_count = sum(1 for row in all_rows if row["has_recent_data"])
    hidden_count = len(rows)
    return render_template(
        "performance/inactive_franchises.html",
        rows=rows,
        active_count=active_count,
        hidden_count=hidden_count,
        month_options=MONTHS,
        year_options=reporting_years(),
        selected_month=month,
        selected_year=year,
        selected_period_label=month_label(month, year),
    )


@performance_bp.route("/inactive-franchises/scan", methods=["POST"])
@login_required
@permission_required("performance:manage_inactive")
def scan_inactive_franchises():
    month, year = selected_period_from_request(request.form)
    changed = auto_hide_inactive_franchises(month, year, accessible_franchise_ids(include_inactive=True), current_user.id)
    log_action("Performance", "Auto-hidden inactive franchises", f"Franchises hidden: {changed}; Period: {month_label(month, year)}")
    flash(f"Hidden {changed} franchise(s) with no KPI data for the last 3 months.", "success")
    return redirect(url_for("performance.inactive_franchises", month=month, year=year))


@performance_bp.route("/inactive-franchises/<int:franchise_id>/reactivate", methods=["POST"])
@login_required
@permission_required("performance:manage_inactive")
def reactivate_inactive_franchise(franchise_id):
    month, year = selected_period_from_request(request.form)
    if franchise_id not in accessible_franchise_ids(include_inactive=True):
        abort(403)
    franchise = reactivate_franchise_performance(franchise_id, current_user.id)
    if franchise:
        log_action("Performance", "Reactivated franchise performance", f"Franchise: {franchise.business_name}; ID: {franchise.id}")
        flash(f"{franchise.business_name} is active again and will be included in targets, graphs and leaderboards.", "success")
    return redirect(url_for("performance.inactive_franchises", month=month, year=year))


@performance_bp.route("/access-overview")
@login_required
@permission_required("users:manage")
def access_overview():
    users = User.query.order_by(User.name.asc(), User.surname.asc()).all()
    summaries = [user_access_summary(user) for user in users]
    return render_template("performance/access_overview.html", summaries=summaries)
