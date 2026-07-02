"""Enterprise event bus for Martins Funeral System.

The event bus is intentionally database-backed instead of in-memory so events,
processing state and errors survive Render restarts.  Phase 8 uses this as the
coordination layer between imports, royalties, cache, dashboards, notifications
and future modules such as Attendance and Claims.
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from flask import current_app
from flask_login import current_user

from app.extensions import db
from app.models import EventProcessingLog, EventSubscription, SystemEvent

_EVENT_HANDLERS: Dict[str, list[Callable[[SystemEvent], Any]]] = {}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, default=str)


def _current_user_id() -> Optional[int]:
    try:
        return current_user.id if getattr(current_user, "is_authenticated", False) else None
    except Exception:
        return None


def subscribe(event_type: str):
    """Register a Python handler for a given event type.

    Handlers are intentionally best-effort. The event bus logs failures and keeps
    the original event for retry/replay instead of breaking the user request.
    """
    def decorator(func: Callable[[SystemEvent], Any]):
        _EVENT_HANDLERS.setdefault(event_type, []).append(func)
        return func
    return decorator


def emit_event(
    event_type: str,
    *,
    source: str = "system",
    title: str = "",
    message: str = "",
    payload: Optional[dict] = None,
    priority: int = 100,
    correlation_id: Optional[str] = None,
    aggregate_type: Optional[str] = None,
    aggregate_id: Optional[int] = None,
    import_job_id: Optional[int] = None,
    franchise_id: Optional[int] = None,
    user_id: Optional[int] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    status: str = "pending",
    commit: bool = False,
) -> SystemEvent:
    event = SystemEvent(
        event_type=(event_type or "system.event")[:120],
        source=(source or "system")[:120],
        title=(title or event_type or "System event")[:180],
        message=(message or "")[:800],
        status=(status or "pending")[:30],
        priority=int(priority or 100),
        correlation_id=(correlation_id or "")[:120] or None,
        aggregate_type=(aggregate_type or "")[:80] or None,
        aggregate_id=aggregate_id,
        import_job_id=import_job_id,
        franchise_id=franchise_id,
        user_id=user_id if user_id is not None else _current_user_id(),
        year=year,
        month=month,
        payload_json=_json_dumps(payload or {})[:20000],
        available_at=utcnow(),
    )
    db.session.add(event)
    if commit:
        db.session.commit()
    return event


def log_event_processing(event: SystemEvent, handler: str, status: str, message: str, data: Optional[dict] = None, commit: bool = False) -> EventProcessingLog:
    entry = EventProcessingLog(
        system_event_id=event.id,
        handler=(handler or "event_bus")[:160],
        status=(status or "info")[:30],
        message=(message or "")[:1000],
        data_json=_json_dumps(data or {})[:8000],
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
    return entry


def _handlers_for(event_type: str) -> list[Callable[[SystemEvent], Any]]:
    handlers = list(_EVENT_HANDLERS.get(event_type, []))
    handlers.extend(_EVENT_HANDLERS.get("*", []))
    return handlers


def process_event(event: SystemEvent, *, worker_id: str = "event-worker", commit: bool = True) -> SystemEvent:
    event.locked_by = worker_id[:120]
    event.locked_at = utcnow()
    event.status = "processing"
    event.attempts = int(event.attempts or 0) + 1
    db.session.flush()

    handlers = _handlers_for(event.event_type)
    if not handlers:
        log_event_processing(event, "event_bus", "success", "No registered handler; event recorded only.")
    else:
        for handler in handlers:
            handler_name = getattr(handler, "__name__", "handler")
            try:
                handler(event)
                log_event_processing(event, handler_name, "success", "Handler completed.")
            except Exception as exc:  # pragma: no cover - safety net for production
                event.status = "failed"
                event.error_json = _json_dumps({"error": str(exc), "traceback": traceback.format_exc()})[:20000]
                log_event_processing(event, handler_name, "error", str(exc))
                if commit:
                    db.session.commit()
                return event

    event.status = "processed"
    event.processed_at = utcnow()
    event.locked_by = None
    event.locked_at = None
    if commit:
        db.session.commit()
    return event


def process_pending_events(*, limit: int = 25, worker_id: str = "event-worker") -> int:
    now = utcnow()
    events = (SystemEvent.query
              .filter(SystemEvent.status.in_(["pending", "queued"]))
              .filter((SystemEvent.available_at.is_(None)) | (SystemEvent.available_at <= now))
              .order_by(SystemEvent.priority.asc(), SystemEvent.created_at.asc())
              .limit(int(limit or 25)).all())
    count = 0
    for event in events:
        process_event(event, worker_id=worker_id, commit=True)
        count += 1
    return count


def retry_event(event: SystemEvent, *, commit: bool = True) -> SystemEvent:
    event.status = "pending"
    event.error_json = ""
    event.available_at = utcnow()
    event.locked_at = None
    event.locked_by = None
    log_event_processing(event, "event_bus", "info", "Event queued for retry.")
    if commit:
        db.session.commit()
    return event


def release_stale_events(*, stale_after_minutes: int = 15, worker_id: str = "event-worker") -> int:
    cutoff = utcnow() - timedelta(minutes=int(stale_after_minutes or 15))
    rows = SystemEvent.query.filter(
        SystemEvent.status == "processing",
        SystemEvent.locked_at.isnot(None),
        SystemEvent.locked_at < cutoff,
    ).all()
    for event in rows:
        event.status = "pending"
        event.locked_at = None
        event.locked_by = None
        event.available_at = utcnow()
        log_event_processing(event, worker_id, "warning", "Released stale processing event.")
    if rows:
        db.session.commit()
    return len(rows)


def event_stats() -> dict:
    rows = db.session.execute(db.text("""
        SELECT status, COUNT(*) AS count
        FROM system_events
        GROUP BY status
        ORDER BY status
    """)).mappings().all()
    stats = {row["status"] or "unknown": int(row["count"] or 0) for row in rows}
    stats["total"] = sum(stats.values())
    return stats


def ensure_default_subscriptions(commit: bool = False) -> int:
    defaults = [
        ("import-publishing", "monthly_import_published", "live.publish_monthly_import", "Refresh users after month-end figures are published."),
        ("trusted-financials", "trusted_financials_published", "live.publish_trusted_financials", "Refresh dashboards after royalties and cache are trusted."),
        ("job-completed", "job.completed", "jobs", "Record completed background jobs."),
        ("job-failed", "job.failed", "jobs", "Record failed background jobs for Operations Centre."),
        ("cache-rebuilt", "cache.rebuilt", "performance.cache", "Record performance cache rebuilds."),
        ("attendance-updated", "attendance.updated", "attendance", "Future hook for Attendance module live sync."),
        ("claim-created", "claim.created", "insurance_claims", "Future hook for Claims module live sync."),
        ("royalty-recalculated", "royalty.recalculated", "royalty_management", "Record and publish royalty recalculation results."),
        ("royalty-needs-review", "royalty.needs_review", "royalty_management", "Track royalty rows that require Admin/Finance review."),
        ("insights-rebuilt", "insights.rebuilt", "insights_engine", "Record explanation-engine rebuilds for executive insight summaries."),
    ]
    created = 0
    for name, event_type, handler, description in defaults:
        sub = EventSubscription.query.filter_by(name=name).first()
        if not sub:
            db.session.add(EventSubscription(name=name, event_type=event_type, handler=handler, description=description, is_active=True))
            created += 1
    if commit:
        db.session.commit()
    return created
