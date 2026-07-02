from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from app.extensions import db
from app.models import PerformancePageCache

CACHE_VERSION = "phase5"


def _now():
    return datetime.now(timezone.utc)


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


def stable_hash(parts: Iterable) -> str:
    raw = json.dumps(list(parts), sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def build_cache_key(cache_type: str, *, month: Optional[int] = None, year: Optional[int] = None,
                    metric: Optional[str] = None, franchise_ids: Optional[Iterable[int]] = None,
                    scope: str = "global", extra: Optional[dict] = None) -> str:
    ids = sorted(int(fid) for fid in (franchise_ids or []) if fid)
    return stable_hash([CACHE_VERSION, cache_type, scope, int(month or 0), int(year or 0), metric or "", ids, extra or {}])


def get_cached_payload(cache_type: str, cache_key: str):
    row = PerformancePageCache.query.filter_by(cache_type=cache_type, cache_key=cache_key, invalidated_at=None).first()
    if not row:
        return None
    return row.to_payload()


def set_cached_payload(cache_type: str, cache_key: str, payload: dict, *, month: Optional[int] = None,
                       year: Optional[int] = None, metric: Optional[str] = None, scope_type: str = "global",
                       scope_id: Optional[int] = None, row_count: int = 0, commit: bool = False):
    row = PerformancePageCache.query.filter_by(cache_type=cache_type, cache_key=cache_key).first()
    if not row:
        row = PerformancePageCache(cache_type=cache_type, cache_key=cache_key)
        db.session.add(row)
    row.scope_type = scope_type or "global"
    row.scope_id = scope_id
    row.year = int(year) if year else None
    row.month = int(month) if month else None
    row.metric = metric
    row.payload_json = json.dumps(payload or {}, default=_json_default)[:2000000]
    row.row_count = int(row_count or 0)
    row.source_version = CACHE_VERSION
    row.invalidated_at = None
    row.built_at = _now()
    row.updated_at = _now()
    if commit:
        db.session.commit()
    return row


def invalidate_performance_cache(*, month: Optional[int] = None, year: Optional[int] = None,
                                 franchise_ids: Optional[Iterable[int]] = None, cache_type: Optional[str] = None,
                                 commit: bool = False) -> int:
    query = PerformancePageCache.query.filter(PerformancePageCache.invalidated_at.is_(None))
    if cache_type:
        query = query.filter(PerformancePageCache.cache_type == cache_type)
    if month:
        query = query.filter(PerformancePageCache.month == int(month))
    if year:
        query = query.filter(PerformancePageCache.year == int(year))
    # Scope-specific filtering is intentionally conservative. Aggregate cache keys
    # can contain many franchise IDs, so when a franchise period changes we invalidate
    # the whole period rather than risking a stale aggregate view.
    rows = query.all()
    stamp = _now()
    for row in rows:
        row.invalidated_at = stamp
        row.updated_at = stamp
    if commit:
        db.session.commit()
    return len(rows)


def cache_stats():
    total = PerformancePageCache.query.count()
    valid = PerformancePageCache.query.filter(PerformancePageCache.invalidated_at.is_(None)).count()
    invalid = total - valid
    latest = PerformancePageCache.query.order_by(PerformancePageCache.built_at.desc()).first()
    return {
        "total": total,
        "valid": valid,
        "invalidated": invalid,
        "latest_built_at": latest.built_at.isoformat() if latest and latest.built_at else "",
    }
