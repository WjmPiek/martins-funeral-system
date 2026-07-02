"""Persistent job queue for long-running Martins system work.

The queue is stored in PostgreSQL so import/progress state survives Render restarts.
Jobs can be processed from the Operations Centre or by running the CLI worker.
"""
from __future__ import annotations

import json
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from flask import current_app
from flask_login import current_user

from app.extensions import db
from app.models import ImportJob, ImportJobLog

JOB_STATUSES_ACTIVE = {"queued", "running", "processing", "validating", "publishing"}
JOB_STATUSES_DONE = {"completed", "failed", "needs_review", "cancelled"}

_JOB_HANDLERS: Dict[str, Callable[[ImportJob], Any]] = {}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_loads(value: Optional[str], default: Any = None) -> Any:
    if not value:
        return {} if default is None else default
    try:
        return json.loads(value)
    except Exception:
        return {} if default is None else default


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, default=str)


def register_job_handler(kind: str):
    """Decorator used by modules to register persistent job handlers."""
    def decorator(func: Callable[[ImportJob], Any]):
        _JOB_HANDLERS[kind] = func
        return func
    return decorator


def job_payload(job: ImportJob) -> dict:
    return _json_loads(getattr(job, "payload_json", "") or "{}")


def job_result(job: ImportJob) -> dict:
    return _json_loads(getattr(job, "result_json", "") or "{}")


def add_job_log(job: ImportJob, level: str, message: str, data: Optional[dict] = None, commit: bool = True) -> ImportJobLog:
    entry = ImportJobLog(
        import_job_id=job.id,
        level=(level or "info")[:20],
        message=str(message or "")[:1000],
        data_json=_json_dumps(data)[:8000] if data else "",
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
    return entry


def enqueue_job(
    kind: str,
    *,
    filename: str = "",
    payload: Optional[dict] = None,
    total_steps: int = 100,
    queue_name: str = "default",
    priority: int = 100,
    available_at: Optional[datetime] = None,
    created_by_id: Optional[int] = None,
) -> ImportJob:
    """Create a durable queued job.

    The old import progress model is reused so existing Import Centre screens can
    continue to show progress. Additional queue fields are added by v92.
    """
    if created_by_id is None:
        try:
            created_by_id = current_user.id if getattr(current_user, "is_authenticated", False) else None
        except Exception:
            created_by_id = None
    job = ImportJob(
        kind=kind,
        filename=filename or "",
        status="queued",
        message="Queued and waiting to run.",
        total_steps=max(int(total_steps or 100), 1),
        current_step=0,
        progress_percent=0,
        started_at=utcnow(),
        created_by_id=created_by_id,
    )
    # v92 nullable columns. setattr keeps older code import-safe before migration.
    job.queue_name = queue_name or "default"
    job.priority = int(priority or 100)
    job.available_at = available_at or utcnow()
    job.payload_json = _json_dumps(payload or {})[:20000]
    job.attempts = 0
    db.session.add(job)
    db.session.commit()
    add_job_log(job, "info", "Job queued", {"kind": kind, "filename": filename}, commit=True)
    return job


def update_job_progress(job: ImportJob, step: Optional[int] = None, message: Optional[str] = None, status: Optional[str] = None, data: Optional[dict] = None, commit: bool = True) -> ImportJob:
    if step is not None:
        job.current_step = max(0, int(step))
        total = max(int(job.total_steps or 100), 1)
        job.progress_percent = min(100, int((job.current_step / total) * 100))
    if message is not None:
        job.message = str(message)[:255]
        add_job_log(job, "info", message, data=data, commit=False)
    if status is not None:
        job.status = status
    job.heartbeat_at = utcnow()
    if status in JOB_STATUSES_DONE:
        job.finished_at = utcnow()
        job.locked_at = None
        job.locked_by = None
        if status == "completed":
            job.current_step = job.total_steps
            job.progress_percent = 100
    if commit:
        db.session.commit()
    return job


def fail_job(job: ImportJob, exc: Exception | str, *, retryable: bool = True, commit: bool = True) -> ImportJob:
    message = str(exc)[:255]
    max_attempts = int(getattr(job, "max_attempts", 1) or 1)
    attempts = int(getattr(job, "attempts", 0) or 0)
    if retryable and attempts < max_attempts:
        job.status = "queued"
        job.message = f"Retry scheduled after failure: {message}"[:255]
        job.available_at = utcnow() + timedelta(minutes=min(30, attempts * 2 + 1))
        job.locked_at = None
        job.locked_by = None
        add_job_log(job, "warning", job.message, {"attempts": attempts, "max_attempts": max_attempts}, commit=False)
    else:
        job.status = "failed"
        job.message = message
        job.finished_at = utcnow()
        job.locked_at = None
        job.locked_by = None
        job.error_json = _json_dumps({"error": str(exc), "traceback": traceback.format_exc()})[:20000]
        add_job_log(job, "error", message, commit=False)
    if commit:
        db.session.commit()
    return job


def claim_next_job(queue_name: str = "default", worker_id: str = "worker") -> Optional[ImportJob]:
    """Claim one available job using a PostgreSQL row lock when possible."""
    now = utcnow()
    try:
        query = (ImportJob.query
                 .filter(ImportJob.status == "queued")
                 .filter((ImportJob.queue_name == queue_name) | (ImportJob.queue_name.is_(None)))
                 .filter((ImportJob.available_at.is_(None)) | (ImportJob.available_at <= now))
                 .order_by(ImportJob.priority.asc(), ImportJob.started_at.asc())
                 .with_for_update(skip_locked=True))
        job = query.first()
    except Exception:
        db.session.rollback()
        job = (ImportJob.query
               .filter(ImportJob.status == "queued")
               .order_by(ImportJob.priority.asc(), ImportJob.started_at.asc())
               .first())
    if not job:
        return None
    job.status = "running"
    job.locked_at = now
    job.locked_by = worker_id[:120]
    job.heartbeat_at = now
    job.attempts = int(getattr(job, "attempts", 0) or 0) + 1
    add_job_log(job, "info", f"Job claimed by {worker_id}", commit=False)
    db.session.commit()
    return job


def run_job(job: ImportJob, *, worker_id: str = "worker") -> ImportJob:
    handler = _JOB_HANDLERS.get(job.kind)
    if not handler:
        return fail_job(job, f"No job handler registered for kind '{job.kind}'", retryable=False)
    try:
        update_job_progress(job, status="running", message="Job started", commit=True)
        result = handler(job)
        if job.status not in {"needs_review", "failed", "cancelled"}:
            job.status = "completed"
            job.message = "Job completed successfully."
            job.current_step = job.total_steps
            job.progress_percent = 100
            job.finished_at = utcnow()
        job.result_json = _json_dumps(result if isinstance(result, dict) else {"result": result})[:20000]
        job.locked_at = None
        job.locked_by = None
        add_job_log(job, "info", "Job completed", commit=False)
        db.session.commit()
    except Exception as exc:
        current_app.logger.exception("Persistent job failed: %s", exc)
        fail_job(job, exc, retryable=True, commit=True)
    return job


def run_next_job(queue_name: str = "default", worker_id: str = "worker") -> Optional[ImportJob]:
    job = claim_next_job(queue_name=queue_name, worker_id=worker_id)
    if not job:
        return None
    return run_job(job, worker_id=worker_id)


def retry_job(job: ImportJob, *, reset_progress: bool = True) -> ImportJob:
    if reset_progress:
        job.current_step = 0
        job.progress_percent = 0
    job.status = "queued"
    job.message = "Queued for retry."
    job.available_at = utcnow()
    job.finished_at = None
    job.locked_at = None
    job.locked_by = None
    add_job_log(job, "info", "Job queued for retry", commit=False)
    db.session.commit()
    return job


def cancel_job(job: ImportJob, reason: str = "Cancelled by Admin") -> ImportJob:
    if job.status not in JOB_STATUSES_DONE:
        job.status = "cancelled"
        job.message = reason[:255]
        job.finished_at = utcnow()
        job.locked_at = None
        job.locked_by = None
        add_job_log(job, "warning", reason, commit=False)
        db.session.commit()
    return job


# Placeholder handler used to test the queue without running an import.
@register_job_handler("system_noop")
def _noop(job: ImportJob) -> dict:
    update_job_progress(job, 50, "No-op job running", commit=True)
    update_job_progress(job, 100, "No-op job done", commit=True)
    return {"ok": True}
