from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable, Optional

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.extensions import db
from app.models import LiveEvent, LiveNotification, MonthlyFigure, Franchise

live_bp = Blueprint('live', __name__, url_prefix='/live')


def _now():
    return datetime.now(timezone.utc)


def _role_names(user=None):
    user = user or current_user
    return {role.name for role in getattr(user, 'roles', []) or [] if getattr(role, 'name', None)}


def _is_admin_finance(user=None):
    return bool(_role_names(user) & {'Admin', 'Super Admin', 'Finance Manager', 'Finance Assistant', 'Regional Manager'})


def _user_franchise_ids(user=None):
    user = user or current_user
    return [f.id for f in (getattr(user, 'assigned_franchises', []) or []) if getattr(f, 'id', None)]


def create_live_event(kind: str, title: str, message: str = '', *, user_id: Optional[int] = None,
                      import_job_id: Optional[int] = None, franchise_id: Optional[int] = None,
                      month: Optional[int] = None, year: Optional[int] = None,
                      visibility: str = 'admin_finance', payload: Optional[dict] = None,
                      commit: bool = False) -> LiveEvent:
    event = LiveEvent(
        kind=(kind or 'system')[:80],
        title=(title or '')[:160],
        message=(message or '')[:500],
        user_id=user_id,
        import_job_id=import_job_id,
        franchise_id=franchise_id,
        month=month,
        year=year,
        visibility=(visibility or 'admin_finance')[:40],
        payload_json=json.dumps(payload or {}, default=str)[:8000],
        created_at=_now(),
    )
    db.session.add(event)
    if commit:
        db.session.commit()
    return event


def notify_users(title: str, message: str = '', *, user_ids: Optional[Iterable[int]] = None,
                 role_scope: str = 'admin_finance', franchise_id: Optional[int] = None,
                 import_job_id: Optional[int] = None, payload: Optional[dict] = None,
                 commit: bool = False) -> list[LiveNotification]:
    from app.models import User
    users = []
    if user_ids:
        users = User.query.filter(User.id.in_(list(user_ids))).all()
    elif role_scope == 'franchise' and franchise_id:
        users = [u for u in User.query.all() if any(f.id == franchise_id for f in (u.assigned_franchises or []))]
    else:
        users = [u for u in User.query.all() if _is_admin_finance(u)]
    notes = []
    for user in users:
        note = LiveNotification(
            user_id=user.id,
            title=(title or '')[:160],
            message=(message or '')[:500],
            category=(role_scope or 'system')[:40],
            franchise_id=franchise_id,
            import_job_id=import_job_id,
            payload_json=json.dumps(payload or {}, default=str)[:8000],
            created_at=_now(),
        )
        db.session.add(note)
        notes.append(note)
    if commit:
        db.session.commit()
    return notes


def publish_monthly_import(month: int, year: int, franchise_ids: Iterable[int], *, import_job=None,
                           source: str = 'month_end_import', report: Optional[dict] = None) -> None:
    ids = [int(fid) for fid in (franchise_ids or []) if fid]
    payload = {
        'month': month,
        'year': year,
        'franchise_ids': ids,
        'franchise_count': len(ids),
        'source': source,
        'report': report or {},
    }
    create_live_event(
        'monthly_import_published',
        f'Month-end data published for {year}-{int(month):02d}',
        f'{len(ids)} franchise record(s) updated and visible according to each user permission.',
        user_id=getattr(import_job, 'created_by_id', None),
        import_job_id=getattr(import_job, 'id', None),
        month=month,
        year=year,
        visibility='all',
        payload=payload,
    )
    notify_users(
        'Month-end figures updated',
        f'{year}-{int(month):02d} figures were imported, royalties recalculated and dashboards refreshed.',
        role_scope='admin_finance',
        import_job_id=getattr(import_job, 'id', None),
        payload=payload,
    )
    for fid in ids:
        franchise = Franchise.query.get(fid)
        notify_users(
            'Your figures were updated',
            f'{getattr(franchise, "business_name", "Your franchise")} month-end figures are now available.',
            role_scope='franchise',
            franchise_id=fid,
            import_job_id=getattr(import_job, 'id', None),
            payload={**payload, 'franchise_id': fid},
        )


def mark_import_visible(rows: Iterable[MonthlyFigure], *, status: str = 'Published') -> int:
    count = 0
    for row in rows or []:
        row.status = status
        row.approved_at = row.approved_at or _now()
        row.updated_at = _now()
        count += 1
    return count


def _refresh_payload(month: int, year: int, franchise_ids: Iterable[int], source: str, report: Optional[dict] = None) -> dict:
    ids = [int(fid) for fid in (franchise_ids or []) if fid]
    return {
        'month': int(month),
        'year': int(year),
        'period': f'{int(year)}-{int(month):02d}',
        'franchise_ids': ids,
        'franchise_count': len(ids),
        'source': source,
        'auto_refresh': True,
        'refresh_sections': ['dashboard', 'royalties', 'monthly', 'leaderboard', 'performance'],
        'refresh_paths': ['/dashboard', '/royalties', '/monthly', '/performance', '/performance/graphs', '/leaderboard', '/franchise'],
        'report': report or {},
    }


def publish_trusted_financials(month: int, year: int, franchise_ids: Iterable[int], *, import_job=None,
                               source: str = 'trusted_financial_publish', report: Optional[dict] = None,
                               commit: bool = False) -> LiveEvent:
    """Broadcast that imported figures passed royalty/reconciliation checks.

    This is the event the browser uses to refresh active dashboard, royalty,
    leaderboard and graph pages.  Admin/Finance receive company-wide notices;
    franchise users receive only notices for franchises linked to their login.
    """
    ids = [int(fid) for fid in (franchise_ids or []) if fid]
    payload = _refresh_payload(month, year, ids, source, report)
    event = create_live_event(
        'trusted_financials_published',
        f'Trusted financials published for {int(year)}-{int(month):02d}',
        f'Royalties, dashboards, graphs and leaderboard were refreshed for {len(ids)} franchise record(s).',
        user_id=getattr(import_job, 'created_by_id', None),
        import_job_id=getattr(import_job, 'id', None),
        month=month,
        year=year,
        visibility='all',
        payload=payload,
    )
    notify_users(
        'Financial data refreshed',
        f'{int(year)}-{int(month):02d} royalties, dashboards, graphs and leaderboard are now up to date.',
        role_scope='admin_finance',
        import_job_id=getattr(import_job, 'id', None),
        payload=payload,
    )
    for fid in ids:
        franchise = Franchise.query.get(fid)
        notify_users(
            'Your dashboard was refreshed',
            f'{getattr(franchise, "business_name", "Your franchise")} figures and royalties are now up to date.',
            role_scope='franchise',
            franchise_id=fid,
            import_job_id=getattr(import_job, 'id', None),
            payload={**payload, 'franchise_id': fid, 'franchise_ids': [fid]},
        )
    if commit:
        db.session.commit()
    return event


def _payload_from_item(item) -> dict:
    raw = getattr(item, 'payload_json', '') or ''
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _should_refresh_path(path: str, payload: dict, kind: str = '') -> bool:
    if not payload or not payload.get('auto_refresh'):
        return False
    path = (path or '').split('?', 1)[0].rstrip('/') or '/'
    # Never auto-refresh upload/edit pages while a user may be working in a form.
    blocked = ['/admin/imports', '/admin/imports/centre']
    if any(path.startswith(prefix) for prefix in blocked):
        return False
    refresh_paths = payload.get('refresh_paths') or []
    return any(path == prefix.rstrip('/') or path.startswith(prefix.rstrip('/') + '/') for prefix in refresh_paths)


@live_bp.route('/status')
@login_required
def status():
    since_id = request.args.get('since_id', type=int) or 0
    current_path = request.args.get('path', '') or ''
    roles = _role_names()
    franchise_ids = _user_franchise_ids()
    is_admin_finance = _is_admin_finance()

    notifications = LiveNotification.query.filter(
        LiveNotification.user_id == current_user.id,
        LiveNotification.id > since_id,
    ).order_by(LiveNotification.id.desc()).limit(10).all()

    event_query = LiveEvent.query.filter(LiveEvent.id > since_id)
    if not is_admin_finance:
        if franchise_ids:
            event_query = event_query.filter(
                db.or_(
                    LiveEvent.visibility == 'all',
                    LiveEvent.franchise_id.in_(franchise_ids),
                )
            )
        else:
            event_query = event_query.filter(LiveEvent.visibility == 'all')
    events = event_query.order_by(LiveEvent.id.desc()).limit(10).all()

    latest_figure = MonthlyFigure.query
    if not is_admin_finance:
        if franchise_ids:
            latest_figure = latest_figure.filter(MonthlyFigure.franchise_id.in_(franchise_ids))
        else:
            latest_figure = latest_figure.filter(False)
    latest_figure = latest_figure.order_by(MonthlyFigure.updated_at.desc()).first()

    newest_id = since_id
    refresh = {'required': False}
    combined_items = list(notifications) + list(events)
    for item in combined_items:
        newest_id = max(newest_id, int(item.id or 0))
        payload = _payload_from_item(item)
        kind = getattr(item, 'kind', '') or getattr(item, 'category', '') or ''
        if not refresh.get('required') and _should_refresh_path(current_path, payload, kind):
            refresh = {
                'required': True,
                'event_id': int(item.id or 0),
                'kind': kind,
                'period': payload.get('period') or (f"{getattr(item, 'year', '')}-{int(getattr(item, 'month', 0) or 0):02d}" if getattr(item, 'year', None) and getattr(item, 'month', None) else ''),
                'message': getattr(item, 'message', '') or 'New live data is available.',
            }

    return jsonify({
        'ok': True,
        'latest_id': newest_id,
        'server_time': _now().isoformat(),
        'latest_period': latest_figure.period_label if latest_figure else '',
        'notifications': [n.to_dict() for n in notifications],
        'events': [e.to_dict() for e in events],
        'refresh': refresh,
        'roles': sorted(roles),
    })


@live_bp.route('/notifications/read', methods=['POST'])
@login_required
def mark_read():
    ids = request.json.get('ids', []) if request.is_json else []
    query = LiveNotification.query.filter(LiveNotification.user_id == current_user.id)
    if ids:
        query = query.filter(LiveNotification.id.in_([int(i) for i in ids if str(i).isdigit()]))
    for note in query.filter(LiveNotification.read_at.is_(None)).all():
        note.read_at = _now()
    db.session.commit()
    return jsonify({'ok': True})
