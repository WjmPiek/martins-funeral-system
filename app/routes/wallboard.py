
from datetime import date, datetime, time
from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
from app.models import User, LapsedPolicy, RecoveryCallLog, ClientApplication
from app.security import require_manager_or_admin, is_admin_user
from app.services.branch_access import user_branch, selected_branch_arg

wallboard_bp = Blueprint("wallboard", __name__, url_prefix="/wallboard")

def _payload(branch=None):
    start = datetime.combine(date.today(), time.min)
    leads = LapsedPolicy.query
    apps = ClientApplication.query
    users = User.query
    if branch:
        leads = leads.filter(LapsedPolicy.branch == branch)
        apps = apps.filter(ClientApplication.branch == branch)
        users = users.filter(User.branch == branch)
    total_calls = RecoveryCallLog.query.filter(RecoveryCallLog.created_at >= start).count()
    sales_today = apps.filter(ClientApplication.created_at >= start).count()
    callbacks_due = leads.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date <= date.today()).count()
    open_leads = leads.filter(LapsedPolicy.recovery_status.in_(["Imported","New","Called","No Answer","Callback","Interested"])).count()
    agents = []
    for u in users.order_by(User.branch.asc(), User.name.asc()).all():
        if not u.role or u.role.name.lower().replace('_',' ') not in {"agent","sales agent","staff","user"}: continue
        calls = RecoveryCallLog.query.filter(RecoveryCallLog.agent_id == u.id, RecoveryCallLog.created_at >= start).count()
        apps_count = ClientApplication.query.filter(ClientApplication.agent_id == u.id, ClientApplication.created_at >= start).count()
        agents.append({"name": u.name, "branch": u.branch, "calls": calls, "sales": apps_count, "conversion": round(apps_count/calls*100,1) if calls else 0})
    return {"generated_at": datetime.now().strftime("%H:%M:%S"), "total_calls": total_calls, "sales_today": sales_today, "callbacks_due": callbacks_due, "open_leads": open_leads, "agents": agents}

@wallboard_bp.route("/")
@login_required
def index():
    blocked = require_manager_or_admin()
    if blocked: return blocked
    branch = selected_branch_arg() if is_admin_user() else user_branch()
    return render_template("wallboard/index.html", branch=branch)

@wallboard_bp.route("/data")
@login_required
def data():
    branch = selected_branch_arg() if is_admin_user() else user_branch()
    return jsonify(_payload(branch))
