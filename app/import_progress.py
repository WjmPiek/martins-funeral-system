from datetime import datetime, timezone
import json

from flask import current_app
from flask_login import current_user

from app.extensions import db
from app.models import ImportJob


def start_import_job(kind, filename='', total_steps=100, *, status='running', payload=None, queue_name='default'):
    """Create a durable import/job progress record.

    Existing imports still call this for immediate processing.  Phase 7 adds the
    persistent queue fields so the same row can also be retried or processed by
    the worker if the handler is moved out of the request.
    """
    job = ImportJob(
        kind=kind,
        filename=filename or '',
        status=status or 'running',
        message='Queued and waiting to run...' if status == 'queued' else 'Starting import...',
        total_steps=max(int(total_steps or 100), 1),
        current_step=0,
        progress_percent=0,
        started_at=datetime.now(timezone.utc),
        available_at=datetime.now(timezone.utc),
        heartbeat_at=datetime.now(timezone.utc),
        queue_name=queue_name or 'default',
        payload_json=json.dumps(payload or {}, default=str)[:20000] if payload else '',
        created_by_id=(current_user.id if getattr(current_user, 'is_authenticated', False) else None),
    )
    db.session.add(job)
    db.session.commit()
    try:
        from app.jobs import add_job_log
        add_job_log(job, 'info', job.message, {'kind': kind, 'filename': filename}, commit=True)
    except Exception:
        pass
    return job


def update_import_job(job, step=None, message=None, status=None, extra=None, commit=True):
    if not job:
        return None
    if step is not None:
        job.current_step = max(0, int(step))
        total = max(int(job.total_steps or 100), 1)
        job.progress_percent = min(100, int((job.current_step / total) * 100))
    if message is not None:
        job.message = str(message)[:255]
    if status is not None:
        job.status = status
    job.heartbeat_at = datetime.now(timezone.utc)
    if extra is not None:
        try:
            text = json.dumps(extra, default=str) if not isinstance(extra, str) else extra
        except Exception:
            text = str(extra)
        job.extra_json = text[:8000]
        if hasattr(job, 'result_json') and status in {'completed', 'needs_review'}:
            job.result_json = text[:20000]
    if status in {'completed', 'failed', 'needs_review', 'cancelled'}:
        job.finished_at = datetime.now(timezone.utc)
        job.locked_at = None
        job.locked_by = None
        if status == 'completed':
            job.current_step = job.total_steps
            job.progress_percent = 100
    if message is not None:
        try:
            from app.jobs import add_job_log
            add_job_log(job, 'error' if status == 'failed' else 'info', message, commit=False)
        except Exception:
            pass
    if commit:
        try:
            db.session.commit()
        except Exception as exc:
            current_app.logger.exception('Could not update import progress: %s', exc)
            db.session.rollback()
    return job
