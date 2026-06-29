from app.models import ClientFicaDocument, DocumentSignature

SIGNATURE_DOCUMENTS = [
    ("application", "Application Form"),
    ("popia", "POPIA Consent"),
    ("disclosure", "Policy Disclosure"),
    ("welcome", "Welcome Pack Acknowledgement"),
]

FICA_LABELS = {
    "id_copy": "South African ID Copy",
    "proof_of_address": "Proof of Address",
    "bank_statement": "Bank Statement / Bank Confirmation",
    "passport": "Passport Copy",
    "permit_visa": "Permit / Visa",
}


def _digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def client_is_sa(application):
    return len(_digits(getattr(application, "id_number", ""))) == 13


def is_debit_order(application):
    return "debit" in str(getattr(application, "payment_method", "") or "").lower()


def required_fica_types(application):
    required = ["id_copy" if client_is_sa(application) else "passport", "proof_of_address"]
    if not client_is_sa(application):
        required.append("permit_visa")
    if is_debit_order(application):
        required.append("bank_statement")
    return required


def document_summary(application):
    signed_rows = DocumentSignature.query.filter_by(application_id=application.id).all()
    signed_types = {row.document_type: row for row in signed_rows}
    fica_docs = ClientFicaDocument.query.filter_by(application_id=application.id).order_by(ClientFicaDocument.uploaded_at.desc()).all()

    rows = []
    for key, label in SIGNATURE_DOCUMENTS:
        is_signed = key in signed_types
        rows.append({
            "group": "Signature",
            "key": key,
            "label": label,
            "required": True,
            "status": "Signed" if is_signed else "Missing",
            "badge": "success" if is_signed else "danger",
            "signed_at": signed_types[key].signed_at if is_signed else None,
            "document": signed_types.get(key),
        })

    by_type = {}
    for doc in fica_docs:
        by_type.setdefault(doc.document_type, []).append(doc)

    for key in required_fica_types(application):
        docs = by_type.get(key, [])
        latest = docs[0] if docs else None
        if not latest:
            status, badge = "Missing", "danger"
        elif latest.status in {"Reviewed", "Approved"}:
            status, badge = "Approved", "success"
        elif latest.status == "Rejected":
            status, badge = "Rejected", "danger"
        else:
            status, badge = "Needs Review", "warning"
        rows.append({
            "group": "FICA",
            "key": key,
            "label": FICA_LABELS.get(key, key.replace("_", " ").title()),
            "required": True,
            "status": status,
            "badge": badge,
            "uploaded_at": latest.uploaded_at if latest else None,
            "document": latest,
            "all_documents": docs,
        })

    # Show extra uploaded FICA documents that are not currently required, so nothing is hidden.
    for key, docs in by_type.items():
        if key in required_fica_types(application):
            continue
        latest = docs[0]
        rows.append({
            "group": "FICA",
            "key": key,
            "label": FICA_LABELS.get(key, key.replace("_", " ").title()) + " (extra)",
            "required": False,
            "status": latest.status or "Received",
            "badge": "secondary",
            "uploaded_at": latest.uploaded_at,
            "document": latest,
            "all_documents": docs,
        })

    missing = [row for row in rows if row["required"] and row["status"] in {"Missing", "Rejected"}]
    pending_review = [row for row in rows if row["status"] == "Needs Review"]
    complete = not missing and not pending_review
    return {
        "rows": rows,
        "missing": missing,
        "pending_review": pending_review,
        "complete": complete,
        "completion_percent": round(((len(rows) - len(missing) - len(pending_review)) / len(rows)) * 100) if rows else 0,
        "required_fica_types": required_fica_types(application),
        "fica_labels": FICA_LABELS,
    }
