import os
import re
from pypdf import PdfReader

ALLOWED_FICA_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}
MAX_FICA_UPLOAD_BYTES = 10 * 1024 * 1024
MIN_FICA_UPLOAD_BYTES = 1024

ADDRESS_WORDS = {
    "street", "str", "road", "rd", "avenue", "ave", "drive", "dr", "lane", "ln",
    "crescent", "close", "unit", "flat", "complex", "estate", "building", "po box",
    "suburb", "city", "town", "province", "postal", "code", "south africa"
}
BANK_WORDS = {"bank", "account", "statement", "branch", "debit", "savings", "cheque"}
PERMIT_WORDS = {"permit", "visa", "passport", "republic", "home affairs"}


def digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def extension_for(filename):
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def extract_pdf_text(path, max_pages=3):
    try:
        reader = PdfReader(path)
        parts = []
        for page in reader.pages[:max_pages]:
            parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()
    except Exception:
        return ""


def looks_like_address(text):
    lower = (text or "").lower()
    if not lower:
        return False
    has_number = bool(re.search(r"\b\d{1,5}\b", lower))
    has_word = any(word in lower for word in ADDRESS_WORDS)
    return has_number and has_word


def validate_fica_upload(path, original_filename, document_type, application):
    """Return (status, notes). Status is Rejected for hard failures, otherwise Needs Review.

    The system deliberately does not auto-approve identity/FICA files. It performs basic
    machine checks, records what it found, and leaves final approval to staff/QA.
    """
    ext = extension_for(original_filename or path)
    if ext not in ALLOWED_FICA_EXTENSIONS:
        return "Rejected", "File type not allowed. Only PDF, JPG, PNG or WEBP files are accepted."
    if not os.path.exists(path):
        return "Rejected", "Upload could not be saved."
    size = os.path.getsize(path)
    if size < MIN_FICA_UPLOAD_BYTES:
        return "Rejected", "File is too small or empty. Please upload a clear document."
    if size > MAX_FICA_UPLOAD_BYTES:
        return "Rejected", "File is too large. Maximum size is 10 MB."

    notes = [f"File accepted for review ({ext.upper()}, {round(size / 1024, 1)} KB)."]

    if ext != "pdf":
        notes.append("Image uploads require staff verification because OCR is not configured on this server.")
        return "Needs Review", " ".join(notes)

    text = extract_pdf_text(path)
    normalized_text = re.sub(r"\s+", " ", text).strip()
    if not normalized_text:
        notes.append("No readable text found in the PDF. It may be a scanned document and must be checked manually.")
        return "Needs Review", " ".join(notes)

    client_id = digits(getattr(application, "id_number", ""))
    client_name_bits = [
        str(getattr(application, "first_names", "") or "").strip().lower(),
        str(getattr(application, "surname", "") or "").strip().lower(),
    ]
    lower = normalized_text.lower()

    if document_type == "id_copy":
        if client_id and client_id in digits(normalized_text):
            notes.append("Client ID number was found in the PDF text.")
        else:
            notes.append("Client ID number was not found in readable PDF text. Staff must verify this is the correct ID copy.")
    elif document_type == "proof_of_address":
        if looks_like_address(normalized_text):
            notes.append("Address-like text was found in the PDF.")
        else:
            notes.append("No clear address-like text was found. Staff must verify proof of address.")
        if any(bit and bit in lower for bit in client_name_bits):
            notes.append("Client name/surname appears in the PDF text.")
        else:
            notes.append("Client name/surname was not found in readable text.")
    elif document_type == "bank_statement":
        if any(word in lower for word in BANK_WORDS):
            notes.append("Banking-related wording was found.")
        else:
            notes.append("No clear banking wording was found. Staff must verify this file.")
    elif document_type in {"passport", "permit_visa"}:
        if any(word in lower for word in PERMIT_WORDS):
            notes.append("Passport/permit wording was found.")
        else:
            notes.append("No clear passport/permit wording was found. Staff must verify this file.")

    return "Needs Review", " ".join(notes)
