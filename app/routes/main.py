from datetime import date, datetime, time
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from app import db
from app.models import ClientApplication, LapsedPolicy, RecoveryCallLog, PolicyProduct, User, TelesalesScriptSession, ClientFicaDocument, ComplianceReview
from app.services.branch_access import scope_by_branch, selected_branch_arg, branch_choices_from_model, can_view_all_branches, user_branch

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
@login_required
def dashboard():
    today = date.today()
    open_statuses = ["New", "Imported", "Called", "No Answer", "Callback", "Interested", "Application Started", "Signature Sent", "FICA Outstanding", "QA Review"]
    lead_q = scope_by_branch(LapsedPolicy.query, LapsedPolicy, agent_col=LapsedPolicy.assigned_agent_id)
    app_q = scope_by_branch(ClientApplication.query, ClientApplication, agent_col=ClientApplication.agent_id)
    call_q = RecoveryCallLog.query.filter(RecoveryCallLog.agent_id == current_user.id)
    stats = {
        "applications": app_q.count(),
        "products": PolicyProduct.query.count(),
        "lapsed": lead_q.count(),
        "calls": call_q.count(),
        "calls_today": call_q.filter(RecoveryCallLog.created_at >= today).count(),
        "callbacks_today": lead_q.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date == today).count(),
        "callbacks_overdue": lead_q.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date < today).count(),
        "due_now": lead_q.filter(LapsedPolicy.recovery_status.in_(open_statuses), LapsedPolicy.next_action_date <= today).count(),
        "interested": lead_q.filter(LapsedPolicy.recovery_status == "Interested").count(),
        "applications_started": lead_q.filter(LapsedPolicy.recovery_status == "Application Started").count(),
    }
    todays_calls = RecoveryCallLog.query.filter(RecoveryCallLog.agent_id == current_user.id, RecoveryCallLog.created_at >= today).order_by(RecoveryCallLog.created_at.desc()).limit(10).all()
    return render_template("dashboard/index.html", stats=stats, todays_calls=todays_calls)


@main_bp.route("/login")
def login_alias():
    return redirect(url_for("auth.login"))


@main_bp.route("/healthz")
def healthz():
    return {"ok": True, "service": "telesales"}


def _is_manager_user():
    role_name = (current_user.role.name if current_user.is_authenticated and current_user.role else "").lower().replace("_", " ")
    return role_name in {"admin", "manager", "branch manager"}


def _today_bounds():
    today = date.today()
    return datetime.combine(today, time.min), datetime.combine(today, time.max)


def _manager_scope(query):
    if not _is_manager_user():
        return query.filter(RecoveryCallLog.agent_id == current_user.id)
    return query


@main_bp.route("/manager")
@login_required
def manager_dashboard():
    """Phase 3 manager dashboard built from existing tables only. No schema changes required."""
    if not _is_manager_user():
        return redirect(url_for("main.dashboard"))

    start, end = _today_bounds()
    branch = selected_branch_arg()

    lead_query = scope_by_branch(LapsedPolicy.query, LapsedPolicy, agent_col=LapsedPolicy.assigned_agent_id, selected_branch=branch)
    app_query = scope_by_branch(ClientApplication.query, ClientApplication, agent_col=ClientApplication.agent_id, selected_branch=branch)
    call_query = RecoveryCallLog.query
    script_query = scope_by_branch(TelesalesScriptSession.query, TelesalesScriptSession, agent_col=TelesalesScriptSession.agent_id, selected_branch=branch)
    fica_query = scope_by_branch(ClientFicaDocument.query.join(ClientApplication, ClientFicaDocument.application_id == ClientApplication.id), ClientApplication, branch_col=ClientApplication.branch, agent_col=ClientApplication.agent_id, selected_branch=branch)

    open_statuses = ["New", "Imported", "Called", "No Answer", "Callback", "Interested", "Application Started", "Signature Sent", "FICA Outstanding", "QA Review"]
    pending_signature_statuses = ["Draft", "Pending Signature", "Signature Sent"]
    pending_qa_statuses = ["QA Review", "Application Started"]

    stats = {
        "total_leads": lead_query.count(),
        "open_leads": lead_query.filter(LapsedPolicy.recovery_status.in_(open_statuses)).count(),
        "calls_today": call_query.filter(RecoveryCallLog.created_at >= start, RecoveryCallLog.created_at <= end).count(),
        "callbacks_today": lead_query.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date == date.today()).count(),
        "callbacks_overdue": lead_query.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date < date.today()).count(),
        "interested": lead_query.filter(LapsedPolicy.recovery_status == "Interested").count(),
        "applications_started": lead_query.filter(LapsedPolicy.recovery_status == "Application Started").count(),
        "signature_pending": app_query.filter(ClientApplication.status.in_(pending_signature_statuses), ClientApplication.signed_at.is_(None)).count(),
        "qa_pending": lead_query.filter(LapsedPolicy.recovery_status.in_(pending_qa_statuses)).count() + script_query.filter(TelesalesScriptSession.status == "Completed", TelesalesScriptSession.qa_result.is_(None)).count(),
        "compliance_reviews": ComplianceReview.query.count(),
        "fica_received": fica_query.filter(ClientFicaDocument.status == "Received").count(),
        "approved": lead_query.filter(LapsedPolicy.recovery_status.in_(["Approved", "Reinstated"])).count(),
        "rejected": lead_query.filter(LapsedPolicy.recovery_status == "Rejected").count(),
    }
    stats["conversion_rate"] = round((stats["approved"] / stats["total_leads"] * 100), 1) if stats["total_leads"] else 0

    agent_rows = db.session.query(
        User.id, User.name, User.branch,
        db.func.count(RecoveryCallLog.id).label("calls"),
        db.func.sum(db.case((RecoveryCallLog.outcome.in_(["Wants Reinstatement", "Wants New Policy", "Application Started", "Signature Sent"]), 1), else_=0)).label("sales_actions"),
        db.func.sum(db.case((RecoveryCallLog.outcome.in_(["No Answer", "Voicemail"]), 1), else_=0)).label("no_answers"),
    ).outerjoin(RecoveryCallLog, db.and_(RecoveryCallLog.agent_id == User.id, RecoveryCallLog.created_at >= start, RecoveryCallLog.created_at <= end))
    if can_view_all_branches() and branch:
        agent_rows = agent_rows.filter(User.branch == branch)
    elif not can_view_all_branches() and user_branch():
        agent_rows = agent_rows.filter(User.branch == user_branch())
    agent_rows = agent_rows.group_by(User.id, User.name, User.branch).order_by(db.desc("calls"), User.name.asc()).all()

    agents = []
    for row in agent_rows:
        conversion = round((int(row.sales_actions or 0) / int(row.calls or 0) * 100), 1) if row.calls else 0
        agents.append({"id": row.id, "name": row.name, "branch": row.branch, "calls": int(row.calls or 0), "sales_actions": int(row.sales_actions or 0), "no_answers": int(row.no_answers or 0), "conversion": conversion})

    status_counts = db.session.query(LapsedPolicy.recovery_status, db.func.count(LapsedPolicy.id)).group_by(LapsedPolicy.recovery_status).order_by(db.func.count(LapsedPolicy.id).desc()).all()
    if branch:
        status_counts = db.session.query(LapsedPolicy.recovery_status, db.func.count(LapsedPolicy.id)).filter(LapsedPolicy.branch == branch).group_by(LapsedPolicy.recovery_status).order_by(db.func.count(LapsedPolicy.id).desc()).all()

    pending_work = {
        "overdue_callbacks": lead_query.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date < date.today()).order_by(LapsedPolicy.next_action_date.asc()).limit(10).all(),
        "today_callbacks": lead_query.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date == date.today()).order_by(LapsedPolicy.imported_at.asc()).limit(10).all(),
        "signature_pending": app_query.filter(ClientApplication.signed_at.is_(None)).order_by(ClientApplication.created_at.asc()).limit(10).all(),
        "fica_received": fica_query.filter(ClientFicaDocument.status == "Received").order_by(ClientFicaDocument.uploaded_at.asc()).limit(10).all(),
        "qa_pending": lead_query.filter(LapsedPolicy.recovery_status == "QA Review").order_by(LapsedPolicy.imported_at.asc()).limit(10).all(),
        "recent_reviews": ComplianceReview.query.order_by(ComplianceReview.created_at.desc()).limit(5).all(),
    }

    branches = branch_choices_from_model(db, LapsedPolicy)

    return render_template("dashboard/manager.html", stats=stats, agents=agents, status_counts=status_counts, pending_work=pending_work, branches=branches, active_branch=branch)


# Grouped Franchise / Monthly Figures navigation placeholders
# These keep the main tabs and sub-tabs available for Admin and Franchise/Branch users.
def _manager_or_admin():
    role_name = (current_user.role.name if current_user.is_authenticated and current_user.role else "").lower().replace("_", " ")
    return role_name in {"admin", "super admin", "branch manager", "manager", "supervisor"}

def _portal_guard():
    if not _manager_or_admin():
        return redirect(url_for("role_portals.home"))
    return None

@main_bp.route("/franchise/details")
@login_required
def franchise_details():
    blocked = _portal_guard()
    if blocked: return blocked
    branch = selected_branch_arg() or user_branch() or "All branches"
    q = scope_by_branch(LapsedPolicy.query, LapsedPolicy, selected_branch=selected_branch_arg())
    company_expr = db.func.coalesce(db.func.nullif(LapsedPolicy.company_name, ''), db.func.nullif(LapsedPolicy.franchise, ''), db.func.nullif(LapsedPolicy.branch, ''), 'Unknown Company')
    rows_q = db.session.query(
        company_expr.label('company'),
        LapsedPolicy.branch.label('branch'),
        db.func.count(LapsedPolicy.id).label('policies'),
        db.func.sum(db.case((LapsedPolicy.recovery_status == 'Suspense', 1), else_=0)).label('suspense'),
        db.func.sum(db.case((LapsedPolicy.recovery_status.notin_(['Suspense','Closed','Rejected']), 1), else_=0)).label('active_leads'),
    )
    # Apply the same branch scope to company details.
    if can_view_all_branches() and selected_branch_arg():
        rows_q = rows_q.filter(LapsedPolicy.branch == selected_branch_arg())
    elif not can_view_all_branches() and user_branch():
        rows_q = rows_q.filter(LapsedPolicy.branch == user_branch())
    rows_q = rows_q.group_by(company_expr, LapsedPolicy.branch).order_by(company_expr.asc()).all()
    rows = [[r.company, r.branch or '', int(r.policies or 0), int(r.active_leads or 0), int(r.suspense or 0)] for r in rows_q]
    cards = [
        {"label":"Scope","value":branch},
        {"label":"Companies","value":len(rows)},
        {"label":"Policies","value":sum(r[2] for r in rows)},
        {"label":"Suspense","value":sum(r[4] for r in rows)},
    ]
    return render_template("franchise_page.html", title="Company Details", subtitle="Companies/business clients from imported data. Records stay separated by branch and company.", headers=["Company Name","Branch","Policies","Active Leads","Suspense"], rows=rows, cards=cards)

@main_bp.route("/franchise/employees")
@login_required
def franchise_employees():
    blocked = _portal_guard()
    if blocked: return blocked
    return redirect(url_for("auth.users_employees"))

@main_bp.route("/monthly/performance")
@login_required
def monthly_performance():
    blocked = _portal_guard()
    if blocked: return blocked
    apps = scope_by_branch(ClientApplication.query, ClientApplication).count()
    leads = scope_by_branch(LapsedPolicy.query, LapsedPolicy).count()
    calls = RecoveryCallLog.query.count() if can_view_all_branches() else RecoveryCallLog.query.filter(RecoveryCallLog.agent_id == current_user.id).count()
    cards = [{"label":"Leads","value":leads},{"label":"Applications","value":apps},{"label":"Calls","value":calls},{"label":"Conversion","value":f"{round((apps/leads*100),1) if leads else 0}%"}]
    return render_template("franchise_page.html", title="Performance", subtitle="Monthly performance summary for the selected scope.", headers=[], rows=[], cards=cards)

@main_bp.route("/monthly/figures")
@login_required
def monthly_figures():
    blocked = _portal_guard()
    if blocked: return blocked
    return redirect(url_for("main.monthly_performance"))

@main_bp.route("/monthly/royalties")
@login_required
def monthly_royalties():
    blocked = _portal_guard()
    if blocked: return blocked
    return redirect(url_for("main.monthly_performance"))

@main_bp.route("/monthly/finance")
@login_required
def monthly_finance():
    blocked = _portal_guard()
    if blocked: return blocked
    return redirect(url_for("main.monthly_performance"))
