
from datetime import date, datetime, time
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, LapsedPolicy, RecoveryCallLog, ClientApplication, ClientFicaDocument, TelesalesScriptSession, AuditLog
from app.security import is_admin_user, is_branch_manager_user, is_agent_user, role_home_endpoint, require_admin, require_manager_or_admin
from app.services.branch_access import scope_by_branch, selected_branch_arg, branch_choices_from_model, user_branch

role_portals_bp = Blueprint("role_portals", __name__)

def _today_bounds():
    today = date.today()
    return datetime.combine(today, time.min), datetime.combine(today, time.max)

def _base_stats(branch=None, agent_id=None):
    start, end = _today_bounds()
    leads = LapsedPolicy.query
    apps = ClientApplication.query
    calls = RecoveryCallLog.query
    scripts = TelesalesScriptSession.query
    docs = ClientFicaDocument.query.join(ClientApplication, ClientFicaDocument.application_id == ClientApplication.id)
    if branch:
        leads = leads.filter(LapsedPolicy.branch == branch)
        apps = apps.filter(ClientApplication.branch == branch)
        scripts = scripts.filter(TelesalesScriptSession.branch == branch)
        docs = docs.filter(ClientApplication.branch == branch)
    if agent_id:
        leads = leads.filter(LapsedPolicy.assigned_agent_id == agent_id)
        apps = apps.filter(ClientApplication.agent_id == agent_id)
        calls = calls.filter(RecoveryCallLog.agent_id == agent_id)
        scripts = scripts.filter(TelesalesScriptSession.agent_id == agent_id)
        docs = docs.filter(ClientApplication.agent_id == agent_id)
    return {
        "leads": leads.count(),
        "calls_today": calls.filter(RecoveryCallLog.created_at >= start, RecoveryCallLog.created_at <= end).count(),
        "sales_today": apps.filter(ClientApplication.created_at >= start, ClientApplication.created_at <= end).count(),
        "callbacks_today": leads.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date == date.today()).count(),
        "callbacks_overdue": leads.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date < date.today()).count(),
        "pending_signatures": apps.filter(ClientApplication.signed_at.is_(None)).count(),
        "fica_outstanding": docs.filter(ClientFicaDocument.status.in_(["Received", "Rejected"])).count(),
        "qa_pending": scripts.filter(TelesalesScriptSession.status == "Completed", TelesalesScriptSession.qa_result.is_(None)).count(),
    }

@role_portals_bp.route("/home")
@login_required
def home():
    return redirect(url_for(role_home_endpoint()))

@role_portals_bp.route("/admin")
@login_required
def admin_home():
    blocked = require_admin()
    if blocked: return blocked
    branch = selected_branch_arg()
    stats = _base_stats(branch=branch)
    branches = branch_choices_from_model(db, LapsedPolicy)
    agents = User.query.order_by(User.branch.asc(), User.name.asc()).all()
    if branch:
        agents = [a for a in agents if a.branch == branch]
    recent_audit = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()
    return render_template("role_portals/admin.html", stats=stats, branches=branches, active_branch=branch, agents=agents, recent_audit=recent_audit)

@role_portals_bp.route("/branch-manager")
@login_required
def branch_manager_home():
    blocked = require_manager_or_admin()
    if blocked: return blocked
    branch = selected_branch_arg() if is_admin_user() else user_branch()
    if not branch:
        branch = user_branch()
    stats = _base_stats(branch=branch)
    start, end = _today_bounds()
    agents = User.query.filter(User.branch == branch).order_by(User.name.asc()).all() if branch else []
    agent_rows = []
    for a in agents:
        calls = RecoveryCallLog.query.filter(RecoveryCallLog.agent_id == a.id, RecoveryCallLog.created_at >= start, RecoveryCallLog.created_at <= end).count()
        apps = ClientApplication.query.filter(ClientApplication.agent_id == a.id, ClientApplication.created_at >= start, ClientApplication.created_at <= end).count()
        agent_rows.append({"agent": a, "calls": calls, "sales": apps, "conversion": round(apps / calls * 100, 1) if calls else 0})
    pending_callbacks = LapsedPolicy.query.filter(LapsedPolicy.branch == branch, LapsedPolicy.recovery_status == "Callback").order_by(LapsedPolicy.next_action_date.asc()).limit(10).all() if branch else []
    return render_template("role_portals/branch_manager.html", stats=stats, branch=branch, agent_rows=agent_rows, pending_callbacks=pending_callbacks)

def _resolve_agent_context():
    """Return the agent id that the current user is allowed to view."""
    if not (is_agent_user() or is_admin_user() or is_branch_manager_user()):
        return None, "Agent access required."
    agent_id = current_user.id if is_agent_user() else request.args.get("agent_id", type=int)
    if not agent_id:
        agent_id = current_user.id
    agent = db.session.get(User, agent_id)
    if not agent:
        return None, "Selected agent was not found."
    if is_agent_user() and agent.id != current_user.id:
        return None, "Agents can only open their own dashboard."
    if is_branch_manager_user() and not is_admin_user() and (agent.branch or "") != (user_branch() or ""):
        return None, "Branch managers can only open agents in their own branch."
    return agent, None

@role_portals_bp.route("/agent")
@login_required
def agent_home():
    agent, error = _resolve_agent_context()
    if error:
        flash(error, "danger")
        return redirect(url_for("main.dashboard"))
    agent_id = agent.id
    stats = _base_stats(agent_id=agent_id)
    callbacks = LapsedPolicy.query.filter(LapsedPolicy.assigned_agent_id == agent_id, LapsedPolicy.recovery_status == "Callback").order_by(LapsedPolicy.next_action_date.asc().nullslast()).limit(10).all()
    my_apps = ClientApplication.query.filter(ClientApplication.agent_id == agent_id).order_by(ClientApplication.created_at.desc()).limit(10).all()
    return render_template("role_portals/agent.html", stats=stats, callbacks=callbacks, my_apps=my_apps, active_agent=agent)

@role_portals_bp.route("/agent/activity")
@login_required
def agent_activity():
    """Clickable Agent Portal card drill-downs.

    Every Agent Portal card points here with a `view` filter. Agents only see
    their own records. Admins can pass agent_id and Branch Managers can pass
    agent_id for agents in their own branch.
    """
    agent, error = _resolve_agent_context()
    if error:
        flash(error, "danger")
        return redirect(url_for("role_portals.agent_home"))
    view = (request.args.get("view") or "leads").strip().lower()
    today = date.today()
    start, end = _today_bounds()

    leads_q = LapsedPolicy.query.filter(LapsedPolicy.assigned_agent_id == agent.id)
    apps_q = ClientApplication.query.filter(ClientApplication.agent_id == agent.id)
    calls_q = RecoveryCallLog.query.filter(RecoveryCallLog.agent_id == agent.id)
    scripts_q = TelesalesScriptSession.query.filter(TelesalesScriptSession.agent_id == agent.id)
    docs_q = ClientFicaDocument.query.join(ClientApplication, ClientFicaDocument.application_id == ClientApplication.id).filter(ClientApplication.agent_id == agent.id)

    title = "My Leads"
    leads = []
    applications = []
    calls = []
    docs = []
    scripts = []

    if view == "calls_today":
        title = "Calls Today"
        calls = calls_q.filter(RecoveryCallLog.created_at >= start, RecoveryCallLog.created_at <= end).order_by(RecoveryCallLog.created_at.desc()).all()
    elif view == "sales_today":
        title = "Sales Today"
        applications = apps_q.filter(ClientApplication.created_at >= start, ClientApplication.created_at <= end).order_by(ClientApplication.created_at.desc()).all()
    elif view == "callbacks_today":
        title = "Callbacks Today"
        leads = leads_q.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date == today).order_by(LapsedPolicy.next_action_date.asc()).all()
    elif view == "callbacks_overdue":
        title = "Callbacks Overdue"
        leads = leads_q.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date < today).order_by(LapsedPolicy.next_action_date.asc()).all()
    elif view == "pending_signatures":
        title = "Pending Signatures"
        applications = apps_q.filter(ClientApplication.signed_at.is_(None)).order_by(ClientApplication.created_at.desc()).all()
    elif view == "fica_outstanding":
        title = "FICA Outstanding"
        docs = docs_q.filter(ClientFicaDocument.status.in_(["Received", "Rejected"])).order_by(ClientFicaDocument.uploaded_at.desc()).all()
    elif view == "qa_pending":
        title = "QA Pending"
        scripts = scripts_q.filter(TelesalesScriptSession.status == "Completed", TelesalesScriptSession.qa_result.is_(None)).order_by(TelesalesScriptSession.completed_at.desc().nullslast()).all()
    else:
        view = "leads"
        leads = leads_q.filter(LapsedPolicy.recovery_status.notin_(["Approved", "Rejected", "Closed", "Reinstated", "Suspense"])).order_by(LapsedPolicy.next_action_date.asc().nullslast(), LapsedPolicy.imported_at.desc()).all()

    return render_template(
        "role_portals/agent_activity.html",
        active_agent=agent,
        view=view,
        title=title,
        leads=leads,
        applications=applications,
        calls=calls,
        docs=docs,
        scripts=scripts,
    )


# PHASE 15 - unified CRM workspace
@role_portals_bp.route("/workspace")
@login_required
def workspace():
    """Unified CRM workspace for Admin, Branch Manager and Agent.

    Admin can select any branch and any agent. Branch Managers are locked to
    their own branch and may select agents in that branch. Agents are locked to
    their own agent record. All client/application/callback data is then scoped
    by that context so moving between tabs no longer loses the agent dashboard.
    """
    branch = request.args.get("branch") or None
    agent_id = request.args.get("agent_id", type=int)
    client_id = request.args.get("client_id", type=int)

    is_admin = is_admin_user()
    is_manager = is_branch_manager_user()
    is_agent = is_agent_user()

    if is_admin:
        branches = branch_choices_from_model(db, LapsedPolicy)
        if branch in ("", "all", "All"):
            branch = None
        agent_query = User.query
        if branch:
            agent_query = agent_query.filter(User.branch == branch)
        agents = agent_query.order_by(User.branch.asc(), User.name.asc()).all()
    elif is_manager:
        branch = user_branch()
        branches = [branch] if branch else []
        agents = User.query.filter(User.branch == branch).order_by(User.name.asc()).all() if branch else []
        if agent_id and not any(a.id == agent_id for a in agents):
            flash("You can only open agents in your own branch.", "danger")
            return redirect(url_for("role_portals.workspace"))
    elif is_agent:
        branch = current_user.branch
        branches = [branch] if branch else []
        agents = [current_user]
        agent_id = current_user.id
    else:
        flash("Workspace access required.", "danger")
        return redirect(url_for("main.dashboard"))

    selected_agent = None
    if agent_id:
        selected_agent = db.session.get(User, agent_id)
        if not selected_agent:
            flash("Selected agent was not found.", "warning")
            agent_id = None
        elif is_manager and selected_agent.branch != branch:
            flash("You can only open agents in your own branch.", "danger")
            return redirect(url_for("role_portals.workspace"))
        elif is_agent and selected_agent.id != current_user.id:
            flash("Agents can only open their own workspace.", "danger")
            return redirect(url_for("role_portals.workspace"))

    if not selected_agent and agents:
        selected_agent = agents[0] if (is_agent or is_manager) else None
        if selected_agent and not agent_id:
            agent_id = selected_agent.id

    stats = _base_stats(branch=branch, agent_id=agent_id)

    lead_query = LapsedPolicy.query
    app_query = ClientApplication.query
    call_query = RecoveryCallLog.query
    script_query = TelesalesScriptSession.query

    if branch:
        lead_query = lead_query.filter(LapsedPolicy.branch == branch)
        app_query = app_query.filter(ClientApplication.branch == branch)
        script_query = script_query.filter(TelesalesScriptSession.branch == branch)
    if agent_id:
        lead_query = lead_query.filter(LapsedPolicy.assigned_agent_id == agent_id)
        app_query = app_query.filter(ClientApplication.agent_id == agent_id)
        call_query = call_query.filter(RecoveryCallLog.agent_id == agent_id)
        script_query = script_query.filter(TelesalesScriptSession.agent_id == agent_id)

    clients = lead_query.order_by(LapsedPolicy.next_action_date.asc().nullslast(), LapsedPolicy.imported_at.desc()).limit(25).all()
    callbacks = lead_query.filter(LapsedPolicy.recovery_status == "Callback").order_by(LapsedPolicy.next_action_date.asc().nullslast()).limit(10).all()
    applications = app_query.order_by(ClientApplication.created_at.desc()).limit(10).all()
    recent_calls = call_query.order_by(RecoveryCallLog.created_at.desc()).limit(10).all()
    qa_items = script_query.filter(TelesalesScriptSession.status == "Completed", TelesalesScriptSession.qa_result.is_(None)).order_by(TelesalesScriptSession.completed_at.desc().nullslast()).limit(10).all()

    selected_client = None
    selected_client_apps = []
    selected_client_calls = []
    selected_client_scripts = []
    if client_id:
        selected_client = db.session.get(LapsedPolicy, client_id)
        allowed = False
        if selected_client:
            if is_admin:
                allowed = (not branch or selected_client.branch == branch) and (not agent_id or selected_client.assigned_agent_id == agent_id)
            elif is_manager:
                allowed = selected_client.branch == branch and (not agent_id or selected_client.assigned_agent_id == agent_id)
            elif is_agent:
                allowed = selected_client.assigned_agent_id == current_user.id
        if not allowed:
            selected_client = None
            flash("You do not have access to that client in this workspace context.", "danger")
        else:
            selected_client_apps = ClientApplication.query.filter(ClientApplication.lapsed_policy_id == selected_client.id).order_by(ClientApplication.created_at.desc()).all()
            selected_client_calls = RecoveryCallLog.query.filter(RecoveryCallLog.lapsed_policy_id == selected_client.id).order_by(RecoveryCallLog.created_at.desc()).all()
            selected_client_scripts = TelesalesScriptSession.query.filter(TelesalesScriptSession.lapsed_policy_id == selected_client.id).order_by(TelesalesScriptSession.created_at.desc()).all()

    branch_summary = {
        "branch": branch or "All Branches",
        "agents": len(agents),
        "clients": lead_query.count(),
        "callbacks": lead_query.filter(LapsedPolicy.recovery_status == "Callback").count(),
        "applications": app_query.count(),
        "qa_pending": script_query.filter(TelesalesScriptSession.status == "Completed", TelesalesScriptSession.qa_result.is_(None)).count(),
    }
    return render_template(
        "role_portals/workspace.html",
        stats=stats,
        branches=branches,
        agents=agents,
        active_branch=branch,
        active_agent=selected_agent,
        clients=clients,
        callbacks=callbacks,
        applications=applications,
        recent_calls=recent_calls,
        qa_items=qa_items,
        selected_client=selected_client,
        selected_client_apps=selected_client_apps,
        selected_client_calls=selected_client_calls,
        selected_client_scripts=selected_client_scripts,
        branch_summary=branch_summary,
        is_admin=is_admin,
        is_manager=is_manager,
        is_agent=is_agent,
    )
