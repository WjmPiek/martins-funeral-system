from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.franchise_context import set_selected_franchise, exit_franchise_view_mode, is_privileged_user, get_accessible_franchises
from app.models import MonthlyFigure, User, user_franchises
from app.leaderboard.routes import build_dashboard_leaderboard_snapshot
from app.performance.service import dashboard_snapshot as build_performance_dashboard_snapshot
from types import SimpleNamespace


dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


def permission_required(code):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.has_permission(code):
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def previous_periods(year, month, count=6):
    periods = []
    y, m = year, month
    for _ in range(count):
        periods.append((y, m))
        m -= 1
        if m < 1:
            m = 12
            y -= 1
    return set(periods)


def monthly_figure_has_data(figure):
    money_fields = [
        "funeral_receipts", "claim_receipts", "society_receipts", "cash_sales",
        "tombstone_receipts", "obo_service_receipts", "insurance_receipts",
        "insurance_payover", "admin_fee", "gross_turnover", "gross_revenue",
        "royalty_amount",
    ]
    number_fields = ["insurance_joinings", "mf_files", "number_of_funerals", "number_of_policies", "number_of_claims"]
    for field in money_fields:
        if getattr(figure, field, 0) or 0:
            return True
    for field in number_fields:
        if getattr(figure, field, 0) or 0:
            return True
    return False



def role_names(user):
    return {role.name for role in getattr(user, "roles", [])}


def ordered_franchises_for_user(user):
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

def find_linked_franchise_group(selected_franchise=None):
    """Return the franchise-user group that contains the selected franchise.

    This makes linked branches visible on the dashboard, for example:
    Dobsonville User -> Dobsonville + Soweto.
    """
    franchise_side_roles = {"Franchise User", "Franchise Manager", "Read Only User"}
    candidates = []

    if current_user.is_authenticated:
        linked = ordered_franchises_for_user(current_user)
        if len(linked) > 1 and role_names(current_user) & franchise_side_roles:
            candidates.append((current_user, linked))

    selected_id = getattr(selected_franchise, "id", None)
    if selected_id:
        for user in User.query.all():
            linked = ordered_franchises_for_user(user)
            if len(linked) < 2 or not (role_names(user) & franchise_side_roles):
                continue
            if any(franchise.id == selected_id for franchise in linked):
                candidates.append((user, linked))

    if not candidates:
        return None

    # If the selected branch belongs to a group, show the group owner with the
    # primary/main franchise first instead of whichever old user happens to be
    # returned first by the database.
    if selected_id:
        candidates.sort(key=lambda pair: 0 if pair[1] and pair[1][0].id == selected_id else 1)

    user, linked = candidates[0]
    return SimpleNamespace(user=user, franchises=linked, branch_names=[franchise.business_name or "Unnamed Franchise" for franchise in linked])

def split_franchises_by_recent_data(franchises):
    latest = db.session.query(MonthlyFigure.year, MonthlyFigure.month).order_by(
        MonthlyFigure.year.desc(), MonthlyFigure.month.desc()
    ).first()
    if not latest:
        return [], list(franchises), "No monthly figures imported yet"

    recent_periods = previous_periods(latest.year, latest.month, 6)
    franchise_ids = [franchise.id for franchise in franchises]
    if not franchise_ids:
        return [], [], f"Last 6 months ending {latest.year}-{latest.month:02d}"

    figures = MonthlyFigure.query.filter(MonthlyFigure.franchise_id.in_(franchise_ids)).all()
    active_ids = {
        figure.franchise_id
        for figure in figures
        if (figure.year, figure.month) in recent_periods and monthly_figure_has_data(figure)
    }

    active = [franchise for franchise in franchises if franchise.id in active_ids]
    inactive = [franchise for franchise in franchises if franchise.id not in active_ids]
    active.sort(key=lambda item: item.business_name or "")
    inactive.sort(key=lambda item: item.business_name or "")
    label = f"Last 6 months ending {latest.year}-{latest.month:02d}"
    return active, inactive, label


@dashboard_bp.route("/")
@login_required
@permission_required("dashboard:view")
def index():
    accessible = get_accessible_franchises()
    active_franchises, inactive_franchises, activity_period_label = split_franchises_by_recent_data(accessible)
    selected_franchise = None
    try:
        from app.franchise_context import get_selected_franchise
        selected_franchise = get_selected_franchise()
    except Exception:
        selected_franchise = None
    leaderboard_snapshot = None
    performance_snapshot = None
    if selected_franchise and current_user.has_permission("leaderboard:view"):
        leaderboard_snapshot = build_dashboard_leaderboard_snapshot(selected_franchise.id)
    if selected_franchise and current_user.has_permission("performance:view"):
        performance_snapshot = build_performance_dashboard_snapshot(selected_franchise.id)

    return render_template(
        "dashboard/index.html",
        user=current_user,
        active_franchises=active_franchises,
        inactive_franchises=inactive_franchises,
        activity_period_label=activity_period_label,
        linked_franchise_group=find_linked_franchise_group(selected_franchise),
        leaderboard_snapshot=leaderboard_snapshot,
        performance_snapshot=performance_snapshot,
    )


@dashboard_bp.route("/main")
@login_required
@permission_required("dashboard:view")
def main_dashboard():
    if is_privileged_user():
        exit_franchise_view_mode()
        flash("Returned to the main dashboard.", "success")
    return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/select-franchise/<int:franchise_id>")
@login_required
@permission_required("dashboard:view")
def select_franchise(franchise_id):
    if set_selected_franchise(franchise_id, franchise_view_mode=True):
        flash("Franchise selected. You are now viewing that franchise dashboard.", "success")
    else:
        flash("You do not have access to that franchise.", "danger")
    return redirect(url_for("dashboard.index"))
