
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, LapsedPolicy, AuditLog
from app.security import require_manager_or_admin, is_admin_user
from app.services.branch_access import user_branch, branch_choices_from_model, selected_branch_arg

allocation_bp = Blueprint("allocation", __name__, url_prefix="/allocation")

def _agents_for_branch(branch):
    q = User.query.join(User.role).filter(User.active.is_(True))
    if branch:
        q = q.filter(User.branch == branch)
    return [u for u in q.order_by(User.name.asc()).all() if u.role and u.role.name.lower().replace('_',' ') in {'agent','sales agent','staff','user'}]

@allocation_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    blocked = require_manager_or_admin()
    if blocked: return blocked
    branch = selected_branch_arg() if is_admin_user() else user_branch()
    if request.method == "POST":
        branch = request.form.get("branch") or branch
        agent_ids = [int(x) for x in request.form.getlist("agent_ids") if x.isdigit()]
        limit = request.form.get("limit", type=int) or 50
        leads = LapsedPolicy.query.filter(LapsedPolicy.assigned_agent_id.is_(None))
        if branch:
            leads = leads.filter(LapsedPolicy.branch == branch)
        leads = leads.order_by(LapsedPolicy.imported_at.asc()).limit(limit).all()
        agents = User.query.filter(User.id.in_(agent_ids)).all() if agent_ids else _agents_for_branch(branch)
        if not agents:
            flash("No active agents found for this branch.", "warning")
            return redirect(url_for("allocation.index", branch=branch or ""))
        count = 0
        for idx, lead in enumerate(leads):
            lead.assigned_agent_id = agents[idx % len(agents)].id
            count += 1
        db.session.add(AuditLog(user_id=current_user.id, action="LEADS_ALLOCATED", entity_type="allocation", entity_id=branch or "all", details=f"Allocated {count} leads across {len(agents)} agents"))
        db.session.commit()
        flash(f"Allocated {count} leads.", "success")
        return redirect(url_for("allocation.index", branch=branch or ""))
    agents = _agents_for_branch(branch)
    unassigned = LapsedPolicy.query.filter(LapsedPolicy.assigned_agent_id.is_(None))
    if branch: unassigned = unassigned.filter(LapsedPolicy.branch == branch)
    branches = branch_choices_from_model(db, LapsedPolicy)
    return render_template("allocation/index.html", branch=branch, branches=branches, agents=agents, unassigned_count=unassigned.count())
