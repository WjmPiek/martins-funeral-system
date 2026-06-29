from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file, session
from flask_login import login_required, current_user
from app.extensions import db
from app.audit import log_action
from app.models import Franchise, RoyaltyScale, User, Role, MonthlyFigure
from app.franchise_context import get_selected_franchise

franchise_bp = Blueprint("franchise", __name__, url_prefix="/franchise")


def permission_required(code):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.has_permission(code):
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def can_edit_protected_franchise_cards():
    """Only Admin and Finance Manager may edit Agreement/Royalty Scale cards.

    Other users may still view the cards when their role has View permission,
    but the fields remain read-only and POST updates are ignored server-side.
    """
    return current_user.has_role("Admin") or current_user.has_role("Finance Manager")


def can_view_franchise_agreement():
    # Admin and Finance Manager must always see this protected card.
    # Other users only see it when the View permission is ticked.
    return can_edit_protected_franchise_cards() or current_user.has_permission("franchise_agreement:view")


def can_edit_franchise_agreement():
    # Agreement fields are locked for every role except Admin and Finance Manager.
    # The View tick box still controls whether the card is visible.
    return can_view_franchise_agreement() and can_edit_protected_franchise_cards()


def can_view_royalty_scale():
    # Admin and Finance Manager must always see this protected card.
    # Other users only see it when the View permission is ticked.
    return can_edit_protected_franchise_cards() or current_user.has_permission("royalty_scale:view")


def can_edit_royalty_scale():
    # Royalty Scale fields are locked for every role except Admin and Finance Manager.
    # The View tick box still controls whether the card is visible.
    return can_view_royalty_scale() and can_edit_protected_franchise_cards()


def recalculate_existing_monthly_figures_for_franchise(franchise):
    # Import here to avoid circular import during Flask startup.
    from app.monthly.routes import recalculate_monthly_figure

    figures = MonthlyFigure.query.filter_by(franchise_id=franchise.id).all()
    for figure in figures:
        recalculate_monthly_figure(figure)


def can_edit_franchise_financials():
    # Backwards-compatible helper used by templates. These protected cards are now
    # role-locked: only Admin and Finance Manager can edit them.
    return can_edit_franchise_agreement() or can_edit_royalty_scale()



def accessible_franchises_for_current_user():
    if current_user.has_permission("franchise_management:view") or current_user.has_permission("franchise_management:manage"):
        return Franchise.query.order_by(Franchise.business_name.asc()).all()
    if getattr(current_user, "assigned_franchises", None):
        return sorted(current_user.assigned_franchises, key=lambda item: item.business_name or "")
    selected = get_selected_franchise()
    return [selected] if selected else []


def franchise_has_royalty_scale(franchise_id):
    return RoyaltyScale.query.filter(
        RoyaltyScale.franchise_id == franchise_id,
        RoyaltyScale.percentage > 0,
    ).first() is not None


def missing_royalty_setup_items(franchise):
    missing = []
    if not franchise.agreement_start_date:
        missing.append("agreement start date")
    if not franchise.agreement_end_date:
        missing.append("agreement end date")
    if not franchise.minimum_royalty_amount or Decimal(franchise.minimum_royalty_amount or 0) <= 0:
        missing.append("minimum royalty")
    if not franchise_has_royalty_scale(franchise.id):
        missing.append("royalty scale brackets")
    return missing


def missing_royalty_setup_notifications(franchises):
    rows = []
    for item in franchises:
        missing = missing_royalty_setup_items(item)
        if missing:
            rows.append({
                "franchise": item,
                "missing": missing,
                "message": f"{item.business_name or 'Unnamed Franchise'} needs: {', '.join(missing)}",
            })
    return rows

def get_or_create_franchise():
    accessible = accessible_franchises_for_current_user()
    accessible_ids = {item.id for item in accessible}

    requested_id = request.values.get("franchise_id", type=int)
    if requested_id:
        if requested_id not in accessible_ids:
            abort(403)
        franchise = Franchise.query.get_or_404(requested_id)
        session["selected_franchise_id"] = franchise.id
        return franchise

    selected = get_selected_franchise()
    if selected and (not accessible_ids or selected.id in accessible_ids):
        return selected

    if accessible:
        franchise = accessible[0]
        session["selected_franchise_id"] = franchise.id
        return franchise

    franchise = Franchise.query.order_by(Franchise.id.asc()).first()
    if franchise:
        return franchise
    franchise = Franchise(business_name="Martins Funerals Franchise")
    db.session.add(franchise)
    db.session.commit()
    return franchise

def renumber_royalty_scales(franchise):
    scales = RoyaltyScale.query.filter_by(franchise_id=franchise.id).order_by(RoyaltyScale.row_number, RoyaltyScale.id).all()
    row_number = 1
    for scale in scales:
        scale.row_number = row_number
        row_number += 1
    db.session.flush()


def parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def format_sa_contact_number(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 10 and digits.startswith("0"):
        return f"({digits[:3]}) {digits[3:6]} {digits[6:]}"
    return (value or "").strip()


def parse_decimal(value, default="0"):
    try:
        return Decimal(str(value or default).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return Decimal(default)


@franchise_bp.route("/details", methods=["GET", "POST"])
@login_required
@permission_required("franchise_details:view")
def details():
    franchise = get_or_create_franchise()
    can_view_agreement = can_view_franchise_agreement()
    can_edit_agreement = can_edit_franchise_agreement()
    can_view_scale = can_view_royalty_scale()
    can_edit_scale = can_edit_royalty_scale()
    can_edit_financials = can_edit_franchise_financials()
    readonly_finance_fields = not can_edit_financials

    if request.method == "POST":
        if not current_user.has_permission("franchise_details:edit"):
            abort(403)

        normal_fields = [
            "business_name", "franchise_code", "ck_business_name", "ck_number", "pty_business_name", "pty_number", "vat_number", "office_address", "office_number",
            "after_hours_number", "franchisee_name", "franchisee_surname", "franchisee_cell",
            "franchisee_email", "facebook_url", "instagram_url", "tiktok_url", "website_url",
            "public_email",
        ]
        for field in normal_fields:
            setattr(franchise, field, request.form.get(field, "").strip())

        franchise.office_number = format_sa_contact_number(franchise.office_number)
        franchise.after_hours_number = format_sa_contact_number(franchise.after_hours_number)
        franchise.franchisee_cell = format_sa_contact_number(franchise.franchisee_cell)

        if can_edit_agreement:
            franchise.agreement_start_date = parse_date(request.form.get("agreement_start_date"))
            franchise.agreement_end_date = parse_date(request.form.get("agreement_end_date"))
            franchise.regional_manager_email = request.form.get("regional_manager_email", "").strip()
            franchise.finance_manager_email = request.form.get("finance_manager_email", "").strip()
            # Gross method is automatic from agreement start date.
            franchise.royalty_gross_method = "new" if (franchise.agreement_start_date and franchise.agreement_start_date.year >= 2018) else "old"

        if can_edit_scale:
            delete_ids = set()
            for raw_id in request.form.getlist("delete_scale_ids"):
                try:
                    delete_ids.add(int(raw_id))
                except (TypeError, ValueError):
                    pass

            if delete_ids:
                RoyaltyScale.query.filter(
                    RoyaltyScale.franchise_id == franchise.id,
                    RoyaltyScale.id.in_(delete_ids),
                ).delete(synchronize_session=False)

            scales = RoyaltyScale.query.filter_by(franchise_id=franchise.id).order_by(RoyaltyScale.row_number, RoyaltyScale.id).all()
            for scale in scales:
                if scale.id in delete_ids:
                    continue
                prefix = f"scale_{scale.id}_"
                scale.amount_from = parse_decimal(request.form.get(prefix + "amount_from"))
                scale.amount_to = parse_decimal(request.form.get(prefix + "amount_to"))
                scale.percentage = parse_decimal(request.form.get(prefix + "percentage"))

            new_from_values = request.form.getlist("new_scale_amount_from[]")
            new_to_values = request.form.getlist("new_scale_amount_to[]")
            new_percentage_values = request.form.getlist("new_scale_percentage[]")
            next_row = RoyaltyScale.query.filter_by(franchise_id=franchise.id).count() + 1
            for amount_from, amount_to, percentage in zip(new_from_values, new_to_values, new_percentage_values):
                amount_from_dec = parse_decimal(amount_from)
                amount_to_dec = parse_decimal(amount_to)
                percentage_dec = parse_decimal(percentage)
                if amount_from_dec == 0 and amount_to_dec == 0 and percentage_dec == 0:
                    continue
                db.session.add(RoyaltyScale(
                    franchise_id=franchise.id,
                    row_number=next_row,
                    amount_from=amount_from_dec,
                    amount_to=amount_to_dec,
                    percentage=percentage_dec,
                ))
                next_row += 1

            renumber_royalty_scales(franchise)

        log_action("Franchise Details", "Updated franchise profile", f"Franchise: {franchise.business_name}")

        if can_edit_scale:
            try:
                franchise.minimum_royalty_amount = request.form.get("minimum_royalty_amount") or 0
                # Gross method is automatic from agreement start date and is updated in the agreement block.
                franchise.royalty_gross_method = "new" if (franchise.agreement_start_date and franchise.agreement_start_date.year >= 2018) else "old"
            except Exception:
                franchise.minimum_royalty_amount = 0

        session["selected_franchise_id"] = franchise.id

        recalculate_existing_monthly_figures_for_franchise(franchise)

        db.session.commit()
        flash("Franchise details saved successfully. Royalty settings were applied to existing monthly figures.", "success")
        return redirect(url_for("franchise.details"))

    scales = RoyaltyScale.query.filter_by(franchise_id=franchise.id).order_by(RoyaltyScale.row_number).all()
    linked_users = list(franchise.assigned_users) if hasattr(franchise, "assigned_users") else []
    franchise_users = sorted(
        linked_users,
        key=lambda user: (user.name or "", user.surname or "")
    )
    accessible_franchises = accessible_franchises_for_current_user()
    missing_notifications = missing_royalty_setup_notifications(accessible_franchises)
    selected_missing_items = missing_royalty_setup_items(franchise)
    return render_template(
        "franchise/details.html",
        franchise=franchise,
        franchises=accessible_franchises,
        missing_notifications=missing_notifications,
        selected_missing_items=selected_missing_items,
        scales=scales,
        readonly_finance_fields=readonly_finance_fields,
        franchise_users=franchise_users,
        can_view_agreement=can_view_agreement,
        can_edit_agreement=can_edit_agreement,
        can_view_scale=can_view_scale,
        can_edit_scale=can_edit_scale,
        can_edit_financials=can_edit_financials,
    )


@franchise_bp.route("/details/export-pdf")
@login_required
@permission_required("franchise_details:export")
def export_details_pdf():
    franchise = get_or_create_franchise()
    scales = RoyaltyScale.query.filter_by(franchise_id=franchise.id).order_by(RoyaltyScale.row_number).all()
    from app.reports.pdf import build_franchise_details_pdf
    pdf_path = build_franchise_details_pdf(franchise, scales, current_user)
    log_action("Franchise Details", "Exported PDF", f"Franchise: {franchise.business_name}")
    db.session.commit()
    return send_file(pdf_path, as_attachment=True, download_name="franchise-details.pdf")
