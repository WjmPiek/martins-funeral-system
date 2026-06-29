from datetime import datetime, timedelta
from io import BytesIO
import base64
import hashlib
import secrets

import qrcode
from flask import Blueprint, current_app, jsonify, render_template, request, redirect, url_for, flash, make_response
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import AuditLog, QRLoginToken, QRTrustedDevice, User


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

QR_EXPIRY_SECONDS = 90
TRUSTED_DEVICE_DAYS = 180
TRUSTED_DEVICE_COOKIE = "mf_qr_trusted_device"
SUPER_ADMIN_EMAIL = "wjm@martinsdirect.com"
ALLOWED_QR_ROLES = {"super admin", "super_admin", "admin", "branch manager", "branch_manager", "manager", "supervisor", "agent", "user", "staff"}
LOGIN_ATTEMPTS = {}
MAX_LOGIN_ATTEMPTS = 8
LOGIN_WINDOW_SECONDS = 15 * 60


def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def _user_agent():
    return (request.headers.get("User-Agent") or "")[:500]


def _login_key():
    return (_client_ip() or "unknown") + ":" + (request.form.get("email", "").lower().strip() or "unknown")


def _login_blocked():
    now = datetime.utcnow()
    key = _login_key()
    attempts = [t for t in LOGIN_ATTEMPTS.get(key, []) if (now - t).total_seconds() < LOGIN_WINDOW_SECONDS]
    LOGIN_ATTEMPTS[key] = attempts
    return len(attempts) >= MAX_LOGIN_ATTEMPTS


def _record_bad_login():
    key = _login_key()
    LOGIN_ATTEMPTS.setdefault(key, []).append(datetime.utcnow())


def _clear_bad_logins():
    LOGIN_ATTEMPTS.pop(_login_key(), None)


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _audit(user_id, action, details):
    try:
        db.session.add(AuditLog(user_id=user_id, action=action, entity_type="auth", entity_id="qr_login", details=details))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _role_allowed(user):
    role_name = (user.role.name if getattr(user, "role", None) else "").lower().strip()
    return not role_name or role_name in ALLOWED_QR_ROLES




def _is_admin_user(user):
    role_name = (user.role.name if getattr(user, "role", None) else "").lower().strip()
    return role_name in {"admin", "super admin", "super_admin"}

def _is_super_admin_user(user):
    email = ((getattr(user, "email", "") or "").lower().strip())
    role_name = (user.role.name if getattr(user, "role", None) else "").lower().strip()
    return email == SUPER_ADMIN_EMAIL or role_name in {"super admin", "super_admin"}

def _admin_required():
    if not current_user.is_authenticated or not _is_admin_user(current_user):
        flash("Admin access required.", "danger")
        return redirect(url_for("role_portals.home"))
    return None

def _device_type(user_agent):
    ua = (user_agent or "").lower()
    if "iphone" in ua or "ipad" in ua:
        return "iPhone / iPad"
    if "android" in ua:
        return "Android phone"
    if "windows" in ua:
        return "Windows device"
    if "macintosh" in ua or "mac os" in ua:
        return "Apple Mac device"
    if "linux" in ua:
        return "Linux device"
    return "Unknown device"

def _trusted_device_from_cookie():
    raw_token = request.cookies.get(TRUSTED_DEVICE_COOKIE)
    if not raw_token:
        return None
    device = QRTrustedDevice.query.filter_by(device_token_hash=_hash_token(raw_token), active=True).first()
    if not device or device.is_expired:
        return None
    user = db.session.get(User, device.user_id)
    if not user or not user.active or not _role_allowed(user):
        return None
    return device


def _set_trusted_device_cookie(response, raw_token):
    response.set_cookie(
        TRUSTED_DEVICE_COOKIE,
        raw_token,
        max_age=TRUSTED_DEVICE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=request.is_secure,
        samesite="Lax",
    )
    return response


def _approve_qr_with_user(qr_token, user, via):
    qr_token.status = "approved"
    qr_token.approved_user_id = user.id
    qr_token.approved_at = datetime.utcnow()
    qr_token.approval_ip = _client_ip()
    qr_token.approval_user_agent = _user_agent()
    db.session.commit()
    _audit(user.id, "QR_LOGIN_APPROVED", f"QR login approved via {via} from phone IP {_client_ip()}")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if _login_blocked():
            flash("Too many failed login attempts. Please wait a few minutes and try again.", "danger")
            return render_template("auth/login.html"), 429
        user = User.query.filter_by(email=request.form.get("email", "").lower().strip()).first()
        if user and user.check_password(request.form.get("password", "")) and user.active:
            _clear_bad_logins()
            login_user(user)
            return redirect(url_for("main.dashboard"))
        _record_bad_login()
        flash("Invalid login details", "danger")
    return render_template("auth/login.html")




@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Public user registration. New users stay inactive until Admin assigns a role."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").lower().strip()
        branch = request.form.get("branch", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please complete name, email and password.", "danger")
            return render_template("auth/register.html")
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/register.html")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("auth/register.html")
        if User.query.filter_by(email=email).first():
            flash("This email is already registered. Please login or contact Admin.", "warning")
            return render_template("auth/register.html")

        from app.models import Role
        role = Role.query.filter_by(name="Pending").first()
        if not role:
            role = Role(name="Pending", description="Registered user pending Admin role assignment")
            db.session.add(role)
            db.session.flush()

        user = User(name=name, email=email, branch=branch, work_tel=phone, role=role, active=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        _audit(user.id, "USER_REGISTERED", f"User registration pending Admin role assignment for {email} / {branch}")
        flash("Registration received. Admin must approve your account and assign your role before you can login or link your phone.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


def _ensure_role(name, description=None):
    from app.models import Role
    role = Role.query.filter_by(name=name).first()
    if not role:
        role = Role(name=name, description=description or name)
        db.session.add(role)
        db.session.flush()
    return role


@auth_bp.route("/admin/branch-manager-approvals")
@login_required
def admin_branch_manager_approvals():
    return redirect(url_for("auth.users_manage"))


@auth_bp.route("/admin/branch-manager-approvals/<int:user_id>/approve", methods=["POST"])
@login_required
def admin_approve_branch_manager(user_id):
    blocked = _admin_required()
    if blocked:
        return blocked
    from app.models import Role
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "warning")
        return redirect(url_for("auth.admin_branch_manager_approvals"))
    if (user.role.name if getattr(user, "role", None) else "").lower().strip() == "admin":
        flash("Admin users are protected and cannot be edited.", "danger")
        return redirect(url_for("auth.admin_branch_manager_approvals"))
    role_id = request.form.get("role_id", type=int)
    role = db.session.get(Role, role_id) if role_id else None
    if not role or role.name not in {"Branch Manager", "Agent"}:
        flash("Please select Branch Manager or Agent before approving this user.", "danger")
        return redirect(url_for("auth.admin_branch_manager_approvals"))
    branch = (request.form.get("branch") or user.branch or "").strip()
    if not branch and role.name in {"Branch Manager", "Agent"}:
        flash("Please assign a branch before saving an Agent or Branch Manager.", "danger")
        return redirect(url_for("auth.admin_branch_manager_approvals"))
    user.role = role
    user.branch = branch
    user.active = True
    db.session.commit()
    _audit(current_user.id, "USER_BRANCH_ACCESS_SAVED", f"Saved user {user.email} as {role.name}; branch={branch}")
    flash(f"{user.name} saved as {role.name} for branch {branch}.", "success")
    return redirect(url_for("auth.admin_branch_manager_approvals"))


@auth_bp.route("/admin/branch-manager-approvals/<int:user_id>/reject", methods=["POST"])
@login_required
def admin_reject_branch_manager(user_id):
    blocked = _admin_required()
    if blocked:
        return blocked
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "warning")
        return redirect(url_for("auth.admin_branch_manager_approvals"))
    if (user.role.name if getattr(user, "role", None) else "").lower().strip() == "admin":
        flash("Admin users are protected and cannot be deleted.", "danger")
        return redirect(url_for("auth.admin_branch_manager_approvals"))
    email = user.email
    db.session.delete(user)
    db.session.commit()
    _audit(current_user.id, "USER_REJECTED", f"Rejected/deleted user registration {email}")
    flash("Registration rejected and removed.", "info")
    return redirect(url_for("auth.admin_branch_manager_approvals"))




# PHASE 15: ROLE-SAFE USER / AGENT MANAGEMENT
def _role_name(user):
    return ((user.role.name if getattr(user, "role", None) else "") or "").lower().replace("_", " ").strip()

def _is_branch_manager_user(user):
    return _role_name(user) in {"branch manager", "manager", "supervisor"}

def _manager_or_admin_required():
    if not current_user.is_authenticated or not (_is_admin_user(current_user) or _is_branch_manager_user(current_user)):
        flash("Admin or Branch Manager access required.", "danger")
        return redirect(url_for("role_portals.home"))
    return None

def _is_protected_admin(user):
    return _role_name(user) in {"admin", "super admin"} or ((getattr(user, "email", "") or "").lower().strip() == SUPER_ADMIN_EMAIL)

def _branch_choices():
    from app.models import ClientApplication, LapsedPolicy
    branches = set()
    for model in (User, ClientApplication, LapsedPolicy):
        try:
            for row in db.session.query(model.branch).filter(model.branch.isnot(None)).distinct().all():
                if row[0]:
                    branches.add(row[0].strip())
        except Exception:
            pass
    if current_user.is_authenticated and getattr(current_user, "branch", None):
        branches.add(current_user.branch.strip())
    return sorted(b for b in branches if b)

def _can_manage_target(target):
    if not target:
        return False, "User not found."
    if _is_protected_admin(target):
        return False, "Admin and Super Admin users are protected and cannot be edited or deleted."
    if _is_admin_user(current_user):
        return True, ""
    if _is_branch_manager_user(current_user):
        if _role_name(target) != "agent":
            return False, "Branch Managers can only manage Agent users."
        if (target.branch or "") != (current_user.branch or ""):
            return False, "Branch Managers can only manage agents in their own branch."
        return True, ""
    return False, "You do not have permission to manage users."

def _allowed_manage_roles():
    from app.models import Role
    names = ["Agent"] if _is_branch_manager_user(current_user) and not _is_admin_user(current_user) else (["Admin", "Branch Manager", "Agent"] if _is_super_admin_user(current_user) else ["Branch Manager", "Agent"])
    roles = []
    for name in names:
        roles.append(_ensure_role(name, name))
    db.session.commit()
    return roles

@auth_bp.route("/users")
@login_required
def users_manage():
    blocked = _manager_or_admin_required()
    if blocked:
        return blocked
    allowed_roles = _allowed_manage_roles()
    branches = _branch_choices()
    if _is_admin_user(current_user):
        users = User.query.order_by(User.active.asc(), User.branch.asc(), User.name.asc()).all()
    else:
        users = User.query.filter(User.branch == current_user.branch).order_by(User.active.asc(), User.name.asc()).all()
    return render_template("auth/user_management.html", users=users, allowed_roles=allowed_roles, branches=branches)

@auth_bp.route("/users/create", methods=["POST"])
@login_required
def users_create():
    blocked = _manager_or_admin_required()
    if blocked:
        return blocked
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").lower().strip()
    password = request.form.get("password") or ""
    role_id = request.form.get("role_id", type=int)
    branch = (request.form.get("branch") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    from app.models import Role
    role = db.session.get(Role, role_id) if role_id else None
    allowed_names = {r.name for r in _allowed_manage_roles()}
    if not name or not email or not password or not role:
        flash("Please complete name, email, password and role.", "danger")
        return redirect(url_for("auth.users_manage"))
    if role.name not in allowed_names:
        flash("You cannot create that role.", "danger")
        return redirect(url_for("auth.users_manage"))
    if len(password) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return redirect(url_for("auth.users_manage"))
    if User.query.filter_by(email=email).first():
        flash("That email already exists.", "danger")
        return redirect(url_for("auth.users_manage"))
    if _is_branch_manager_user(current_user) and not _is_admin_user(current_user):
        branch = current_user.branch or ""
    if not branch:
        flash("Please select/enter a branch.", "danger")
        return redirect(url_for("auth.users_manage"))
    user = User(name=name, email=email, branch=branch, work_tel=phone, role=role, active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    _audit(current_user.id, "USER_CREATED", f"Created {role.name} {email}; branch={branch}")
    flash(f"{role.name} created and allocated to {branch}.", "success")
    return redirect(url_for("auth.users_manage"))

@auth_bp.route("/users/<int:user_id>/update", methods=["POST"])
@login_required
def users_update(user_id):
    blocked = _manager_or_admin_required()
    if blocked:
        return blocked
    user = db.session.get(User, user_id)
    ok, msg = _can_manage_target(user)
    if not ok:
        flash(msg, "danger")
        return redirect(url_for("auth.users_manage"))
    name = (request.form.get("name") or user.name).strip()
    branch = (request.form.get("branch") or user.branch or "").strip()
    phone = (request.form.get("phone") or "").strip()
    active = request.form.get("active") == "1"
    role_id = request.form.get("role_id", type=int)
    from app.models import Role
    role = db.session.get(Role, role_id) if role_id else user.role
    allowed_names = {r.name for r in _allowed_manage_roles()}
    if not role or role.name not in allowed_names:
        flash("You cannot assign that role.", "danger")
        return redirect(url_for("auth.users_manage"))
    if _is_branch_manager_user(current_user) and not _is_admin_user(current_user):
        branch = current_user.branch or ""
        role = _ensure_role("Agent", "Agent")
    if not branch:
        flash("Branch is required.", "danger")
        return redirect(url_for("auth.users_manage"))
    old = f"role={user.role.name if user.role else ''}; branch={user.branch}; active={user.active}"
    user.name = name
    user.branch = branch
    user.work_tel = phone
    user.role = role
    user.active = active
    new_password = request.form.get("new_password") or ""
    if new_password:
        if len(new_password) < 8:
            flash("New password must be at least 8 characters.", "danger")
            return redirect(url_for("auth.users_manage"))
        user.set_password(new_password)
    db.session.commit()
    _audit(current_user.id, "USER_UPDATED", f"Updated {user.email}: {old} -> role={role.name}; branch={branch}; active={active}")
    flash("User saved.", "success")
    return redirect(url_for("auth.users_manage"))



def _ensure_super_admin_account():
    """Make wjm@martinsdirect.com a protected Super Admin whenever that user exists."""
    from app.models import Role
    role = Role.query.filter_by(name="Super Admin").first()
    if not role:
        role = Role(name="Super Admin", description="Protected Super Admin account")
        db.session.add(role)
        db.session.flush()
    user = User.query.filter(db.func.lower(User.email) == SUPER_ADMIN_EMAIL).first()
    if user and (not user.role or user.role.name != "Super Admin" or not user.active):
        user.role = role
        user.active = True
        db.session.commit()
    else:
        db.session.commit()
    return user

def _reassign_user_history_to_super_admin(deleted_user):
    """Move every user foreign-key reference to Super Admin before deleting.

    The previous delete still failed when tables such as lapsed_policies kept a
    foreign-key reference to the user. This function discovers every FK in
    PostgreSQL that points to users(id), updates those references to the
    protected Super Admin, then flushes before the users row is deleted.
    """
    from sqlalchemy import text

    super_user = _ensure_super_admin_account()
    if not super_user:
        raise ValueError(f"Super Admin user {SUPER_ADMIN_EMAIL} does not exist yet. Create it before deleting users.")
    if int(deleted_user.id) == int(super_user.id):
        raise ValueError("Super Admin cannot be deleted.")

    old_id = int(deleted_user.id)
    super_id = int(super_user.id)

    # Business history is reassigned. Login/session rows are removed because
    # they belong to the deleted login, not to policy/application history.
    for stmt in (
        'DELETE FROM "qr_trusted_devices" WHERE user_id = :old_id',
        'DELETE FROM "qr_login_tokens" WHERE approved_user_id = :old_id',
    ):
        try:
            with db.session.begin_nested():
                db.session.execute(text(stmt), {"old_id": old_id})
        except Exception:
            # The table may not exist on older deployments. Ignore safely.
            pass

    try:
        fk_rows = db.session.execute(text("""
            SELECT kcu.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND ccu.table_schema = 'public'
              AND ccu.table_name = 'users'
              AND ccu.column_name = 'id'
              AND kcu.table_schema = 'public'
            ORDER BY kcu.table_name, kcu.column_name
        """)).fetchall()
    except Exception:
        # SQLite/local fallback used for tests. PostgreSQL uses the query above.
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        fk_rows = []
        for table_name in inspector.get_table_names():
            for fk in inspector.get_foreign_keys(table_name):
                if fk.get("referred_table") == "users" and fk.get("referred_columns") == ["id"]:
                    for column_name in fk.get("constrained_columns") or []:
                        fk_rows.append(type("FKRow", (), {"table_name": table_name, "column_name": column_name})())

    for row in fk_rows:
        table_name = row.table_name
        column_name = row.column_name
        if table_name in {"users", "qr_trusted_devices", "qr_login_tokens"}:
            continue
        quoted_table = '"' + table_name.replace('"', '""') + '"'
        quoted_column = '"' + column_name.replace('"', '""') + '"'
        try:
            with db.session.begin_nested():
                db.session.execute(
                    text(f"UPDATE {quoted_table} SET {quoted_column} = :super_id WHERE {quoted_column} = :old_id"),
                    {"super_id": super_id, "old_id": old_id},
                )
        except Exception:
            # Some association tables can have uniqueness constraints. For those
            # rows, remove the association row only; the actual business records
            # have already been reassigned by their own FK rows.
            try:
                with db.session.begin_nested():
                    db.session.execute(text(f"DELETE FROM {quoted_table} WHERE {quoted_column} = :old_id"), {"old_id": old_id})
            except Exception:
                raise

    # Explicit protection for the table reported by Render, even if FK discovery
    # is unavailable for any reason.
    db.session.execute(text('UPDATE "lapsed_policies" SET assigned_agent_id = :super_id WHERE assigned_agent_id = :old_id'), {"super_id": super_id, "old_id": old_id})
    db.session.flush()
    return super_user

def _delete_user_row_permanently(user_id):
    from sqlalchemy import text
    result = db.session.execute(text('DELETE FROM users WHERE id = :old_id'), {"old_id": int(user_id)})
    db.session.flush()
    return result.rowcount

@auth_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
def users_delete(user_id):
    blocked = _manager_or_admin_required()
    if blocked:
        return blocked
    user = db.session.get(User, user_id)
    ok, msg = _can_manage_target(user)
    if not ok:
        flash(msg, "danger")
        return redirect(url_for("auth.users_manage"))
    if user.id == current_user.id:
        flash("You cannot delete your own account while logged in.", "danger")
        return redirect(url_for("auth.users_manage"))
    if not _is_admin_user(current_user):
        flash("Only Admin/Super Admin can permanently delete users.", "danger")
        return redirect(url_for("auth.users_manage"))

    email = user.email
    role = user.role.name if user.role else "User"
    branch = user.branch
    old_id = int(user.id)
    try:
        super_user = _reassign_user_history_to_super_admin(user)
        try:
            db.session.expunge(user)
        except Exception:
            pass
        _delete_user_row_permanently(old_id)
        db.session.commit()
        _audit(current_user.id, "USER_PERMANENTLY_DELETED", f"Permanently deleted {role} {email}; branch={branch}; history reassigned to Super Admin {super_user.email}")
        flash("User permanently deleted. All linked history was moved under Super Admin.", "info")
    except Exception as exc:
        db.session.rollback()
        flash(f"User could not be deleted: {exc}", "danger")
    return redirect(url_for("auth.users_manage"))

@auth_bp.route("/users/employees")
@login_required
def users_employees():
    return users_manage()

@auth_bp.route("/users/roles")
@login_required
def users_roles():
    blocked = _admin_required()
    if blocked:
        return blocked
    from app.models import Role
    roles = Role.query.order_by(Role.name.asc()).all()
    return render_template("auth/user_roles.html", roles=roles)

@auth_bp.route("/users/old-franchises")
@login_required
def old_franchises():
    blocked = _admin_required()
    if blocked:
        return blocked
    return render_template("auth/old_franchises.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/qr/start", methods=["POST"])
def qr_start():
    token = secrets.token_urlsafe(48)
    qr_token = QRLoginToken(
        token=token,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(seconds=QR_EXPIRY_SECONDS),
        desktop_ip=_client_ip(),
        desktop_user_agent=_user_agent(),
    )
    db.session.add(qr_token)
    db.session.commit()

    approve_url = url_for("auth.qr_approve", token=token, _external=True)
    img = qrcode.make(approve_url)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    return jsonify({
        "token": token,
        "qr_image": f"data:image/png;base64,{image_b64}",
        "expires_in": QR_EXPIRY_SECONDS,
    })


@auth_bp.route("/qr/status/<token>")
def qr_status(token):
    qr_token = QRLoginToken.query.filter_by(token=token).first()
    if not qr_token:
        return jsonify({"status": "invalid"}), 404

    if qr_token.desktop_ip != _client_ip() or qr_token.desktop_user_agent != _user_agent():
        return jsonify({"status": "blocked"}), 403

    if qr_token.status == "pending" and qr_token.is_expired:
        qr_token.status = "expired"
        db.session.commit()

    if qr_token.status == "approved":
        user = db.session.get(User, qr_token.approved_user_id)
        if not user or not user.active or not _role_allowed(user):
            qr_token.status = "rejected"
            db.session.commit()
            return jsonify({"status": "rejected"})
        login_user(user)
        qr_token.status = "used"
        qr_token.used_at = datetime.utcnow()
        db.session.commit()
        _audit(user.id, "QR_LOGIN_USED", f"Desktop QR login completed from IP {_client_ip()}")
        return jsonify({"status": "approved", "redirect": url_for("main.dashboard")})

    return jsonify({"status": qr_token.status})


@auth_bp.route("/qr/approve/<token>", methods=["GET", "POST"])
def qr_approve(token):
    qr_token = QRLoginToken.query.filter_by(token=token).first()
    if not qr_token:
        return render_template("auth/qr_approve.html", state="invalid")

    if qr_token.status != "pending" or qr_token.is_expired:
        if qr_token.status == "pending":
            qr_token.status = "expired"
            db.session.commit()
        return render_template("auth/qr_approve.html", state=qr_token.status)

    trusted_device = _trusted_device_from_cookie()
    if trusted_device:
        user = db.session.get(User, trusted_device.user_id)
        trusted_device.last_ip = _client_ip()
        trusted_device.last_used_at = datetime.utcnow()
        _approve_qr_with_user(qr_token, user, "trusted device")
        return render_template("auth/qr_approve.html", state="trusted_approved", user=user)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "reject":
            qr_token.status = "rejected"
            db.session.commit()
            return render_template("auth/qr_approve.html", state="rejected")

        email = request.form.get("email", "").lower().strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password) or not user.active or not _role_allowed(user):
            flash("Access denied. Use an active TeleSales user account.", "danger")
            return render_template("auth/qr_approve.html", state="pair_required", token=qr_token)

        raw_device_token = secrets.token_urlsafe(48)
        device = QRTrustedDevice(
            user_id=user.id,
            device_token_hash=_hash_token(raw_device_token),
            device_name=request.form.get("device_name", "Mobile device")[:180] or "Mobile device",
            first_ip=_client_ip(),
            last_ip=_client_ip(),
            user_agent=_user_agent(),
            last_used_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=TRUSTED_DEVICE_DAYS),
            active=True,
        )
        db.session.add(device)
        _approve_qr_with_user(qr_token, user, "first-time device pairing")
        response = make_response(render_template("auth/qr_approve.html", state="paired_approved", user=user))
        _set_trusted_device_cookie(response, raw_device_token)
        _audit(user.id, "QR_TRUSTED_DEVICE_CREATED", f"Trusted QR device created from IP {_client_ip()}")
        return response

    return render_template("auth/qr_approve.html", state="pair_required", token=qr_token)


@auth_bp.route("/qr/remove-trusted-device", methods=["POST"])
def qr_remove_trusted_device():
    raw_token = request.cookies.get(TRUSTED_DEVICE_COOKIE)
    response = make_response(redirect(url_for("auth.login")))
    if raw_token:
        device = QRTrustedDevice.query.filter_by(device_token_hash=_hash_token(raw_token), active=True).first()
        if device:
            device.active = False
            db.session.commit()
            _audit(device.user_id, "QR_TRUSTED_DEVICE_REMOVED", f"Trusted QR device removed from IP {_client_ip()}")
        response.delete_cookie(TRUSTED_DEVICE_COOKIE)
    flash("This phone is no longer trusted for QR login.", "info")
    return response


@auth_bp.route("/admin/trusted-devices")
@login_required
def admin_trusted_devices():
    blocked = _admin_required()
    if blocked:
        return blocked

    devices = (QRTrustedDevice.query
        .order_by(QRTrustedDevice.active.desc(), QRTrustedDevice.last_used_at.desc().nullslast(), QRTrustedDevice.created_at.desc())
        .all())
    users = {u.id: u for u in User.query.all()}
    return render_template("auth/admin_trusted_devices.html", devices=devices, users=users, device_type=_device_type, now=datetime.utcnow())


@auth_bp.route("/admin/trusted-devices/<int:device_id>/revoke", methods=["POST"])
@login_required
def admin_revoke_trusted_device(device_id):
    blocked = _admin_required()
    if blocked:
        return blocked

    device = db.session.get(QRTrustedDevice, device_id)
    if not device:
        flash("Trusted device not found.", "warning")
        return redirect(url_for("auth.admin_trusted_devices"))

    device.active = False
    device.expires_at = datetime.utcnow()
    db.session.commit()
    _audit(current_user.id, "QR_TRUSTED_DEVICE_REVOKED_BY_ADMIN", f"Admin revoked trusted device {device.id} for user {device.user_id}")
    flash("Trusted device revoked. The phone must be paired again before QR auto-login works.", "success")
    return redirect(url_for("auth.admin_trusted_devices"))


@auth_bp.route("/admin/trusted-devices/<int:device_id>/force-repair", methods=["POST"])
@login_required
def admin_force_repair_device(device_id):
    blocked = _admin_required()
    if blocked:
        return blocked

    device = db.session.get(QRTrustedDevice, device_id)
    if not device:
        flash("Trusted device not found.", "warning")
        return redirect(url_for("auth.admin_trusted_devices"))

    device.active = False
    device.expires_at = datetime.utcnow()
    db.session.commit()
    _audit(current_user.id, "QR_TRUSTED_DEVICE_FORCE_REPAIR", f"Admin forced re-pairing for device {device.id} user {device.user_id}")
    flash("Force re-pairing applied for this device.", "success")
    return redirect(url_for("auth.admin_trusted_devices"))


@auth_bp.route("/admin/trusted-devices/user/<int:user_id>/force-repair", methods=["POST"])
@login_required
def admin_force_repair_user_devices(user_id):
    blocked = _admin_required()
    if blocked:
        return blocked

    devices = QRTrustedDevice.query.filter_by(user_id=user_id, active=True).all()
    for device in devices:
        device.active = False
        device.expires_at = datetime.utcnow()
    db.session.commit()
    _audit(current_user.id, "QR_TRUSTED_USER_FORCE_REPAIR", f"Admin forced re-pairing for all trusted devices for user {user_id}; count={len(devices)}")
    flash(f"Force re-pairing applied to {len(devices)} active device(s) for this user.", "success")
    return redirect(url_for("auth.admin_trusted_devices"))
