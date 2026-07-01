from __future__ import annotations

import json
from decimal import Decimal
from typing import Iterable, Set, Tuple

from flask import current_app

from app.extensions import db
from app.import_progress import update_import_job
from app.models import Franchise, MonthlyFigure, RoyaltyScale


def _as_list(values):
    return list(values or [])


def _stage(job, step: int, message: str):
    update_import_job(job, step=step, message=message, commit=True)


def _has_royalty_scale(franchise: Franchise) -> bool:
    if not franchise:
        return False
    structured = RoyaltyScale.query.filter_by(franchise_id=franchise.id).first()
    if structured:
        return True
    if (franchise.imported_royalty_scale_text or '').strip():
        return True
    try:
        return Decimal(franchise.imported_royalty_percentage or 0) > 0
    except Exception:
        return False


def _franchise_warning(franchise: Franchise) -> list[str]:
    warnings = []
    if not franchise.agreement_start_date:
        warnings.append('missing agreement start date')
    if not _has_royalty_scale(franchise):
        warnings.append('missing royalty scale')
    if not franchise.assigned_users:
        warnings.append('no linked franchise user login')
    return warnings


def run_month_end_import_pipeline(
    period_tuples: Iterable[Tuple[int, int]],
    franchise_ids: Iterable[int],
    progress_job=None,
) -> dict:
    """Run the full month-end pipeline after an Excel import.

    This intentionally runs after the raw values are imported.  The raw import only
    stores the figures.  This pipeline then makes the system business-ready:

    1. Validate that each branch is matched to the correct franchise record.
    2. Validate agreement date and royalty scale availability.
    3. Recalculate monthly rows from the agreement-date formula.
    4. Rebuild performance/leaderboard cache tables.
    5. Store a compact report on the ImportJob so the progress block can show the
       final result and support troubleshooting.
    """
    periods = sorted(set(tuple(item) for item in (period_tuples or [])), key=lambda item: (item[1], item[0]))
    ids: Set[int] = {int(item) for item in (franchise_ids or []) if item}
    report = {
        'status': 'completed',
        'periods': [f'{year}-{month:02d}' for month, year in periods],
        'franchise_count': len(ids),
        'recalculated_rows': 0,
        'performance_rows': 0,
        'warnings': [],
    }

    _stage(progress_job, 62, 'Pipeline stage 1/5: validating franchise matches...')
    franchises = Franchise.query.filter(Franchise.id.in_(ids)).order_by(Franchise.business_name).all() if ids else []
    for franchise in franchises:
        warnings = _franchise_warning(franchise)
        if warnings:
            report['warnings'].append({
                'franchise_id': franchise.id,
                'franchise': franchise.business_name,
                'warnings': warnings,
            })

    _stage(progress_job, 72, 'Pipeline stage 2/5: recalculating royalties from agreement dates...')
    from app.monthly.routes import recalculate_monthly_figure
    rows = []
    if periods and ids:
        clauses = []
        for month, year in periods:
            clauses.append(db.and_(MonthlyFigure.month == month, MonthlyFigure.year == year))
        rows = MonthlyFigure.query.filter(
            MonthlyFigure.franchise_id.in_(ids),
            db.or_(*clauses),
        ).all()
    for monthly_figure in rows:
        recalculate_monthly_figure(monthly_figure)
        report['recalculated_rows'] += 1
    db.session.commit()

    _stage(progress_job, 84, 'Pipeline stage 3/5: rebuilding performance cache...')
    try:
        from app.performance.service import rebuild_performance_results
        for month, year in periods:
            report['performance_rows'] += int(rebuild_performance_results(month, year, list(ids), 'annual_gross_scale') or 0)
    except Exception as exc:
        current_app.logger.exception('Performance cache rebuild failed in import pipeline: %s', exc)
        report['status'] = 'warning'
        report['warnings'].append({'franchise': 'Performance cache', 'warnings': [str(exc)]})

    _stage(progress_job, 92, 'Pipeline stage 4/5: checking royalty exceptions...')
    zero_royalty_rows = []
    for monthly_figure in rows:
        if Decimal(monthly_figure.gross_revenue or 0) > 0 and Decimal(monthly_figure.royalty_percentage or 0) <= 0:
            zero_royalty_rows.append({
                'franchise': monthly_figure.franchise.business_name if monthly_figure.franchise else monthly_figure.franchise_id,
                'period': monthly_figure.period_label,
                'gross': str(monthly_figure.gross_revenue or 0),
            })
    if zero_royalty_rows:
        report['status'] = 'warning'
        report['warnings'].append({
            'franchise': 'Royalty calculation',
            'warnings': [f'{len(zero_royalty_rows)} rows have gross revenue but 0% royalty. Check agreement date/scale.'],
            'rows': zero_royalty_rows[:20],
        })

    _stage(progress_job, 98, 'Pipeline stage 5/5: saving import report...')
    if progress_job:
        progress_job.extra_json = json.dumps(report, default=str)[:4000]
        db.session.commit()
    return report
