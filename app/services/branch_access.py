from flask import abort, request
from flask_login import current_user
from sqlalchemy import or_

GLOBAL_BRANCH_ROLES = {"admin", "super admin"}
MANAGER_BRANCH_ROLES = {"manager", "branch manager", "branch_manager", "supervisor", "qa", "compliance"}


def role_name(user=None):
    user = user or current_user
    role = getattr(user, "role", None)
    return str(getattr(role, "name", "") or "").strip().lower().replace("_", " ")


def is_admin(user=None):
    return role_name(user) in GLOBAL_BRANCH_ROLES


def is_branch_manager(user=None):
    return role_name(user) in MANAGER_BRANCH_ROLES


def can_view_all_branches(user=None):
    return is_admin(user)


def user_branch(user=None):
    return (getattr(user or current_user, "branch", None) or "").strip()


def selected_branch_arg():
    branch = (request.args.get("branch") or "").strip()
    return branch


def branch_choices_from_model(db, model, branch_col=None):
    branch_col = branch_col or model.branch
    q = db.session.query(branch_col).filter(branch_col.isnot(None), branch_col != "")
    if not can_view_all_branches() and user_branch():
        q = q.filter(branch_col == user_branch())
    return [r[0] for r in q.distinct().order_by(branch_col.asc()).all() if r[0]]


def scope_by_branch(query, model, branch_col=None, agent_col=None, selected_branch=None, allow_agent_fallback=True):
    """Apply data isolation.

    Super Admin/Admin can see all branches and may filter by selected_branch.
    Branch managers/supervisors/compliance users see only their own branch.
    Agents see only rows allocated to them when an agent column is supplied; otherwise they see nothing.
    """
    branch_col = branch_col or getattr(model, "branch", None)
    selected_branch = (selected_branch or "").strip()

    if can_view_all_branches():
        if selected_branch and branch_col is not None:
            return query.filter(branch_col == selected_branch)
        return query

    if is_branch_manager():
        branch = user_branch()
        if branch and branch_col is not None:
            return query.filter(branch_col == branch)
        return query.filter(False)

    if allow_agent_fallback and agent_col is not None:
        return query.filter(agent_col == current_user.id)

    return query.filter(False)


def ensure_branch_access(obj, branch_attr="branch", agent_attr=None):
    if can_view_all_branches():
        return True
    if is_branch_manager():
        branch = user_branch()
        obj_branch = (getattr(obj, branch_attr, None) or "").strip()
        if branch and obj_branch == branch:
            return True
    if agent_attr and getattr(obj, agent_attr, None) == current_user.id:
        return True
    abort(403)
