from __future__ import annotations

import json
from decimal import Decimal
from typing import Iterable, Set, Tuple

from flask import current_app

from app.extensions import db
from app.import_progress import update_import_job
from app.models import Franchise, MonthlyFigure, RoyaltyScale
from app.royalty_engine import validate_franchise_for_royalties


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


def _franchise_warning(franchise: Franchise, month=None, year=None) -> dict:
    validation = validate_franchise_for_royalties(franchise, month=month, year=year)
    warnings = list(validation.get('warnings') or [])
    blocking = list(validation.get('blocking_errors') or [])
    if franchise and not franchise.assigned_users:
        warnings.append('no linked franchise user login')
    validation['warnings'] = warnings
    validation['blocking_errors'] = blocking
    validation['blocking'] = bool(blocking)
    return validation


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
        'figures_visible': False,
        'trusted_financials': False,
        'blocking_issue_count': 0,
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

    # Franchise validation.  Missing agreement/scale can change royalty totals and
    # therefore blocks trusted publishing.  Missing login is a warning only: Admin
    # and Finance must still see the imported figures immediately, while the
    # franchise-user visibility can be fixed from User Management.
    blocking_validation_count = 0
    validation_month = periods[0][0] if periods else None
    validation_year = periods[0][1] if periods else None
    for franchise in franchises:
        validation = _franchise_warning(franchise, month=validation_month, year=validation_year)
        warnings = list(validation.get('warnings') or [])
        blocking = list(validation.get('blocking_errors') or [])
        if warnings or blocking:
            if blocking:
                blocking_validation_count += 1
            report['warnings'].append({
                'franchise_id': franchise.id,
                'franchise': franchise.business_name,
                'warnings': warnings,
                'blocking_errors': blocking,
                'blocking': bool(blocking),
                'royalty_method': validation.get('method_label'),
                'method_source': validation.get('method_source'),
                'scale_count': validation.get('scale_count'),
                'scale_source': validation.get('scale_source'),
                'scale_source_franchise': validation.get('scale_source_franchise'),
            })

    if report['errors'] or blocking_validation_count:
        report['status'] = 'needs_review'
        report['blocking_issue_count'] = blocking_validation_count + len(report['errors'])
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

    _stage(progress_job, 74, 'Publishing imported figures to role-filtered visibility...')
    try:
        from app.live import mark_import_visible
        report['published_rows'] = mark_import_visible(rows, status='Published')
        report['figures_visible'] = True
    except Exception as exc:
        current_app.logger.exception('Could not mark imported rows as visible: %s', exc)
        report['warnings'].append({'franchise': 'Live visibility', 'warnings': [f'Could not mark imported rows as Published: {exc}'], 'blocking': True})
        report['status'] = 'needs_review'
        report['blocking_issue_count'] = int(report.get('blocking_issue_count', 0) or 0) + 1

    _stage(progress_job, 78, 'Stage 3/6: recalculating royalties from agreement date and scale...')
    from app.monthly.routes import recalculate_monthly_figure
    from app.royalty_management import snapshot_monthly_figure
    report['royalty_engine_reviews'] = []
    report['royalty_snapshots'] = 0
    for monthly_figure in rows:
        result = recalculate_monthly_figure(monthly_figure)
        try:
            snapshot_monthly_figure(monthly_figure, commit=False)
            report['royalty_snapshots'] += 1
        except Exception as snap_exc:
            report['warnings'].append({'franchise': getattr(getattr(monthly_figure, 'franchise', None), 'business_name', monthly_figure.franchise_id), 'warnings': [f'Royalty snapshot failed: {snap_exc}'], 'blocking': True})
            report['status'] = 'needs_review'
            report['stage'] = 'royalty_snapshot_needs_review'
        report['recalculated_rows'] += 1
        if Decimal(monthly_figure.royalty_amount or 0) > 0 or Decimal(monthly_figure.royalty_percentage or 0) > 0:
            report['royalties_calculated'] += 1
        if result and (result.warnings or result.blocking_errors):
            report['royalty_engine_reviews'].append(result.to_dict())
            if result.blocking_errors:
                report['status'] = 'needs_review'
                report['stage'] = 'royalty_needs_review'
    try:
        from app.grouped_royalties import apply_grouped_royalties_for_period
        report['grouped_royalties'] = []
        for month, year in periods:
            grouped_result = apply_grouped_royalties_for_period(month, year, ids)
            if grouped_result.get('groups'):
                report['grouped_royalties'].append({
                    'period': f'{year}-{month:02d}',
                    'groups': grouped_result.get('groups', 0),
                    'rows': grouped_result.get('rows', 0),
                })
        if report['grouped_royalties']:
            for monthly_figure in rows:
                snapshot_monthly_figure(monthly_figure, commit=False)
    except Exception as grouped_exc:
        current_app.logger.exception('Grouped royalty calculation failed: %s', grouped_exc)
        report['status'] = 'needs_review'
        report['stage'] = 'grouped_royalty_needs_review'
        report['errors'].append(f'Grouped royalty calculation failed: {grouped_exc}')
    db.session.commit()

    _stage(progress_job, 86, 'Stage 4/6: checking royalty exceptions...')
    zero_royalty_rows = []
    for monthly_figure in rows:
        if "Royalty grouped under main franchise:" in (monthly_figure.notes or ""):
            continue
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

    # Always notify users that new monthly figures are visible.  Trusted financial
    # publishing (graphs/cache/leaderboard) only happens when reconciliation is clean.
    try:
        from app.live import publish_monthly_import
        for month, year in periods:
            publish_monthly_import(month, year, ids, import_job=progress_job, source='month_end_import', report=report)
    except Exception as live_exc:
        current_app.logger.exception('Could not publish live import event: %s', live_exc)

    if periods and ids:
        _stage(progress_job, 96, 'Stage 6/6: refreshing performance graphs and leaderboard cache...')
        try:
            from app.performance.service import warm_performance_cache_for_period
            from app.live import publish_trusted_financials
            for month, year in periods:
                refreshed = warm_performance_cache_for_period(month, year, list(ids), mode='annual_gross_scale')
                report['performance_rows'] += int(refreshed.get('performance_rows', 0) or 0)
                report['performance_cache_rows'] = int(report.get('performance_cache_rows', 0) or 0) + int(refreshed.get('cache_rows', 0) or 0)
                if report['status'] == 'completed':
                    publish_trusted_financials(month, year, ids, import_job=progress_job, source='month_end_import', report=report)
            report['published'] = True
            report['trusted_financials'] = report['status'] == 'completed'
            if report['status'] == 'completed':
                report['publish_message'] = 'Imported figures are visible. Royalties reconciled. Graphs, leaderboard and performance summaries were refreshed.'
            else:
                report['publish_message'] = 'Imported figures are visible and performance summaries were refreshed, but trusted publishing is blocked by review items.'
        except Exception as exc:
            current_app.logger.exception('Performance cache rebuild failed in import pipeline: %s', exc)
            report['status'] = 'needs_review'
            report['stage'] = 'publish_failed'
            report['errors'].append(f'Performance cache publish failed: {exc}')
    else:
        report['published'] = False
        report['trusted_financials'] = False
        report['publish_message'] = 'Imported figures are visible, but trusted royalty/performance publishing is blocked by review items.'

    final_message = 'Import completed and published.' if report['status'] == 'completed' else 'Import needs review before publishing.'
    _stage(progress_job, 99, final_message)
    if progress_job:
        progress_job.extra_json = json.dumps(report, default=str)[:8000]
        progress_job.status = report['status']
        progress_job.message = final_message
        db.session.commit()
    return report
