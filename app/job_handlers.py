"""Persistent job handlers for Martins background processing.

This module is imported by create_app so handlers register before the CLI worker
or Operations Centre tries to run queued jobs.
"""
from __future__ import annotations

from pathlib import Path
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.jobs import add_job_log, job_payload, register_job_handler, update_job_progress
from app.models import ImportJob


def _file_storage_from_payload(payload: dict) -> FileStorage:
    path = Path(payload.get("stored_path") or "")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Queued upload file not found: {path}")
    stream = path.open("rb")
    return FileStorage(stream=stream, filename=payload.get("original_filename") or path.name)


@register_job_handler("monthly_excel_import")
def run_monthly_excel_import_job(job: ImportJob) -> dict:
    """Process an Excel month-end import from the persistent queue."""
    from app.monthly.routes import import_monthly_figures_excel_file

    payload = job_payload(job)
    update_job_progress(job, 5, "Opening queued Excel workbook", status="running", commit=True)
    storage = _file_storage_from_payload(payload)
    try:
        result = import_monthly_figures_excel_file(
            storage,
            allocate_users=bool(payload.get("allocate_users", True)),
            progress_job=job,
            actor_user_id=payload.get("created_by_id"),
        )
        pipeline = result.get("pipeline") or {}
        if pipeline.get("status") == "needs_review":
            update_job_progress(
                job,
                100,
                "Excel import processed but needs review before trusted publishing.",
                status="needs_review",
                data=result,
                commit=False,
            )
        else:
            update_job_progress(
                job,
                100,
                "Excel import completed, royalties recalculated and data published.",
                status="completed",
                data=result,
                commit=False,
            )
        job.result_json = job.result_json or job.extra_json
        db.session.commit()
        return result
    finally:
        try:
            storage.close()
        except Exception:
            pass


@register_job_handler("monthly_pdf_import")
def run_monthly_pdf_import_job(job: ImportJob) -> dict:
    """Process one PDF month-end import from the persistent queue."""
    from app.monthly.routes import create_monthly_figure_from_pdf
    from app.monthly.import_pipeline import run_month_end_import_pipeline

    payload = job_payload(job)
    update_job_progress(job, 5, "Opening queued PDF report", status="running", commit=True)
    storage = _file_storage_from_payload(payload)
    try:
        figure = create_monthly_figure_from_pdf(
            storage,
            franchise_id=payload.get("franchise_id"),
            month=payload.get("month"),
            year=payload.get("year"),
            progress_job=job,
            actor_user_id=payload.get("created_by_id"),
            trusted_admin_import=True,
        )
        update_job_progress(job, 75, "Rebuilding import pipeline for imported PDF", commit=True)
        pipeline = run_month_end_import_pipeline(
            period_tuples={(figure.month, figure.year)},
            franchise_ids={figure.franchise_id},
            progress_job=job,
        )
        result = {
            "monthly_figure_id": figure.id,
            "franchise_id": figure.franchise_id,
            "franchise_name": getattr(figure.franchise, "business_name", ""),
            "month": figure.month,
            "year": figure.year,
            "period_label": figure.period_label,
            "pipeline": pipeline,
        }
        if pipeline.get("status") == "needs_review":
            update_job_progress(job, 100, "PDF import processed but needs review before trusted publishing.", status="needs_review", data=result, commit=False)
        else:
            update_job_progress(job, 100, "PDF import completed, royalties recalculated and data published.", status="completed", data=result, commit=False)
        job.result_json = job.result_json or job.extra_json
        db.session.commit()
        return result
    finally:
        try:
            storage.close()
        except Exception:
            pass


@register_job_handler("rebuild_performance_cache")
def run_rebuild_performance_cache_job(job: ImportJob) -> dict:
    """Rebuild cached performance results for all imported periods."""
    from app.models import MonthlyFigure
    from app.performance.service import rebuild_performance_results

    periods = db.session.query(MonthlyFigure.month, MonthlyFigure.year).distinct().order_by(MonthlyFigure.year, MonthlyFigure.month).all()
    total_periods = max(len(periods), 1)
    total_rows = 0
    for index, (month, year) in enumerate(periods, start=1):
        franchise_ids = [row[0] for row in db.session.query(MonthlyFigure.franchise_id).filter_by(month=month, year=year).distinct().all()]
        saved = rebuild_performance_results(month, year, franchise_ids, "annual_gross_scale")
        total_rows += int(saved or 0)
        update_job_progress(job, int((index / total_periods) * 100), f"Rebuilt performance cache for {year}-{month:02d}", commit=True)
    add_job_log(job, "info", "Performance cache rebuild complete", {"rows": total_rows}, commit=False)
    return {"periods": len(periods), "rows": total_rows}
