import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from markupsafe import Markup, escape
from pypdf import PdfReader
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from app.extensions import db
from app.models import MFFManual, MFFManualVersion, MFFIndexDocument, MFFManualAcknowledgement
from app.manuals.storage import save_pdf, resolve_storage_path, seed_root

manuals_bp = Blueprint("manuals", __name__, url_prefix="/manuals")


def _can(action="view"):
    return current_user.is_authenticated and current_user.has_permission(f"manuals:{action}")


def _require(action="view"):
    if not _can(action):
        flash("You do not have permission to access Manuals.", "danger")
        return False
    return True


def _is_admin():
    return current_user.has_permission("manuals:manage") or current_user.has_permission("system_administration:view")


def _latest(manual_id):
    return (MFFManualVersion.query.filter_by(manual_id=manual_id, is_published=True)
            .order_by(MFFManualVersion.uploaded_at.desc(), MFFManualVersion.id.desc()).first())


def _normalize_doc_name(value):
    value = (value or "").lower()
    value = re.sub(r"\.pdf$", "", value)
    value = value.replace("&", " and ")
    value = re.sub(r"\b(index|manual|module|latest|version|final|copy)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _infer_manual(name):
    normalized_name = _normalize_doc_name(name)
    scored = []
    for manual in MFFManual.query.order_by(MFFManual.title.asc()).all():
        title = _normalize_doc_name(manual.title)
        if not title:
            continue
        score = 0
        if normalized_name == title:
            score = 100
        elif title in normalized_name:
            score = 80
        elif normalized_name in title:
            score = 70
        else:
            overlap = len(set(normalized_name.split()) & set(title.split()))
            score = overlap * 10
        if score:
            scored.append((score, manual))
    scored.sort(key=lambda item: (item[0], len(item[1].title)), reverse=True)
    return scored[0][1] if scored else None


def _seed_if_empty():
    if MFFManual.query.first() or MFFIndexDocument.query.first():
        return
    root = seed_root(current_app)
    manuals_root = root / "MANUALS"
    indexes_root = root / "INDEX"
    if manuals_root.exists():
        for pdf in sorted(manuals_root.glob("*.pdf")):
            title = pdf.stem.replace("_", " ").replace("  ", " ").strip()
            manual = MFFManual(title=title, confidentiality_note="Confidential - internal use only")
            db.session.add(manual); db.session.flush()
            v = MFFManualVersion(manual_id=manual.id, version_label="v1.0", filename=pdf.name, storage_path=str(pdf), sha256="seed", uploaded_by_user_id=None, is_published=True)
            db.session.add(v)
    if indexes_root.exists():
        db.session.flush()
        for pdf in sorted(indexes_root.glob("*.pdf")):
            linked = _infer_manual(pdf.stem)
            doc = MFFIndexDocument(title=pdf.stem.replace("_", " "), filename=pdf.name, storage_path=str(pdf), manual_id=linked.id if linked else None, uploaded_by_user_id=None, is_active=True)
            db.session.add(doc)
    db.session.commit()


def _safe_pdf_response(path, download_name, as_attachment=False):
    if not path or not Path(path).exists():
        abort(404)
    resp = send_file(path, mimetype="application/pdf", as_attachment=as_attachment, download_name=download_name)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@lru_cache(maxsize=256)
def _extract_pages(path, mtime):
    pages = []
    try:
        reader = PdfReader(path)
        for idx, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append((idx, re.sub(r"\s+", " ", text).strip()))
    except Exception:
        return []
    return pages


def _snippet(text, query, radius=110):
    if not text:
        return ""
    low = text.lower(); q = query.lower(); pos = low.find(q)
    if pos < 0:
        sample = text[:radius*2]
        return Markup(escape(sample + ("…" if len(text) > len(sample) else "")))
    start=max(0,pos-radius); end=min(len(text),pos+len(query)+radius)
    before = "…" if start else ""; after = "…" if end < len(text) else ""
    part = text[start:end]
    highlighted = re.sub(re.escape(query), lambda m: f"<mark>{escape(m.group(0))}</mark>", escape(part), flags=re.I)
    return Markup(before + highlighted + after)


def _search_documents(query, scope="all"):
    results=[]
    q=(query or "").strip()
    if not q: return results
    items=[]
    if scope in ("all","manuals"):
        versions = MFFManualVersion.query.filter_by(is_published=True).all()
        items += [("manual", v.manual.title if v.manual else v.filename, v.version_label, v.filename, v.storage_path, url_for("manuals.download_version", version_id=v.id)) for v in versions]
    if scope in ("all","indexes"):
        docs = MFFIndexDocument.query.filter_by(is_active=True).all()
        items += [("index", d.title, "Index document", d.filename, d.storage_path, url_for("manuals.open_index", document_id=d.id)) for d in docs]
    for kind,title,subtitle,filename,path,url in items:
        p=resolve_storage_path(current_app, path)
        if not p or not p.exists(): continue
        page_hits=[]; total=0
        for page_no,text in _extract_pages(str(p), p.stat().st_mtime):
            count=text.lower().count(q.lower())
            if count:
                total += count
                page_hits.append({"page_number":page_no,"match_count":count,"snippet":_snippet(text,q)})
        if total or q.lower() in title.lower() or q.lower() in filename.lower():
            results.append({"kind":kind,"title":title,"subtitle":subtitle,"filename":filename,"url":url,"total_matches":total,"page_results":page_hits[:8],"extra_pages":max(0,len(page_hits)-8),"snippet":page_hits[0]["snippet"] if page_hits else "Filename/title match"})
    results.sort(key=lambda r: (r["total_matches"], r["title"]), reverse=True)
    return results


@manuals_bp.before_request
def _before():
    if current_user.is_authenticated:
        try:
            _seed_if_empty()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Manual seed failed")


@manuals_bp.route("/")
@login_required
def index():
    if not _require("view"):
        return redirect(url_for("dashboard.index"))
    manuals = MFFManual.query.order_by(MFFManual.title.asc()).all()
    latest_map = {m.id: _latest(m.id) for m in manuals}
    indexes_count = MFFIndexDocument.query.filter_by(is_active=True).count()
    acknowledgements = MFFManualAcknowledgement.query.count()
    return render_template("manuals/index.html", manuals=manuals, latest_map=latest_map, indexes_count=indexes_count, acknowledgements=acknowledgements, is_manual_admin=_is_admin())


@manuals_bp.route("/library")
@login_required
def library():
    if not _require("view"):
        return redirect(url_for("dashboard.index"))
    manuals = MFFManual.query.order_by(MFFManual.title.asc()).all()
    latest_map = {m.id: _latest(m.id) for m in manuals}
    return render_template("manuals/library.html", manuals=manuals, latest_map=latest_map, is_manual_admin=_is_admin())


@manuals_bp.route("/indexes")
@login_required
def indexes():
    if not _require("view"):
        return redirect(url_for("dashboard.index"))
    docs = MFFIndexDocument.query.filter_by(is_active=True).order_by(MFFIndexDocument.title.asc()).all()
    return render_template("manuals/indexes.html", documents=docs, is_manual_admin=_is_admin())


@manuals_bp.route("/search")
@login_required
def search():
    if not _require("view"):
        return redirect(url_for("dashboard.index"))
    query=(request.args.get("q") or "").strip()
    scope=(request.args.get("scope") or "all").strip().lower()
    if scope not in {"all","manuals","indexes"}: scope="all"
    results=_search_documents(query,scope) if query else []
    total_matches=sum(r.get("total_matches") or 0 for r in results)
    return render_template("manuals/search.html", query=query, scope=scope, results=results, total_matches=total_matches, total_files=len(results))


@manuals_bp.post("/search-pdfs")
@login_required
def search_pdfs_api():
    if not _require("view"):
        return jsonify({"ok":False,"message":"Forbidden"}),403
    data=request.get_json(silent=True) or {}
    query=(data.get("query") or request.form.get("query") or "").strip()
    scope=(data.get("scope") or request.form.get("scope") or "all").strip().lower()
    results=_search_documents(query, scope) if query else []
    return jsonify({"pdf_count":len(results),"total_matches":sum(r.get("total_matches") or 0 for r in results),"results":[{"kind":r["kind"],"title":r["title"],"filename":r["filename"],"total_matches":r["total_matches"],"url":r["url"],"snippet":str(r["snippet"])} for r in results]})


@manuals_bp.route("/upload", methods=["GET","POST"])
@login_required
def upload_manual():
    if not _require("manage"):
        return redirect(url_for("manuals.index"))
    if request.method == "POST":
        title=(request.form.get("title") or "").strip(); version=(request.form.get("version_label") or "v1.0").strip(); file=request.files.get("file")
        if not title or not file or not (file.filename or "").lower().endswith(".pdf"):
            flash("Manual title and a PDF file are required.", "danger"); return redirect(url_for("manuals.upload_manual"))
        manual=MFFManual.query.filter_by(title=title).first() or MFFManual(title=title, confidentiality_note="Confidential - internal use only")
        db.session.add(manual); db.session.flush()
        if MFFManualVersion.query.filter_by(manual_id=manual.id, version_label=version).first():
            flash("That version label already exists for this manual.", "danger"); return redirect(url_for("manuals.upload_manual"))
        MFFManualVersion.query.filter_by(manual_id=manual.id).update({"is_published":False})
        filename, storage_path, sha = save_pdf(current_app, file, "manuals", "manual")
        v=MFFManualVersion(manual_id=manual.id, version_label=version, filename=filename, storage_path=storage_path, sha256=sha, uploaded_by_user_id=current_user.id, is_published=True)
        db.session.add(v); db.session.commit(); flash("Manual uploaded and published.", "success")
        return redirect(url_for("manuals.manual_detail", manual_id=manual.id))
    return render_template("manuals/upload_manual.html")


@manuals_bp.route("/indexes/upload", methods=["GET","POST"])
@login_required
def upload_index():
    if not _require("manage"):
        return redirect(url_for("manuals.indexes"))
    manuals=MFFManual.query.order_by(MFFManual.title.asc()).all()
    if request.method == "POST":
        file=request.files.get("file"); title=(request.form.get("title") or "").strip(); manual_id=request.form.get("manual_id") or None
        if not file or not (file.filename or "").lower().endswith(".pdf"):
            flash("A PDF index file is required.", "danger"); return redirect(url_for("manuals.upload_index"))
        filename, storage_path, sha = save_pdf(current_app, file, "indexes", "index")
        linked = db.session.get(MFFManual, int(manual_id)) if manual_id else _infer_manual(title or filename)
        doc=MFFIndexDocument(title=title or Path(filename).stem, filename=filename, storage_path=storage_path, manual_id=linked.id if linked else None, uploaded_by_user_id=current_user.id, is_active=True)
        db.session.add(doc); db.session.commit(); flash("Index uploaded.", "success")
        return redirect(url_for("manuals.indexes"))
    return render_template("manuals/upload_index.html", manuals=manuals)


@manuals_bp.route("/<int:manual_id>")
@login_required
def manual_detail(manual_id):
    if not _require("view"):
        return redirect(url_for("dashboard.index"))
    manual=db.session.get(MFFManual, manual_id) or abort(404)
    latest=_latest(manual.id)
    versions=MFFManualVersion.query.filter_by(manual_id=manual.id).order_by(MFFManualVersion.uploaded_at.desc()).all()
    linked_indexes=MFFIndexDocument.query.filter_by(manual_id=manual.id, is_active=True).all()
    return render_template("manuals/detail.html", manual=manual, latest=latest, versions=versions, linked_indexes=linked_indexes, is_manual_admin=_is_admin())


@manuals_bp.route("/<int:manual_id>/open")
@login_required
def manual_open(manual_id):
    if not _require("view"):
        return redirect(url_for("dashboard.index"))
    latest=_latest(manual_id)
    if not latest:
        flash("No published version available.", "warning"); return redirect(url_for("manuals.library"))
    return redirect(url_for("manuals.view_version", version_id=latest.id))


@manuals_bp.route("/version/<int:version_id>/view")
@login_required
def view_version(version_id):
    if not _require("view"):
        return redirect(url_for("dashboard.index"))
    v=db.session.get(MFFManualVersion, version_id) or abort(404)
    return render_template("manuals/view.html", version=v, back_url=request.args.get("next") or url_for("manuals.manual_detail", manual_id=v.manual_id))


@manuals_bp.route("/version/<int:version_id>/download")
@login_required
def download_version(version_id):
    if not _require("view"):
        return redirect(url_for("dashboard.index"))
    v=db.session.get(MFFManualVersion, version_id) or abort(404)
    path=resolve_storage_path(current_app, v.storage_path)
    return _safe_pdf_response(path, v.filename, as_attachment=(request.args.get("download") == "1"))


@manuals_bp.route("/indexes/<int:document_id>/open")
@login_required
def open_index(document_id):
    if not _require("view"):
        return redirect(url_for("dashboard.index"))
    doc=db.session.get(MFFIndexDocument, document_id) or abort(404)
    path=resolve_storage_path(current_app, doc.storage_path)
    return _safe_pdf_response(path, doc.filename, False)


@manuals_bp.post("/version/<int:version_id>/acknowledge")
@login_required
def acknowledge(version_id):
    if not _require("view"):
        return redirect(url_for("dashboard.index"))
    v=db.session.get(MFFManualVersion, version_id) or abort(404)
    existing=MFFManualAcknowledgement.query.filter_by(manual_version_id=v.id, user_id=current_user.id).first()
    if not existing:
        ack=MFFManualAcknowledgement(manual_version_id=v.id, user_id=current_user.id, attested_name=current_user.full_name, ip_address=request.headers.get("X-Forwarded-For", request.remote_addr) or "", user_agent=(request.headers.get("User-Agent") or "")[:500])
        db.session.add(ack); db.session.commit(); flash("Manual acknowledged.", "success")
    return redirect(url_for("manuals.manual_detail", manual_id=v.manual_id))
