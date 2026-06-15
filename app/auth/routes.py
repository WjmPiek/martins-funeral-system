from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_mail import Message
from app.extensions import db, mail
from app.models import User, Role, Franchise
from datetime import datetime, timezone


auth_bp = Blueprint("auth", __name__)


def send_password_reset_email(user):
    token = user.get_reset_token()
    reset_url = url_for("auth.reset_password", token=token, _external=True)
    subject = "Reset your password"
    body = f"""Hello {user.name},

A password reset was requested for your account.

Click this link to create a new password:
{reset_url}

This link expires in 30 minutes.

If you did not request this, you can ignore this email.
"""
    try:
        msg = Message(subject=subject, recipients=[user.email], body=body)
        mail.send(msg)
        return True, None
    except Exception as exc:
        if current_app.debug:
            print("Password reset link:", reset_url)
        return False, reset_url


@auth_bp.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        surname = request.form.get("surname", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not surname or not email or not password:
            flash("Please complete all required fields.", "danger")
            return render_template("auth/register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("auth/register.html")

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("An account with this email already exists.", "warning")
            return redirect(url_for("auth.login"))

        user = User(name=name, surname=surname, email=email)
        user.set_password(password)

        franchise = Franchise.query.order_by(Franchise.id.asc()).first()
        if not franchise:
            franchise = Franchise(business_name="Martins Funerals Franchise")
            db.session.add(franchise)
            db.session.flush()
        user.franchise_id = franchise.id
        user.assigned_franchises.append(franchise)


        # The first registered user becomes Admin so the system can be configured.
        default_role_name = "Admin" if User.query.count() == 0 else "Franchise User"
        role = Role.query.filter_by(name=default_role_name).first()
        if not role:
            role = Role(name=default_role_name, description=f"Default {default_role_name} role", is_system_role=True)
            db.session.add(role)
            db.session.flush()
        user.roles.append(role)

        db.session.add(user)
        db.session.commit()

        flash("Registration successful. You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password) and user.is_active_account:
            user.last_login_at = datetime.now(timezone.utc)
            user.ensure_protected_admin_role()
            db.session.commit()
            login_user(user)
            flash("Welcome back.", "success")
            return redirect(url_for("dashboard.index"))

        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()

        if user:
            sent, debug_url = send_password_reset_email(user)
            if sent:
                flash("Password reset instructions have been sent to your email.", "success")
            else:
                flash("Email sending is not configured yet. In development, check the terminal for the reset link.", "warning")
                if debug_url:
                    flash(f"Development reset link: {debug_url}", "info")
        else:
            flash("If that email exists, reset instructions will be sent.", "info")

        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    user = User.verify_reset_token(token)
    if not user:
        flash("The reset link is invalid or has expired.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/reset_password.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("auth/reset_password.html")

        user.set_password(password)
        db.session.commit()
        flash("Your password has been updated. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html")
