"""Persistent job queue for long-running Martins system work.

The queue is stored in PostgreSQL so import/progress state survives Render restarts.
Jobs can be processed from the Operations Centre or by running the CLI worker.
"""
from __future__ import annotations

import json
import os
import socket
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from flask import current_app
from flask_login import current_user

from app.extensions import db
from app.models import ImportJob, ImportJobLog, WorkerHeartbeat

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



def register_worker_heartbeat(
    worker_id: str = "worker",
    *,
    queue_name: str = "default",
    status: str = "idle",
    current_job_id: Optional[int] = None,
    message: str = "",
    commit: bool = True,
) -> WorkerHeartbeat:
    """Create or update a persistent worker heartbeat row.

    Render worker containers can restart or move. This row gives Admin a clear
    answer to "is the background worker alive?" and which job it is processing.
    """
    now = utcnow()
    worker_id = (worker_id or "worker")[:120]
    hb = WorkerHeartbeat.query.filter_by(worker_id=worker_id).first()
    if not hb:
        hb = WorkerHeartbeat(worker_id=worker_id, started_at=now)
        db.session.add(hb)
    hb.queue_name = (queue_name or "default")[:80]
    hb.status = (status or "idle")[:30]
    hb.current_job_id = current_job_id
    hb.hostname = socket.gethostname()[:160]
    hb.process_id = os.getpid()
    hb.last_message = (message or "")[:255]
    hb.heartbeat_at = now
    hb.stopped_at = None if hb.status not in {"stopped", "offline"} else now
    if commit:
        db.session.commit()
    return hb


def stop_worker_heartbeat(worker_id: str = "worker", *, message: str = "Worker stopped", commit: bool = True) -> Optional[WorkerHeartbeat]:
    hb = WorkerHeartbeat.query.filter_by(worker_id=(worker_id or "worker")[:120]).first()
    if hb:
        hb.status = "stopped"
        hb.current_job_id = None
        hb.last_message = (message or "Worker stopped")[:255]
        hb.heartbeat_at = utcnow()
        hb.stopped_at = hb.heartbeat_at
        if commit:
            db.session.commit()
    return hb


def worker_heartbeat_rows(limit: int = 20) -> list[WorkerHeartbeat]:
    return WorkerHeartbeat.query.order_by(WorkerHeartbeat.heartbeat_at.desc()).limit(limit).all()

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
    if getattr(job, "locked_by", None):
        try:
            register_worker_heartbeat(
                job.locked_by,
                queue_name=getattr(job, "queue_name", "default") or "default",
                status=status or job.status or "running",
                current_job_id=job.id,
                message=message or job.message or "Job heartbeat",
                commit=False,
            )
        except Exception:
            # The job heartbeat must never fail the import itself.
            current_app.logger.debug("Worker heartbeat update skipped", exc_info=True)
    if status in JOB_STATUSES_DONE:
        job.finished_at = utcnow()
        job.locked_at = None
        job.locked_by = None
        if status == "completed":
            job.current_step = job.total_steps
            job.progress_percent = 100
        try:
            from app.events import emit_event
            emit_event(
                f"job.{status}",
                source="jobs.update_job_progress",
                title=f"Job {job.id} {status}",
                message=job.message or "",
                payload={"job_id": job.id, "kind": job.kind, "status": status, "progress": job.progress_percent},
                import_job_id=job.id,
                aggregate_type="import_job",
                aggregate_id=job.id,
                commit=False,
            )
        except Exception:
            current_app.logger.debug("Event emission skipped for job completion", exc_info=True)
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
    try:
        from app.events import emit_event
        emit_event(
            "job.failed" if job.status == "failed" else "job.retry_scheduled",
            source="jobs.fail_job",
            title=f"Job {job.id} {job.status}",
            message=job.message or message,
            payload={"job_id": job.id, "kind": job.kind, "status": job.status, "attempts": attempts, "max_attempts": max_attempts},
            import_job_id=job.id,
            aggregate_type="import_job",
            aggregate_id=job.id,
            commit=False,
        )
    except Exception:
        current_app.logger.debug("Event emission skipped for job failure", exc_info=True)
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
    try:
        register_worker_heartbeat(worker_id, queue_name=queue_name, status="running", current_job_id=job.id, message=f"Claimed job {job.id}", commit=False)
    except Exception:
        current_app.logger.debug("Worker heartbeat claim update skipped", exc_info=True)
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
        completed_worker_id = job.locked_by or worker_id
        job.locked_at = None
        job.locked_by = None
        try:
            register_worker_heartbeat(completed_worker_id, queue_name=getattr(job, "queue_name", "default") or "default", status="idle", current_job_id=None, message=f"Completed job {job.id}", commit=False)
        except Exception:
            current_app.logger.debug("Worker heartbeat completion update skipped", exc_info=True)
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


def release_stale_jobs(stale_after_minutes: int = 15, *, worker_id: str = "system") -> int:
    """Release running jobs whose heartbeat is stale.

    Render can restart a web or worker container while a job is locked.  Because
    the queue is persistent, stale locks must be returned to the queue so an
    Admin or worker can continue processing safely.
    """
    cutoff = utcnow() - timedelta(minutes=max(int(stale_after_minutes or 15), 1))
    stale_jobs = (ImportJob.query
                  .filter(ImportJob.status.in_(["running", "processing", "validating", "publishing"]))
                  .filter((ImportJob.heartbeat_at.is_(None)) | (ImportJob.heartbeat_at < cutoff))
                  .all())
    for job in stale_jobs:
        job.status = "queued"
        job.message = f"Released stale lock by {worker_id}."[:255]
        job.available_at = utcnow()
        job.locked_at = None
        job.locked_by = None
        add_job_log(job, "warning", "Stale job lock released", {"worker_id": worker_id, "stale_after_minutes": stale_after_minutes}, commit=False)
    if stale_jobs:
        db.session.commit()
    return len(stale_jobs)


def queue_stats(queue_name: str = "default") -> dict:
    """Return lightweight queue status counts for dashboards and workers."""
    rows = (db.session.query(ImportJob.status, db.func.count(ImportJob.id))
            .filter((ImportJob.queue_name == queue_name) | (ImportJob.queue_name.is_(None)))
            .group_by(ImportJob.status)
            .all())
    stats = {status: int(count or 0) for status, count in rows}
    stats["active"] = sum(stats.get(status, 0) for status in JOB_STATUSES_ACTIVE)
    stats["done"] = sum(stats.get(status, 0) for status in JOB_STATUSES_DONE)
    return stats


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
