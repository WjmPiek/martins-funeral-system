
from datetime import datetime, date, timezone
from decimal import Decimal
from pathlib import Path
import csv
import os
import re
import secrets

import pandas as pd
from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for, Response
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app.extensions import db
from app.audit import log_action
from app.models import (
    Franchise,
    InsurancePolicyMonthlyRaw,
    InsuranceClaimsMonthlyRaw,
    InsurancePolicyDataDetailRaw,
    InsuranceImportHistory,
    InsuranceFranchiseMapping,
    InsuranceClaimCase,
    InsuranceClaimNote,
    InsuranceClaimAttachment,
    InsuranceClaimDocumentType,
)

insurance_claims_bp = Blueprint("insurance_claims", __name__, url_prefix="/insurance-claims")


def _require(permission):
    if not current_user.has_permission(permission):
        flash("You do not have permission to access Insurance Claims.", "danger")
        return redirect(url_for("dashboard.index"))
    return None


def _storage_root():
    root = current_app.config.get("INSURANCE_CLAIMS_STORAGE_ROOT") or os.environ.get("INSURANCE_CLAIMS_STORAGE_ROOT")
    if not root:
        root = os.path.join(current_app.instance_path, "insurance_claims")
    Path(root).mkdir(parents=True, exist_ok=True)
    return Path(root)


def _clean_money(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return Decimal("0")
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return Decimal("0")
    text = text.replace("R", "").replace(",", "").replace(" ", "")
    text = re.sub(r"[^0-9.\-]", "", text)
    if text in {"", ".", "-"}:
        return Decimal("0")
    try:
        return Decimal(text)
    except Exception:
        return Decimal("0")


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _month_from(value):
    if isinstance(value, date):
        return date(value.year, value.month, 1)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return date.today().replace(day=1)
    try:
        dt = pd.to_datetime(value, errors="coerce")
        if pd.isna(dt):
            return date.today().replace(day=1)
        return date(int(dt.year), int(dt.month), 1)
    except Exception:
        return date.today().replace(day=1)


def _selected_franchise_options():
    if current_user.has_permission("franchise_management:view") or current_user.has_permission("franchise_management:manage"):
        return Franchise.query.order_by(Franchise.business_name).all()
    return current_user.accessible_franchises()


def _match_franchise(name):
    raw = str(name or "").strip()
    if not raw:
        return None, ""
    mapping = InsuranceFranchiseMapping.query.filter(db.func.lower(db.func.trim(InsuranceFranchiseMapping.source_name)) == _norm(raw)).first()
    if mapping:
        return mapping.franchise, mapping.mapped_name or raw
    key = _norm(raw)
    franchises = Franchise.query.all()
    for franchise in franchises:
        names = [franchise.business_name, franchise.franchise_code, franchise.ck_business_name, franchise.pty_business_name]
        if any(_norm(n) == key for n in names if n):
            return franchise, franchise.business_name
    # soft contains match for imported files where names carry suffixes
    for franchise in franchises:
        bn = _norm(franchise.business_name)
        if bn and (bn in key or key in bn):
            return franchise, franchise.business_name
    return None, raw


def _find_column(columns, candidates):
    normed = {_norm(c): c for c in columns}
    for candidate in candidates:
        c = normed.get(_norm(candidate))
        if c is not None:
            return c
    for c in columns:
        n = _norm(c)
        if any(_norm(candidate) in n for candidate in candidates):
            return c
    return None


def _read_excel_first_sheet(file_storage):
    return pd.read_excel(file_storage, sheet_name=0)


def _dashboard_totals():
    policies = InsurancePolicyMonthlyRaw.query.all()
    claims = InsuranceClaimsMonthlyRaw.query.all()
    total_retail = sum(Decimal(p.retail_premium or 0) for p in policies)
    total_risk = sum(Decimal(p.risk_premium or 0) for p in policies)
    total_claims = sum(Decimal(c.claims_amount or 0) for c in claims)
    total_claim_count = sum(Decimal(c.claim_count or 0) for c in claims)
    claim_ratio = (total_claims / total_risk * Decimal("100")) if total_risk else Decimal("0")
    return {
        "policy_months": len({p.import_month for p in policies}),
        "total_franchises": len({p.franchise_name for p in policies} | {c.claims_franchise_name for c in claims}),
        "total_retail": total_retail,
        "total_risk": total_risk,
        "total_claims": total_claims,
        "total_claim_count": total_claim_count,
        "claim_ratio": claim_ratio,
        "open_cases": InsuranceClaimCase.query.filter_by(archived=False).filter(InsuranceClaimCase.status != "Closed").count(),
        "closed_cases": InsuranceClaimCase.query.filter_by(status="Closed").count(),
    }


@insurance_claims_bp.route("/", methods=["GET"])
@login_required
def index():
    denied = _require("insurance_claims:view")
    if denied: return denied
    recent_policy = InsurancePolicyMonthlyRaw.query.order_by(InsurancePolicyMonthlyRaw.import_month.desc(), InsurancePolicyMonthlyRaw.franchise_name).limit(100).all()
    recent_claims = InsuranceClaimsMonthlyRaw.query.order_by(InsuranceClaimsMonthlyRaw.claim_month.desc(), InsuranceClaimsMonthlyRaw.claims_franchise_name).limit(100).all()
    imports = InsuranceImportHistory.query.order_by(InsuranceImportHistory.created_at.desc()).limit(12).all()
    cases = InsuranceClaimCase.query.filter_by(archived=False).order_by(InsuranceClaimCase.created_at.desc()).limit(10).all()
    return render_template("insurance_claims/index.html", totals=_dashboard_totals(), recent_policy=recent_policy, recent_claims=recent_claims, imports=imports, cases=cases)


@insurance_claims_bp.route("/import/policy-data", methods=["POST"])
@login_required
def import_policy_data():
    denied = _require("insurance_claims:import")
    if denied: return denied
    file = request.files.get("file")
    month_value = request.form.get("import_month")
    if not file or not file.filename:
        flash("Choose a PolicyData Excel file first.", "warning")
        return redirect(url_for("insurance_claims.index"))
    source = secure_filename(file.filename)
    import_month = _month_from(month_value or date.today())
    try:
        df = _read_excel_first_sheet(file)
        franchise_col = _find_column(df.columns, ["Franchise", "Franchise Name", "Branch", "Business Name"])
        relation_col = _find_column(df.columns, ["Relation"])
        retail_col = _find_column(df.columns, ["Retail", "Retail Premium", "Premium"])
        risk_col = _find_column(df.columns, ["AUL Risk", "Risk Premium", "Risk", "AUL Risk Premium"])
        mpia_col = _find_column(df.columns, ["MPIA", "Paid Months", "Policy Months"])
        if not franchise_col:
            raise ValueError("No franchise column found. Expected Franchise / Franchise Name / Branch.")
        db.session.query(InsurancePolicyDataDetailRaw).filter_by(source_file=source, import_month=import_month).delete()
        db.session.query(InsurancePolicyMonthlyRaw).filter_by(import_month=import_month).delete()
        buckets = {}
        row_count = 0
        for idx, row in df.iterrows():
            raw_franchise = row.get(franchise_col)
            if not str(raw_franchise or "").strip():
                continue
            relation = str(row.get(relation_col, "") or "").strip() if relation_col else ""
            is_mem = relation.upper() == "MEM" if relation_col else True
            franchise, mapped_name = _match_franchise(raw_franchise)
            retail = _clean_money(row.get(retail_col)) if retail_col else Decimal("0")
            original_risk = _clean_money(row.get(risk_col)) if risk_col else Decimal("0")
            mpia = _clean_money(row.get(mpia_col)) if mpia_col else Decimal("1")
            if mpia == 0: mpia = Decimal("1")
            single_premium = (original_risk / mpia) if mpia else Decimal("0")
            r1_fee = Decimal("1.00") * mpia if is_mem else Decimal("0")
            adv_fee = ((single_premium - Decimal("1.00")) * Decimal("0.021") * mpia) if is_mem else Decimal("0")
            risk_after = original_risk - r1_fee
            new_risk = original_risk - r1_fee - adv_fee if is_mem else Decimal("0")
            detail = InsurancePolicyDataDetailRaw(
                source_file=source, import_month=import_month, row_number=int(idx)+2,
                franchise_id=franchise.id if franchise else None, franchise_name=mapped_name or str(raw_franchise),
                relation=relation, is_mem=is_mem, retail_premium=retail, original_risk_premium=original_risk,
                mpia=mpia, single_premium=single_premium, r1_policy_fee=r1_fee, adv_fund_2_1_fee=adv_fee,
                risk_after_r1=risk_after, new_risk_premium=new_risk, raw_data={str(k): (None if pd.isna(v) else str(v)) for k, v in row.to_dict().items()}
            )
            db.session.add(detail)
            if is_mem:
                key = mapped_name or str(raw_franchise).strip()
                if key not in buckets:
                    buckets[key] = {"franchise": franchise, "retail": Decimal("0"), "risk": Decimal("0"), "orig": Decimal("0"), "r1": Decimal("0"), "adv": Decimal("0"), "qty": Decimal("0")}
                buckets[key]["retail"] += retail
                buckets[key]["risk"] += new_risk
                buckets[key]["orig"] += original_risk
                buckets[key]["r1"] += r1_fee
                buckets[key]["adv"] += adv_fee
                buckets[key]["qty"] += Decimal("1")
            row_count += 1
        for name, b in buckets.items():
            db.session.add(InsurancePolicyMonthlyRaw(
                franchise_id=b["franchise"].id if b["franchise"] else None, franchise_name=name, import_month=import_month,
                retail_premium=b["retail"], risk_premium=b["risk"], policy_qty=b["qty"], original_risk_premium=b["orig"],
                r1_policy_fee=b["r1"], underwriter_2_1_fee=b["adv"], risk_after_r1=b["orig"]-b["r1"], source_file=source
            ))
        db.session.add(InsuranceImportHistory(import_type="PolicyData", source_file=source, imported_months=import_month.isoformat(), row_count=row_count, created_by_id=current_user.id))
        db.session.commit()
        log_action("insurance_policydata_import", "Insurance Claims", f"Imported {row_count} PolicyData rows from {source}")
        flash(f"PolicyData imported: {row_count} rows. MEM rows were used for monthly policy/risk totals.", "success")
    except Exception as exc:
        db.session.rollback()
        db.session.add(InsuranceImportHistory(import_type="PolicyData", source_file=source, imported_months=str(import_month), row_count=0, status="failed", message=str(exc), created_by_id=current_user.id))
        db.session.commit()
        flash(f"PolicyData import failed: {exc}", "danger")
    return redirect(url_for("insurance_claims.index"))


@insurance_claims_bp.route("/import/claims", methods=["POST"])
@login_required
def import_claims_data():
    denied = _require("insurance_claims:import")
    if denied: return denied
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choose a Claims Excel file first.", "warning")
        return redirect(url_for("insurance_claims.index"))
    source = secure_filename(file.filename)
    try:
        df = _read_excel_first_sheet(file)
        franchise_col = _find_column(df.columns, ["Franchise", "Franchise Name", "Branch", "Claims Franchise Name"])
        date_col = _find_column(df.columns, ["Date Of Claim Paid", "Claim Paid Date", "Claim Date", "Date"])
        amount_col = _find_column(df.columns, ["Amount of Claim Paid Before Net Off", "Claim Amount", "Claims Amount", "Amount"])
        paid_franchise_col = _find_column(df.columns, ["Claim paid to franchise", "Paid Franchise"])
        paid_client_col = _find_column(df.columns, ["Claim paid to client", "Paid Client"])
        pending_col = _find_column(df.columns, ["Repudiated", "Pending", "Repudiated / Pending"])
        if not franchise_col:
            raise ValueError("No franchise column found in claims file.")
        if not date_col:
            raise ValueError("No claim date / paid date column found in claims file.")
        if not amount_col:
            raise ValueError("No claim amount column found in claims file.")
        months = set()
        buckets = {}
        row_count = 0
        for _, row in df.iterrows():
            raw_franchise = row.get(franchise_col)
            if not str(raw_franchise or "").strip():
                continue
            m = _month_from(row.get(date_col))
            months.add(m)
            franchise, mapped_name = _match_franchise(raw_franchise)
            amount = _clean_money(row.get(amount_col))
            paid_f = _clean_money(row.get(paid_franchise_col)) if paid_franchise_col else Decimal("0")
            paid_c = _clean_money(row.get(paid_client_col)) if paid_client_col else Decimal("0")
            pending = _clean_money(row.get(pending_col)) if pending_col else Decimal("0")
            key = (_norm(mapped_name or raw_franchise), mapped_name or str(raw_franchise).strip(), m)
            if key not in buckets:
                buckets[key] = {"franchise": franchise, "claims": Decimal("0"), "count": Decimal("0"), "paid_f": Decimal("0"), "paid_c": Decimal("0"), "pending": Decimal("0")}
            buckets[key]["claims"] += amount
            buckets[key]["count"] += Decimal("1") if amount else Decimal("0")
            buckets[key]["paid_f"] += paid_f
            buckets[key]["paid_c"] += paid_c
            buckets[key]["pending"] += pending
            row_count += 1
        for m in months:
            db.session.query(InsuranceClaimsMonthlyRaw).filter_by(claim_month=m).delete()
        for (claim_key, name, m), b in buckets.items():
            db.session.add(InsuranceClaimsMonthlyRaw(
                franchise_id=b["franchise"].id if b["franchise"] else None, claim_key=claim_key,
                claims_franchise_name=name, claim_month=m, claims_amount=b["claims"], claim_count=b["count"],
                claim_paid_franchise=b["paid_f"], claim_paid_client=b["paid_c"], repudiated_pending=b["pending"],
                grand_total_claims=b["claims"] + b["pending"], source_file=source
            ))
        db.session.add(InsuranceImportHistory(import_type="Claims", source_file=source, imported_months=", ".join(sorted(m.isoformat() for m in months)), row_count=row_count, created_by_id=current_user.id))
        db.session.commit()
        log_action("insurance_claims_import", "Insurance Claims", f"Imported {row_count} claims rows from {source}")
        flash(f"Claims imported: {row_count} rows across {len(months)} month(s).", "success")
    except Exception as exc:
        db.session.rollback()
        db.session.add(InsuranceImportHistory(import_type="Claims", source_file=source, row_count=0, status="failed", message=str(exc), created_by_id=current_user.id))
        db.session.commit()
        flash(f"Claims import failed: {exc}", "danger")
    return redirect(url_for("insurance_claims.index"))


@insurance_claims_bp.route("/claims")
@login_required
def claims():
    denied = _require("insurance_claims:view")
    if denied: return denied
    status = request.args.get("status", "")
    q = request.args.get("q", "")
    query = InsuranceClaimCase.query.filter_by(archived=False)
    if status:
        query = query.filter_by(status=status)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(InsuranceClaimCase.claim_ref.ilike(like), InsuranceClaimCase.claimant_name.ilike(like), InsuranceClaimCase.policy_number.ilike(like), InsuranceClaimCase.franchise_name.ilike(like)))
    cases = query.order_by(InsuranceClaimCase.created_at.desc()).limit(500).all()
    return render_template("insurance_claims/claims.html", cases=cases, status=status, q=q)


@insurance_claims_bp.route("/claims/new", methods=["GET", "POST"])
@login_required
def new_claim():
    denied = _require("insurance_claims:add")
    if denied: return denied
    franchises = _selected_franchise_options()
    if request.method == "POST":
        franchise = Franchise.query.get(request.form.get("franchise_id") or 0)
        claim_date = _month_from(request.form.get("claim_date")) if request.form.get("claim_date") else None
        case = InsuranceClaimCase(
            claim_ref=request.form.get("claim_ref") or f"IC-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}",
            franchise_id=franchise.id if franchise else None, franchise_name=franchise.business_name if franchise else request.form.get("franchise_name", ""),
            claimant_name=request.form.get("claimant_name", ""), policy_number=request.form.get("policy_number", ""),
            id_number=request.form.get("id_number", ""), claim_type=request.form.get("claim_type", "Funeral Claim"),
            claim_date=claim_date, date_of_death=_month_from(request.form.get("date_of_death")) if request.form.get("date_of_death") else None,
            claim_amount=_clean_money(request.form.get("claim_amount")), status=request.form.get("status", "Open"),
            priority=request.form.get("priority", "Normal"), notes=request.form.get("notes", ""), created_by_id=current_user.id
        )
        db.session.add(case); db.session.commit()
        log_action("insurance_claim_create", "Insurance Claims", f"Created claim {case.claim_ref}")
        flash("Claim created.", "success")
        return redirect(url_for("insurance_claims.view_claim", claim_id=case.id))
    return render_template("insurance_claims/claim_form.html", case=None, franchises=franchises)


@insurance_claims_bp.route("/claims/<int:claim_id>", methods=["GET", "POST"])
@login_required
def view_claim(claim_id):
    denied = _require("insurance_claims:view")
    if denied: return denied
    case = InsuranceClaimCase.query.get_or_404(claim_id)
    franchises = _selected_franchise_options()
    if request.method == "POST":
        denied = _require("insurance_claims:edit")
        if denied: return denied
        franchise = Franchise.query.get(request.form.get("franchise_id") or 0)
        case.franchise_id = franchise.id if franchise else None
        case.franchise_name = franchise.business_name if franchise else request.form.get("franchise_name", "")
        case.claimant_name = request.form.get("claimant_name", "")
        case.policy_number = request.form.get("policy_number", "")
        case.id_number = request.form.get("id_number", "")
        case.claim_type = request.form.get("claim_type", "Funeral Claim")
        case.claim_date = _month_from(request.form.get("claim_date")) if request.form.get("claim_date") else None
        case.date_of_death = _month_from(request.form.get("date_of_death")) if request.form.get("date_of_death") else None
        case.claim_amount = _clean_money(request.form.get("claim_amount"))
        old_status = case.status
        case.status = request.form.get("status", "Open")
        case.priority = request.form.get("priority", "Normal")
        case.notes = request.form.get("notes", "")
        if case.status == "Closed" and old_status != "Closed":
            case.closed_at = datetime.now(timezone.utc)
        db.session.commit()
        log_action("insurance_claim_update", "Insurance Claims", f"Updated claim {case.claim_ref}")
        flash("Claim updated.", "success")
        return redirect(url_for("insurance_claims.view_claim", claim_id=case.id))
    return render_template("insurance_claims/claim_form.html", case=case, franchises=franchises)


@insurance_claims_bp.route("/claims/<int:claim_id>/note", methods=["POST"])
@login_required
def add_note(claim_id):
    denied = _require("insurance_claims:edit")
    if denied: return denied
    case = InsuranceClaimCase.query.get_or_404(claim_id)
    note = request.form.get("note", "").strip()
    if note:
        db.session.add(InsuranceClaimNote(claim_id=case.id, user_id=current_user.id, user_email=current_user.email, note=note))
        db.session.commit()
        flash("Note added.", "success")
    return redirect(url_for("insurance_claims.view_claim", claim_id=case.id))


@insurance_claims_bp.route("/claims/<int:claim_id>/attachments", methods=["POST"])
@login_required
def upload_attachment(claim_id):
    denied = _require("insurance_claims:edit")
    if denied: return denied
    case = InsuranceClaimCase.query.get_or_404(claim_id)
    file = request.files.get("file")
    if file and file.filename:
        folder = _storage_root() / "claim_attachments" / str(case.id)
        folder.mkdir(parents=True, exist_ok=True)
        filename = secure_filename(file.filename)
        stored = f"{secrets.token_hex(8)}_{filename}"
        path = folder / stored
        file.save(path)
        db.session.add(InsuranceClaimAttachment(claim_id=case.id, filename=filename, stored_filename=stored, file_path=str(path), content_type=file.mimetype or "", size_bytes=path.stat().st_size, uploaded_by_id=current_user.id))
        db.session.commit()
        flash("Attachment uploaded.", "success")
    return redirect(url_for("insurance_claims.view_claim", claim_id=case.id))


@insurance_claims_bp.route("/attachments/<int:attachment_id>/download")
@login_required
def download_attachment(attachment_id):
    denied = _require("insurance_claims:view")
    if denied: return denied
    attachment = InsuranceClaimAttachment.query.get_or_404(attachment_id)
    return send_file(attachment.file_path, as_attachment=True, download_name=attachment.filename)


@insurance_claims_bp.route("/report.csv")
@login_required
def report_csv():
    denied = _require("insurance_claims:export")
    if denied: return denied
    rows = InsurancePolicyMonthlyRaw.query.order_by(InsurancePolicyMonthlyRaw.import_month.desc(), InsurancePolicyMonthlyRaw.franchise_name).all()
    def generate():
        yield "Franchise,Month,Retail Premium,Risk Premium,Claims,Claim Count,Claim Ratio\n"
        claim_lookup = {(c.claims_franchise_name, c.claim_month): c for c in InsuranceClaimsMonthlyRaw.query.all()}
        for p in rows:
            c = claim_lookup.get((p.franchise_name, p.import_month))
            claims = Decimal(c.claims_amount or 0) if c else Decimal("0")
            count = Decimal(c.claim_count or 0) if c else Decimal("0")
            ratio = (claims / Decimal(p.risk_premium or 0) * Decimal("100")) if p.risk_premium else Decimal("0")
            yield f'"{p.franchise_name}",{p.import_month},{p.retail_premium},{p.risk_premium},{claims},{count},{ratio:.2f}%\n'
    return Response(generate(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=insurance_claims_report.csv"})
