import hashlib
import os
from pathlib import Path
from werkzeug.utils import secure_filename


def manuals_storage_root(app):
    configured = (app.config.get("MANUALS_STORAGE_ROOT") or os.environ.get("MANUALS_STORAGE_ROOT") or "").strip()
    if configured:
        return Path(configured)
    if os.path.exists("/var/data"):
        return Path("/var/data") / "mff_manuals"
    return Path(app.instance_path) / "mff_manuals"


def seed_root(app):
    return Path(app.root_path) / "manuals_seed"


def ensure_pdf_storage(app):
    root = manuals_storage_root(app)
    (root / "manuals").mkdir(parents=True, exist_ok=True)
    (root / "indexes").mkdir(parents=True, exist_ok=True)
    return root


def save_pdf(app, upload_file, folder, prefix="document"):
    root = ensure_pdf_storage(app) / folder
    filename = secure_filename(upload_file.filename or f"{prefix}.pdf") or f"{prefix}.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    stem, ext = os.path.splitext(filename)
    candidate = filename
    i = 2
    while (root / candidate).exists():
        candidate = f"{stem}-{i}{ext}"
        i += 1
    target = root / candidate
    sha = hashlib.sha256()
    with open(target, "wb") as fh:
        while True:
            chunk = upload_file.stream.read(8192)
            if not chunk:
                break
            sha.update(chunk)
            fh.write(chunk)
    return candidate, str(target), sha.hexdigest()


def resolve_storage_path(app, storage_path):
    if not storage_path:
        return None
    p = Path(storage_path)
    if p.is_absolute():
        return p
    return Path(app.root_path).parent / storage_path
