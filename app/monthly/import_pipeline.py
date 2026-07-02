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
    """Run a controlled month-end import pipeline.

    The raw Excel import stores only the submitted figures.  This pipeline then
    validates, recalculates and publishes the data.  If a blocking validation
    fails, the import is marked ``needs_review`` and performance/leaderboard
    cache publishing is skipped until the issue is corrected and the import is
    re-run or refreshed.
    """
    periods = sorted(set(tuple(item) for item in (period_tuples or [])), key=lambda item: (item[1], item[0]))
    ids: Set[int] = {int(item) for item in (franchise_ids or []) if item}
    report = {
        'status': 'completed',
        'stage': 'published',
        'periods': [f'{year}-{month:02d}' for month, year in periods],
        'franchise_count': len(ids),
        'matched_franchises': 0,
        'saved_rows': 0,
        'recalculated_rows': 0,
        'royalties_calculated': 0,
        'performance_rows': 0,
        'warnings': [],
        'errors': [],
        'published': False,
        'publish_message': '',
    }

    _stage(progress_job, 58, 'Stage 1/6: validating imported period and franchise matches...')
    if not periods:
        report['status'] = 'needs_review'
        report['stage'] = 'validation_failed'
        report['errors'].append('No valid month/year sheets were detected in the uploaded workbook.')
    if not ids:
        report['status'] = 'needs_review'
        report['stage'] = 'validation_failed'
        report['errors'].append('No franchise rows were imported from the workbook.')

    franchises = Franchise.query.filter(Franchise.id.in_(ids)).order_by(Franchise.business_name).all() if ids else []
    report['matched_franchises'] = len(franchises)

    for franchise in franchises:
        warnings = _franchise_warning(franchise)
        if warnings:
            report['warnings'].append({
                'franchise_id': franchise.id,
                'franchise': franchise.business_name,
                'warnings': warnings,
            })

    if report['warnings'] or report['errors']:
        report['status'] = 'needs_review'
        if report['stage'] == 'published':
            report['stage'] = 'validation_needs_review'

    _stage(progress_job, 70, 'Stage 2/6: loading imported monthly rows...')
    rows = []
    if periods and ids:
        clauses = []
        for month, year in periods:
            clauses.append(db.and_(MonthlyFigure.month == month, MonthlyFigure.year == year))
        rows = MonthlyFigure.query.filter(
            MonthlyFigure.franchise_id.in_(ids),
            db.or_(*clauses),
        ).all()
    report['saved_rows'] = len(rows)

    _stage(progress_job, 74, 'Publishing rows to live system visibility...')
    try:
        from app.live import mark_import_visible
        report['published_rows'] = mark_import_visible(rows, status='Published')
    except Exception as exc:
        current_app.logger.exception('Could not mark imported rows as visible: %s', exc)
        report['warnings'].append({'franchise': 'Live visibility', 'warnings': [f'Could not mark imported rows as Published: {exc}']})

    _stage(progress_job, 78, 'Stage 3/6: recalculating royalties from agreement date and scale...')
    from app.monthly.routes import recalculate_monthly_figure
    for monthly_figure in rows:
        recalculate_monthly_figure(monthly_figure)
        report['recalculated_rows'] += 1
        if Decimal(monthly_figure.royalty_amount or 0) > 0 or Decimal(monthly_figure.royalty_percentage or 0) > 0:
            report['royalties_calculated'] += 1
    db.session.commit()

    _stage(progress_job, 86, 'Stage 4/6: checking royalty exceptions...')
    zero_royalty_rows = []
    for monthly_figure in rows:
        if Decimal(monthly_figure.gross_revenue or 0) > 0 and Decimal(monthly_figure.royalty_percentage or 0) <= 0:
            zero_royalty_rows.append({
                'franchise': monthly_figure.franchise.business_name if monthly_figure.franchise else monthly_figure.franchise_id,
                'period': monthly_figure.period_label,
                'gross': str(monthly_figure.gross_revenue or 0),
            })
    if zero_royalty_rows:
        report['status'] = 'needs_review'
        report['stage'] = 'royalty_needs_review'
        report['warnings'].append({
            'franchise': 'Royalty calculation',
            'warnings': [f'{len(zero_royalty_rows)} rows have gross revenue but 0% royalty. Check agreement date/scale.'],
            'rows': zero_royalty_rows[:50],
        })

    _stage(progress_job, 92, 'Stage 5/6: reconciliation checks...')
    expected_rows = len(rows)
    if report['recalculated_rows'] != expected_rows:
        report['status'] = 'needs_review'
        report['stage'] = 'reconciliation_failed'
        report['errors'].append(f'Recalculated rows ({report["recalculated_rows"]}) did not match saved rows ({expected_rows}).')

    if report['status'] == 'completed':
        _stage(progress_job, 96, 'Stage 6/6: publishing performance graphs and leaderboard cache...')
        try:
            from app.performance.service import rebuild_performance_results
            for month, year in periods:
                report['performance_rows'] += int(rebuild_performance_results(month, year, list(ids), 'annual_gross_scale') or 0)
                try:
                    from app.live import publish_monthly_import
                    publish_monthly_import(month, year, ids, import_job=progress_job, source='month_end_import', report=report)
                except Exception as live_exc:
                    current_app.logger.exception('Could not publish live import event: %s', live_exc)
            report['published'] = True
            report['publish_message'] = 'Graphs, leaderboard and performance summaries were refreshed. Live users were notified.'
        except Exception as exc:
            current_app.logger.exception('Performance cache rebuild failed in import pipeline: %s', exc)
            report['status'] = 'needs_review'
            report['stage'] = 'publish_failed'
            report['errors'].append(f'Performance cache publish failed: {exc}')
    else:
        report['published'] = False
        report['publish_message'] = 'Not published. Fix the review items first, then re-run/recalculate the import.'

    final_message = 'Import completed and published.' if report['status'] == 'completed' else 'Import needs review before publishing.'
    _stage(progress_job, 99, final_message)
    if progress_job:
        progress_job.extra_json = json.dumps(report, default=str)[:8000]
        progress_job.status = report['status']
        progress_job.message = final_message
        db.session.commit()
    return report

