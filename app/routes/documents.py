import os
import secrets
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import ClientApplication, ClientFicaDocument, AuditLog
from app.services.document_status_service import document_summary, FICA_LABELS
from app.services.fica_validation_service import validate_fica_upload
from app.services.email_service import send_email
from app.services.whatsapp_service import send_whatsapp_message
from app.services.branch_access import scope_by_branch, ensure_branch_access, selected_branch_arg, branch_choices_from_model


documents_bp = Blueprint("documents", __name__, url_prefix="/documents")
ALLOWED_UPLOADS = {"pdf", "png", "jpg", "jpeg", "webp"}


def _role_name():
    return str(getattr(getattr(current_user, "role", None), "name", "") or "").lower().replace("_", " ")


def _can_manage_documents():
    return _role_name() in {"admin", "super admin", "super_admin", "manager", "branch manager", "branch_manager", "compliance", "qa"}


def _client_name(app):
    return " ".join([x for x in [app.first_names, app.surname] if x]) or app.application_ref


def _upload_folder():
    folder = os.path.abspath(current_app.config["UPLOAD_FOLDER"])
    os.makedirs(folder, exist_ok=True)
    return folder


def _resolve_existing(path):
    if not path:
        return None
    base = os.path.basename(path)
    candidates = [path, os.path.abspath(path), os.path.join(_upload_folder(), base), os.path.join(current_app.root_path, "static", "uploads", base)]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return os.path.abspath(candidate)
    return None


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOADS


@documents_bp.route("/")
@login_required
def document_dashboard():
    if not _can_manage_documents():
        flash("Only managers/compliance users can access document tracking.", "danger")
        return redirect(url_for("main.dashboard"))
    branch = selected_branch_arg()
    status_filter = request.args.get("status") or "outstanding"
    q = scope_by_branch(ClientApplication.query, ClientApplication, agent_col=ClientApplication.agent_id, selected_branch=branch)
    apps = q.order_by(ClientApplication.updated_at.desc()).limit(300).all()

    records = []
    for app in apps:
        summary = document_summary(app)
        if status_filter == "missing" and not summary["missing"]:
            continue
        if status_filter == "review" and not summary["pending_review"]:
            continue
        if status_filter == "complete" and not summary["complete"]:
            continue
        if status_filter == "outstanding" and summary["complete"]:
            continue
        records.append({"app": app, "summary": summary})

    branches = branch_choices_from_model(db, ClientApplication)
    stats = {
        "outstanding": sum(1 for app in apps if not document_summary(app)["complete"]),
        "missing": sum(1 for app in apps if document_summary(app)["missing"]),
        "review": sum(1 for app in apps if document_summary(app)["pending_review"]),
        "complete": sum(1 for app in apps if document_summary(app)["complete"]),
    }
    return render_template("documents/dashboard.html", records=records, branches=branches, active_branch=branch, status_filter=status_filter, stats=stats)


@documents_bp.route("/application/<int:app_id>", methods=["GET", "POST"])
@login_required
def application_documents(app_id):
    if not _can_manage_documents():
        flash("Only managers/compliance users can manage documents.", "danger")
        return redirect(url_for("main.dashboard"))
    app = ClientApplication.query.get_or_404(app_id)
    ensure_branch_access(app, agent_attr="agent_id")
    if request.method == "POST":
        doc_type = request.form.get("document_type")
        uploaded_file = request.files.get("file")
        if doc_type not in FICA_LABELS:
            flash("Invalid FICA document type.", "danger")
            return redirect(url_for("documents.application_documents", app_id=app.id))
        if not uploaded_file or not uploaded_file.filename:
            flash("Choose a file to upload.", "danger")
            return redirect(url_for("documents.application_documents", app_id=app.id))
        if not _allowed_file(uploaded_file.filename):
            flash("Only PDF, JPG, PNG or WEBP files are allowed.", "danger")
            return redirect(url_for("documents.application_documents", app_id=app.id))
        safe = secure_filename(uploaded_file.filename)
        folder = os.path.join(_upload_folder(), f"fica_app_{app.id}")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{doc_type}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{safe}")
        uploaded_file.save(path)
        validation_status, validation_notes = validate_fica_upload(path, safe, doc_type, app)
        doc = ClientFicaDocument(application_id=app.id, document_type=doc_type, original_filename=safe, file_path=path, status=validation_status, uploaded_ip=request.remote_addr, user_agent=request.headers.get("User-Agent"))
        db.session.add(doc)
        db.session.add(AuditLog(user_id=current_user.id, action="FICA Uploaded", entity_type="ClientApplication", entity_id=str(app.id), details=f"{FICA_LABELS.get(doc_type, doc_type)} uploaded by staff: {safe}; Status: {validation_status}; {validation_notes}"))
        db.session.commit()
        flash(f"Document uploaded. Status: {validation_status}. {validation_notes}", "warning" if validation_status == "Needs Review" else "danger")
        return redirect(url_for("documents.application_documents", app_id=app.id))
    return render_template("documents/application.html", app=app, summary=document_summary(app), fica_labels=FICA_LABELS)


@documents_bp.route("/fica/<int:doc_id>/download")
@login_required
def download_fica(doc_id):
    if not _can_manage_documents():
        abort(403)
    doc = ClientFicaDocument.query.get_or_404(doc_id)
    ensure_branch_access(doc.application, agent_attr="agent_id")
    path = _resolve_existing(doc.file_path)
    if not path:
        abort(404)
    return send_file(path, as_attachment=False)


@documents_bp.route("/fica/<int:doc_id>/<action>", methods=["POST"])
@login_required
def review_fica(doc_id, action):
    if not _can_manage_documents():
        abort(403)
    doc = ClientFicaDocument.query.get_or_404(doc_id)
    ensure_branch_access(doc.application, agent_attr="agent_id")
    if action not in {"approve", "reject"}:
        abort(404)
    old_status = doc.status
    doc.status = "Reviewed" if action == "approve" else "Rejected"
    reason = request.form.get("reason", "").strip()
    db.session.add(AuditLog(
        user_id=current_user.id,
        action="FICA Reviewed",
        entity_type="ClientFicaDocument",
        entity_id=str(doc.id),
        details=f"{FICA_LABELS.get(doc.document_type, doc.document_type)} changed from {old_status} to {doc.status}. {reason}"
    ))
    db.session.commit()
    flash(f"{FICA_LABELS.get(doc.document_type, doc.document_type)} marked as {doc.status}.", "success" if action == "approve" else "warning")
    return redirect(url_for("documents.application_documents", app_id=doc.application_id))


@documents_bp.route("/application/<int:app_id>/resend-missing/<channel>", methods=["POST"])
@login_required
def resend_missing(app_id, channel):
    if not _can_manage_documents():
        flash("Only managers/compliance users can resend document requests.", "danger")
        return redirect(url_for("main.dashboard"))
    app = ClientApplication.query.get_or_404(app_id)
    ensure_branch_access(app, agent_attr="agent_id")
    summary = document_summary(app)
    missing_labels = [row["label"] for row in summary["missing"]]
    if not missing_labels:
        flash("No missing documents to request.", "success")
        return redirect(url_for("documents.application_documents", app_id=app.id))

    if not app.sign_token or app.sign_token_revoked or app.sign_token_used_at:
        app.sign_token = secrets.token_urlsafe(32)
        app.sign_token_created_at = datetime.utcnow()
        app.sign_token_used_at = None
        app.sign_token_revoked = False

    base_url = current_app.config.get("BASE_URL") or request.url_root.rstrip("/")
    link = f"{base_url}{url_for('signing.sign_application', token=app.sign_token)}"
    body = (
        f"Dear {_client_name(app)},\n\n"
        "Martin's Funerals still needs the following documents/signatures to complete your application:\n"
        + "\n".join(f"- {label}" for label in missing_labels)
        + f"\n\nPlease use this secure link to complete them:\n{link}\n\nThank you."
    )

    sent = False
    if channel == "email":
        if not app.email:
            flash("This application has no email address.", "danger")
            return redirect(url_for("documents.application_documents", app_id=app.id))
        sent = send_email(app.email, "Martin's Funerals missing documents", body, [])
    elif channel == "whatsapp":
        if not app.cell_number:
            flash("This application has no cellphone number.", "danger")
            return redirect(url_for("documents.application_documents", app_id=app.id))
        sent = send_whatsapp_message(app.cell_number, body)
    else:
        abort(404)

    db.session.add(AuditLog(user_id=current_user.id, action="Missing Documents Requested", entity_type="ClientApplication", entity_id=str(app.id), details=f"Channel: {channel}; Missing: {', '.join(missing_labels)}"))
    db.session.commit()
    if sent:
        flash(f"Missing document request sent by {channel}.", "success")
    else:
        flash(f"Request saved but {channel} delivery failed. Check provider settings/logs.", "warning")
    return redirect(url_for("documents.application_documents", app_id=app.id))
