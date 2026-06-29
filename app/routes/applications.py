import json
import os, secrets
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file, abort
from flask_login import login_required, current_user
from itsdangerous import URLSafeTimedSerializer
from app import db
from app.models import ClientApplication, PolicyProduct, PolicyProductRule, ApplicationSignature, ClientFicaDocument, DocumentSignature, TelesalesScriptSession
from app.security import permission_required
from app.services.email_service import send_email
from app.services.whatsapp_service import send_whatsapp_message
from app.services.pdf_service import generate_application_pdf, generate_welcome_pack, generate_popia_pdf, generate_disclosure_pdf, generate_fica_pdf
from app.services.compliance_service import only_digits, format_dob, dob_from_sa_id, is_valid_sa_id, validate_age_limit, classify_product_template, assert_application_rules
from app.services.document_status_service import document_summary
from app.services.branch_access import scope_by_branch, ensure_branch_access

applications_bp = Blueprint("applications", __name__, url_prefix="/applications")


def signer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])



def _role_name():
    return str(getattr(getattr(current_user, "role", None), "name", "") or "").lower()


def _is_admin():
    return _role_name() in {"admin", "super admin", "super_admin"}


@applications_bp.route("/")
@login_required
@permission_required("applications.view")
def list_applications():
    status_filter = (request.args.get("status") or "").strip().lower()
    q = scope_by_branch(ClientApplication.query, ClientApplication, agent_col=ClientApplication.agent_id)
    if status_filter in {"unsigned", "pending_signature", "pending-signature"}:
        q = q.filter(ClientApplication.signed_at.is_(None))
    elif status_filter:
        q = q.filter(ClientApplication.status.ilike(status_filter.replace("_", " ")))
    apps = q.order_by(ClientApplication.created_at.desc()).limit(200).all()
    return render_template("applications/list.html", apps=apps, status_filter=status_filter)

@applications_bp.route("/new", methods=["GET", "POST"])
@login_required
@permission_required("applications.create")
def new_application():
    products = PolicyProduct.query.filter_by(active=True).order_by(PolicyProduct.product_name, PolicyProduct.plan_name).all()
    if request.method == "POST":
        prod = PolicyProduct.query.get(request.form.get("product_id")) if request.form.get("product_id") else None
        ref = "APP-" + datetime.now().strftime("%Y%m%d") + "-" + secrets.token_hex(3).upper()

        def val(name, default=""):
            return request.form.get(name, default)

        def money(name):
            try:
                return float(str(request.form.get(name) or 0).replace("R", "").replace(",", ""))
            except Exception:
                return 0

        def user_is_admin():
            role = getattr(current_user, "role", None)
            return bool(role and str(role.name or "").lower() == "admin")

        def build_rows(prefix, count, fields):
            rows = []
            for i in range(1, count + 1):
                row = {f: val(f"{prefix}_{i}_{f}") for f in fields}
                if "id_or_dob" in row:
                    row["id_or_dob"] = format_dob(dob_from_sa_id(row["id_or_dob"]) or row["id_or_dob"])
                if any(str(v).strip() for v in row.values()):
                    rows.append(row)
            return json.dumps(rows)

        form_template = classify_product_template(prod)
        is_member_product = form_template == "member_product"
        product_text = f"{prod.product_name} {prod.plan_name}" if prod else ""
        locked_monthly_premium = prod.monthly_premium if prod else money("monthly_premium")
        locked_cover_amount = prod.cover_amount if prod else money("cover_amount")
        extended_premium_value = money("extended_premium") if user_is_admin() else 0
        total_payment_value = money("total_payment") if user_is_admin() and val("total_payment") else ((float(locked_monthly_premium or 0)) + float(extended_premium_value or 0))
        plan_choice_value = product_text if is_member_product else ""

        principal_dob = format_dob(val("date_of_birth") or dob_from_sa_id(val("id_number")))
        spouse_dob = format_dob(val("spouse_date_of_birth") or dob_from_sa_id(val("spouse_id_number")))
        beneficiary_dob = format_dob(val("beneficiary_date_of_birth") or dob_from_sa_id(val("beneficiary_id_number")))

        errors = []
        if val("id_number") and not is_valid_sa_id(val("id_number")):
            errors.append("Principal member ID number is not a valid South African ID number.")
        if val("spouse_id_number") and not is_valid_sa_id(val("spouse_id_number")):
            errors.append("Spouse ID number is not a valid South African ID number.")
        if val("beneficiary_id_number") and not is_valid_sa_id(val("beneficiary_id_number")):
            errors.append("Beneficiary ID number is not a valid South African ID number.")

        validate_age_limit("Principal member", principal_dob, prod, errors)
        if spouse_dob:
            validate_age_limit("Spouse", spouse_dob, prod, errors)

        if "debit" in val("payment_method").lower():
            for label, field in [("Bank Name", "bank_name"), ("Branch Code", "branch_code"), ("Account Number", "account_number"), ("Account Type", "account_type"), ("Account Holder", "account_holder")]:
                if not val(field).strip():
                    errors.append(f"{label} is required because payment method is Debit Order.")

        rows_to_check = []
        if is_member_product:
            rows_to_check.extend(json.loads(build_rows("productdep", 13, ["full_name", "relationship", "id_or_dob"])))
        else:
            rows_to_check.extend(json.loads(build_rows("child", 6, ["full_name", "relationship", "id_or_dob"])))
            rows_to_check.extend(json.loads(build_rows("extended", 6, ["full_name", "relationship", "id_or_dob", "cover", "premium"])))
        for idx, row in enumerate(rows_to_check, start=1):
            id_or_dob = row.get("id_or_dob")
            if only_digits(id_or_dob) and len(only_digits(id_or_dob)) == 13 and not is_valid_sa_id(id_or_dob):
                errors.append(f"Dependent {idx} ID number is not valid.")
            validate_age_limit(f"Dependent {idx}", dob_from_sa_id(id_or_dob) or id_or_dob, prod, errors)

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("applications/form.html", products=products, google_maps_api_key=os.getenv("GOOGLE_MAPS_API_KEY", ""))

        a = ClientApplication(
            application_ref=ref,
            product_id=prod.id if prod else None,
            policy_number=val("policy_number"),
            branch=val("branch") or current_user.branch,
            agent_id=current_user.id,
            agent_name=val("agent_name") or current_user.name,
            agent_code=val("agent_code"),

            title=val("title"),
            first_names=val("first_names"),
            surname=val("surname"),
            id_number=val("id_number"),
            date_of_birth=principal_dob,
            cell_number=val("cell_number"),
            email=val("email"),
            address=val("residential_address"),
            residential_address=val("residential_address"),
            address_place_id=val("address_place_id"),
            address_lat=money("address_lat"),
            address_lng=money("address_lng"),
            residential_postal_code=val("residential_postal_code"),
            postal_address=val("postal_address"),
            postal_code=val("postal_code"),
            home_tel=val("home_tel"),
            work_tel=val("work_tel"),

            spouse_title=val("spouse_title"),
            spouse_first_names=val("spouse_first_names"),
            spouse_surname=val("spouse_surname"),
            spouse_id_number=val("spouse_id_number"),
            spouse_date_of_birth=spouse_dob,

            plan_choice=plan_choice_value,
            cover_amount=locked_cover_amount,
            monthly_premium=locked_monthly_premium,
            extended_premium=extended_premium_value,
            total_payment=total_payment_value,
            waiting_period=f"{prod.waiting_period_months} months" if prod else val("waiting_period"),

            dependents_json="[]" if is_member_product else build_rows("child", 6, ["full_name", "relationship", "id_or_dob"]),
            extended_family_json="[]" if is_member_product else build_rows("extended", 6, ["full_name", "relationship", "id_or_dob", "cover", "premium"]),
            product_dependents_json=build_rows("productdep", 13, ["full_name", "relationship", "id_or_dob"]) if is_member_product else "[]",

            beneficiary_full_names=val("beneficiary_full_names"),
            beneficiary_title=val("beneficiary_title"),
            beneficiary_id_number=val("beneficiary_id_number"),
            beneficiary_date_of_birth=beneficiary_dob,
            beneficiary_relationship=val("beneficiary_relationship"),

            payment_method=val("payment_method"),
            first_deduction_date=format_dob(val("first_deduction_date")),
            debit_day=val("debit_day"),
            bank_name=val("bank_name"),
            branch_name=val("branch_name"),
            branch_code=val("branch_code"),
            bank_town=val("bank_town"),
            account_number=val("account_number"),
            account_type=val("account_type"),
            account_holder=val("account_holder"),

            employer=val("employer"),
            salary=money("salary"),
            persal_no=val("persal_no"),
            paypoint=val("paypoint"),
            payroll_premium=money("payroll_premium"),
            personal_holder=val("personal_holder"),
            department_code=val("department_code"),

            joining_fee=(prod.rules.joining_fee if prod and getattr(prod, "rules", None) else 0),
            joining_fee_waived=False,
            application_type="New Policy",
            form_template=form_template,
        )
        try:
            db.session.add(a)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception("Application create failed")
            flash("The database connection was interrupted while saving. Please try submitting again.", "danger")
            return render_template("applications/form.html", products=products, google_maps_api_key=os.getenv("GOOGLE_MAPS_API_KEY", ""))
        flash("Application created", "success")
        return redirect(url_for("applications.view_application", app_id=a.id))
    return render_template("applications/form.html", products=products, google_maps_api_key=os.getenv("GOOGLE_MAPS_API_KEY", ""))


@applications_bp.route("/<int:app_id>")
@login_required
@permission_required("applications.view")
def view_application(app_id):
    a = ClientApplication.query.get_or_404(app_id)
    ensure_branch_access(a, agent_attr="agent_id")
    return render_template("applications/view.html", app=a, document_summary=document_summary(a))


def _client_salutation(app_obj):
    title = (getattr(app_obj, "title", "") or "").strip()
    surname = (getattr(app_obj, "surname", "") or getattr(app_obj, "first_names", "") or "Client").strip()
    if title:
        return f"{title} {surname}"
    return surname

def _block_signing_message(errors):
    for error in errors:
        flash(error, "danger")
    flash("Application blocked. No email, SMS or WhatsApp signing link was sent. Please correct the product/FICA validation errors first.", "danger")

@applications_bp.route("/<int:app_id>/send-sign-link", methods=["POST"])
@login_required
@permission_required("applications.send_signing")
def send_sign_link(app_id):
    a = ClientApplication.query.get_or_404(app_id)
    ensure_branch_access(a, agent_attr="agent_id")
    ok, errors = assert_application_rules(a)
    if not ok:
        _block_signing_message(errors)
        return redirect(url_for("applications.view_application", app_id=a.id))
    token = secrets.token_urlsafe(32)
    a.sign_token = token
    a.sign_token_created_at = datetime.utcnow()
    a.sign_token_used_at = None
    a.sign_token_revoked = False

    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    preview_pdf = os.path.join(folder, f"review_application_{a.id}.pdf")
    popia_pdf = os.path.join(folder, f"popia_consent_{a.id}.pdf")
    disclosure_pdf = os.path.join(folder, f"policy_disclosure_{a.id}.pdf")
    fica_pdf = os.path.join(folder, f"fica_verification_{a.id}.pdf")
    generate_application_pdf(a, preview_pdf)
    generate_popia_pdf(a, popia_pdf)
    generate_disclosure_pdf(a, disclosure_pdf)
    generate_fica_pdf(a, fica_pdf)
    a.popia_pdf_path = popia_pdf
    a.disclosure_pdf_path = disclosure_pdf

    link = f"{current_app.config['BASE_URL']}{url_for('signing.sign_application', token=token)}"
    salutation = _client_salutation(a)
    body = (
        f"Dear {salutation},\n\n"
        "Please open this secure Martin's Funerals link to review your application documents, upload any required FICA documents and sign electronically:\n\n"
        f"{link}\n\n"
        "For your security, you will need your ID number to unlock the document page.\n\n"
        "No documents are attached to this email. Your documents are available only inside the secure signing link.\n\n"
        "The link can only be used once. After signing it will be deactivated."
    )
    send_email(a.email, "Your Martin's Funerals secure signing link", body, [])
    a.status = "Signing Link Sent"
    db.session.commit()
    flash("Signing link and review documents sent", "success")
    return redirect(url_for("applications.view_application", app_id=a.id))


@applications_bp.route("/<int:app_id>/send-sign-whatsapp", methods=["POST"])
@login_required
@permission_required("applications.send_signing")
def send_sign_whatsapp(app_id):
    app_obj = ClientApplication.query.get_or_404(app_id)
    ensure_branch_access(app_obj, agent_attr="agent_id")
    ok, errors = assert_application_rules(app_obj)
    if not ok:
        _block_signing_message(errors)
        return redirect(url_for("applications.view_application", app_id=app_obj.id))

    token = secrets.token_urlsafe(32)
    app_obj.sign_token = token
    app_obj.sign_token_created_at = datetime.utcnow()
    app_obj.sign_token_used_at = None
    app_obj.sign_token_revoked = False
    db.session.commit()
    base_url = current_app.config.get("BASE_URL") or request.url_root.rstrip("/")
    sign_url = f"{base_url}/sign/{token}"

    message = (
        "Martin's Funerals application signing link\n\n"
        f"Dear {_client_salutation(app_obj)},\n\n"
        "Please review and sign your application using this secure link:\n"
        f"{sign_url}\n\n"
        "You will need to complete the required confirmation and signature steps. "
        "After signing, your signed application and welcome pack will be kept on record."
    )

    phone = app_obj.cell_number
    sent = send_whatsapp_message(phone, message)

    if sent:
        flash("WhatsApp signing link sent.", "success")
    else:
        flash("WhatsApp was not sent. Check WhatsApp API environment variables and Render logs.", "danger")

    return redirect(url_for("applications.view_application", app_id=app_obj.id))




@applications_bp.route("/<int:app_id>/delete", methods=["POST"])
@login_required
@permission_required("applications.view")
def delete_application(app_id):
    if not _is_admin():
        abort(403)
    app_obj = ClientApplication.query.get_or_404(app_id)
    ref = app_obj.application_ref
    try:
        # Remove child records first so deletion works even without DB cascade rules.
        ApplicationSignature.query.filter_by(application_id=app_obj.id).delete(synchronize_session=False)
        ClientFicaDocument.query.filter_by(application_id=app_obj.id).delete(synchronize_session=False)
        DocumentSignature.query.filter_by(application_id=app_obj.id).delete(synchronize_session=False)
        TelesalesScriptSession.query.filter_by(application_id=app_obj.id).update({"application_id": None}, synchronize_session=False)
        db.session.delete(app_obj)
        db.session.commit()
        flash(f"Application {ref} deleted.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Application delete failed")
        flash("Application could not be deleted. Please check linked records or Render logs.", "danger")
    return redirect(url_for("applications.list_applications"))

@applications_bp.route("/<int:app_id>/download/<doc_type>")
@login_required
@permission_required("applications.view")
def download_document(app_id, doc_type):
    app_obj = ClientApplication.query.get_or_404(app_id)
    ensure_branch_access(app_obj, agent_attr="agent_id")

    upload_folder = os.path.abspath(current_app.config["UPLOAD_FOLDER"])
    os.makedirs(upload_folder, exist_ok=True)

    def normalize_existing(path):
        if not path:
            return None
        base = os.path.basename(path)
        candidates = [
            path,
            os.path.abspath(path),
            os.path.join(upload_folder, base),
            os.path.join(current_app.root_path, "static", "uploads", base),
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return os.path.abspath(candidate)
        return None

    if doc_type == "signed_application":
        path = normalize_existing(app_obj.signed_pdf_path)
        if not path:
            path = os.path.join(upload_folder, f"signed_application_{app_obj.id}.pdf")
            generate_application_pdf(app_obj, path)
            app_obj.signed_pdf_path = path

    elif doc_type == "welcome_pack":
        # Always regenerate so branding, footer, signature and policy details stay current.
        path = os.path.join(upload_folder, f"welcome_pack_{app_obj.id}.pdf")
        generate_welcome_pack(app_obj, path)
        app_obj.welcome_pack_path = path

    elif doc_type == "popia":
        # Always regenerate so the marketing-consent tick, signature and date reflect the latest signing record.
        path = os.path.join(upload_folder, f"popia_consent_{app_obj.id}.pdf")
        generate_popia_pdf(app_obj, path)
        app_obj.popia_pdf_path = path

    elif doc_type == "disclosure":
        path = os.path.join(upload_folder, f"policy_disclosure_{app_obj.id}.pdf")
        generate_disclosure_pdf(app_obj, path)
        app_obj.disclosure_pdf_path = path

    elif doc_type == "fica":
        path = os.path.join(upload_folder, f"fica_verification_{app_obj.id}.pdf")
        generate_fica_pdf(app_obj, path)
    else:
        abort(404)

    db.session.commit()

    if not path or not os.path.exists(path):
        abort(404)

    return send_file(path, as_attachment=False)
