from datetime import datetime, timezone

from flask import current_app
from flask_login import current_user

from app.extensions import db
from app.models import ImportJob


def start_import_job(kind, filename='', total_steps=100):
    job = ImportJob(
        kind=kind,
        filename=filename or '',
        status='running',
        message='Starting import...',
        total_steps=max(int(total_steps or 100), 1),
        current_step=0,
        progress_percent=0,
        started_at=datetime.now(timezone.utc),
        created_by_id=(current_user.id if getattr(current_user, 'is_authenticated', False) else None),
    )
    db.session.add(job)
    db.session.commit()
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
    if extra is not None:
        job.extra_json = str(extra)[:4000]
    if status in {'completed', 'failed', 'needs_review'}:
        job.finished_at = datetime.now(timezone.utc)
        if status == 'completed':
            job.current_step = job.total_steps
            job.progress_percent = 100
    if commit:
        try:
            db.session.commit()
        except Exception as exc:
            current_app.logger.exception('Could not update import progress: %s', exc)
            db.session.rollback()
    return job
