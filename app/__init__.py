from flask import Flask, g, request, url_for
import click
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
from config import Config
from app.extensions import db, migrate, login_manager, mail


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Long-lived browser cache for static assets. This keeps the Martins logo, CSS and JS
    # in the browser cache instead of refetching/reflashing them on every page change.
    app.config.setdefault("SEND_FILE_MAX_AGE_DEFAULT", 31536000)

    @app.after_request
    def add_static_asset_cache_headers(response):
        if request.path.startswith(app.static_url_path + "/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            response.headers["Expires"] = (datetime.utcnow() + timedelta(days=365)).strftime("%a, %d %b %Y %H:%M:%S GMT")
            response.headers.pop("Pragma", None)
        return response

    @app.before_request
    def start_request_timer():
        g.request_started_at = time.perf_counter()

    @app.after_request
    def record_request_timing(response):
        started = getattr(g, "request_started_at", None)
        if started is None:
            return response
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
        threshold_ms = float(app.config.get("SLOW_REQUEST_THRESHOLD_MS", 1500))
        if elapsed_ms >= threshold_ms and not request.path.startswith(app.static_url_path + "/"):
            app.logger.warning(
                "SLOW_REQUEST method=%s path=%s status=%s duration_ms=%.1f query=%s",
                request.method, request.path, response.status_code, elapsed_ms, request.query_string.decode("utf-8", "ignore")
            )
        return response

    def _static_asset_version(relative_path):
        try:
            asset_path = Path(app.static_folder) / relative_path
            return str(int(asset_path.stat().st_mtime))
        except OSError:
            return "1"

    def _static_asset_url(relative_path):
        return url_for("static", filename=relative_path, v=_static_asset_version(relative_path))

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = None
    login_manager.login_message_category = "warning"

    from app.auth.routes import auth_bp
    from app.dashboard.routes import dashboard_bp
    from app.admin.routes import admin_bp
    from app.franchise.routes import franchise_bp
    from app.monthly.routes import monthly_bp
    from app.royalties.routes import royalties_bp
    from app.heatmap.routes import heatmap_bp
    from app.attendance.routes import attendance_bp
    from app.manuals.routes import manuals_bp
    from app.insurance_claims.routes import insurance_claims_bp
    from app.leaderboard.routes import leaderboard_bp
    from app.performance.routes import performance_bp
    from app.live import live_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(franchise_bp)
    app.register_blueprint(monthly_bp)
    app.register_blueprint(royalties_bp)
    app.register_blueprint(heatmap_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(manuals_bp)
    app.register_blueprint(insurance_claims_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(performance_bp)
    app.register_blueprint(live_bp)

    # Register persistent job handlers after blueprints/modules are importable.
    from app import job_handlers  # noqa: F401


    @app.template_filter("rand")
    def format_rand(value):
        try:
            amount = float(value or 0)
        except (TypeError, ValueError):
            amount = 0.0
        return f"R {amount:,.2f}"

    @app.template_filter("count_value")
    def format_count_value(value):
        """Format non-currency operational counts such as Joinings and Funerals."""
        try:
            amount = float(value or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount == int(amount):
            return f"{int(amount):,}"
        return f"{amount:,.2f}"

    @app.template_filter("metric_value")
    def format_metric_value(value, metric_key=None, metric_format=None):
        """Render KPI values with the correct unit. Joinings/Funerals are counts, not Rand."""
        count_metrics = {"joinings", "funerals", "insurance_joinings", "mf_files", "number_of_funerals"}
        if metric_format == "number" or metric_key in count_metrics:
            return format_count_value(value)
        return format_rand(value)

    @app.context_processor
    def inject_static_branding():
        return {
            "brand_logo_url": _static_asset_url("img/logo.png"),
            "brand_logo_fallback_url": _static_asset_url("img/logo-placeholder.svg"),
            "asset_url": _static_asset_url,
        }

    @app.context_processor
    def inject_franchise_context():
        from app.franchise_context import (
            get_accessible_franchises,
            get_selected_franchise,
            is_franchise_view_mode,
            is_privileged_user,
        )
        return {
            "accessible_franchises": get_accessible_franchises(),
            "selected_franchise": get_selected_franchise(),
            "franchise_view_mode": is_franchise_view_mode(),
            "privileged_user": is_privileged_user(),
        }



    @app.cli.command("enqueue-noop-job")
    def enqueue_noop_job():
        """Create a small test job for the persistent queue."""
        from app.jobs import enqueue_job
        job = enqueue_job("system_noop", filename="system", payload={"source": "cli"})
        print(f"Queued job {job.id}")

    @app.cli.command("run-next-job")
    def run_next_job_command():
        """Process one queued persistent job."""
        from app.jobs import run_next_job
        job = run_next_job(worker_id="render-cli")
        if not job:
            print("No queued jobs found.")
        else:
            print(f"Processed job {job.id}: {job.status} - {job.message}")

    @app.cli.command("run-job-worker")
    @click.option("--forever", is_flag=True, help="Keep polling for jobs instead of exiting when the queue is empty.")
    @click.option("--sleep", "sleep_seconds", default=5, show_default=True, type=int, help="Seconds to wait between empty polls.")
    @click.option("--queue", "queue_name", default="default", show_default=True, help="Queue name to process.")
    @click.option("--worker-id", default="render-worker", show_default=True, help="Worker identifier stored on locked jobs.")
    @click.option("--release-stale", is_flag=True, help="Release stale running jobs before polling.")
    @click.option("--stale-minutes", default=15, show_default=True, type=int, help="Heartbeat age in minutes before a job is stale.")
    def run_job_worker_command(forever, sleep_seconds, queue_name, worker_id, release_stale, stale_minutes):
        """Process queued persistent jobs.

        Use once from Render Shell for manual processing, or use --forever as a
        Render Worker start command for continuous background processing.
        """
        import time
        from app.jobs import queue_stats, register_worker_heartbeat, release_stale_jobs, run_next_job, stop_worker_heartbeat

        processed = 0
        empty_polls = 0
        register_worker_heartbeat(worker_id, queue_name=queue_name, status="starting", message="Worker starting", commit=True)
        try:
            while True:
                register_worker_heartbeat(worker_id, queue_name=queue_name, status="polling", message="Polling for queued jobs", commit=True)
                if release_stale:
                    released = release_stale_jobs(stale_after_minutes=stale_minutes, worker_id=worker_id)
                    if released:
                        print(f"Released stale jobs: {released}")

                job = run_next_job(queue_name=queue_name, worker_id=worker_id)
                if job:
                    processed += 1
                    empty_polls = 0
                    register_worker_heartbeat(worker_id, queue_name=queue_name, status="idle", message=f"Processed job {job.id}: {job.status}", commit=True)
                    print(f"Processed job {job.id}: {job.status} - {job.message}")
                    continue

                stats = queue_stats(queue_name=queue_name)
                if not forever:
                    break
                empty_polls += 1
                print(f"No queued jobs. Poll {empty_polls}. Stats: {stats}. Sleeping {sleep_seconds}s")
                time.sleep(max(int(sleep_seconds or 5), 1))
        finally:
            stop_worker_heartbeat(worker_id, message=f"Worker stopped after processing {processed} jobs", commit=True)
        print(f"Worker finished. Jobs processed: {processed}")

    @app.cli.command("release-stale-jobs")
    @click.option("--stale-minutes", default=15, show_default=True, type=int)
    @click.option("--worker-id", default="render-cli", show_default=True)
    def release_stale_jobs_command(stale_minutes, worker_id):
        """Release stale locked jobs back to the persistent queue."""
        from app.jobs import release_stale_jobs
        count = release_stale_jobs(stale_after_minutes=stale_minutes, worker_id=worker_id)
        print(f"Released stale jobs: {count}")

    @app.cli.command("process-events")
    @click.option("--limit", default=50, show_default=True, type=int)
    @click.option("--worker-id", default="event-cli", show_default=True)
    @click.option("--release-stale", is_flag=True, help="Release stale processing events before processing pending events.")
    def process_events_command(limit, worker_id, release_stale):
        """Process pending enterprise event bus rows."""
        from app.events import ensure_default_subscriptions, process_pending_events, release_stale_events
        ensure_default_subscriptions(commit=True)
        if release_stale:
            released = release_stale_events(worker_id=worker_id)
            print(f"Released stale events: {released}")
        count = process_pending_events(limit=limit, worker_id=worker_id)
        print(f"Processed events: {count}")

    @app.cli.command("seed-event-subscriptions")
    def seed_event_subscriptions_command():
        """Seed default event-bus subscription registry rows."""
        from app.events import ensure_default_subscriptions
        count = ensure_default_subscriptions(commit=True)
        print(f"Event subscriptions created: {count}")

    @app.cli.command("optimize-performance-indexes")
    def optimize_performance_indexes_command():
        """Create safe PostgreSQL indexes used by dashboards, graphs and royalties."""
        from sqlalchemy import text
        statements = [
            "CREATE INDEX IF NOT EXISTS ix_monthly_figures_period_franchise ON monthly_figures (year, month, franchise_id)",
            "CREATE INDEX IF NOT EXISTS ix_monthly_figures_franchise_period ON monthly_figures (franchise_id, year, month)",
            "CREATE INDEX IF NOT EXISTS ix_performance_results_period_metric_franchise ON performance_results (year, month, metric, franchise_id)",
            "CREATE INDEX IF NOT EXISTS ix_performance_results_franchise_period_metric ON performance_results (franchise_id, year, month, metric)",
            "CREATE INDEX IF NOT EXISTS ix_franchise_targets_period_metric_franchise ON franchise_targets (year, month, metric, franchise_id)",
            "CREATE INDEX IF NOT EXISTS ix_performance_page_cache_lookup ON performance_page_cache (cache_type, cache_key, invalidated_at)",
        ]
        for statement in statements:
            db.session.execute(text(statement))
            print(statement)
        db.session.commit()
        db.session.execute(text("ANALYZE monthly_figures"))
        db.session.execute(text("ANALYZE performance_results"))
        db.session.execute(text("ANALYZE franchise_targets"))
        db.session.commit()
        print("Performance indexes created and PostgreSQL statistics refreshed.")

    @app.cli.command("warm-analytics-cache")
    @click.option("--month", type=int, required=True)
    @click.option("--year", type=int, required=True)
    def warm_analytics_cache_command(month, year):
        """Build performance rows and graph payloads before users open pages."""
        from app.models import MonthlyFigure
        from app.performance.service import rebuild_performance_results, warm_graph_caches_for_period
        franchise_ids = [row[0] for row in db.session.query(MonthlyFigure.franchise_id).filter_by(month=month, year=year).distinct().all()]
        rows = rebuild_performance_results(month, year, franchise_ids, "annual_gross_scale")
        graphs = warm_graph_caches_for_period(month, year, franchise_ids, periods=12, mode="annual_gross_scale")
        print(f"Warmed {year}-{month:02d}: {rows} performance rows and {graphs} aggregate graph caches.")

    @app.cli.command("rebuild-performance-cache")
    @click.option("--month", type=int, required=False, help="Reporting month number, 1-12. Omit to rebuild all periods.")
    @click.option("--year", type=int, required=False, help="Reporting year. Omit to rebuild all periods.")
    def rebuild_performance_cache(month, year):
        """Pre-calculate performance_results. Optionally limit to one reporting period."""
        from app.models import MonthlyFigure
        from app.performance.service import rebuild_performance_results
        query = db.session.query(MonthlyFigure.month, MonthlyFigure.year).distinct()
        if month and year:
            query = query.filter(MonthlyFigure.month == int(month), MonthlyFigure.year == int(year))
        periods = query.order_by(MonthlyFigure.year, MonthlyFigure.month).all()
        total = 0
        for period_month, period_year in periods:
            franchise_ids = [row[0] for row in db.session.query(MonthlyFigure.franchise_id).filter_by(month=period_month, year=period_year).distinct().all()]
            saved = rebuild_performance_results(period_month, period_year, franchise_ids, "annual_gross_scale")
            total += saved
            print(f"{period_year}-{period_month:02d}: {saved} rows")
        print(f"Performance cache rebuilt. Total rows saved: {total}")


    @app.cli.command("recalculate-royalties")
    @click.option("--month", type=int, required=True, help="Reporting month number, 1-12.")
    @click.option("--year", type=int, required=True, help="Reporting year, e.g. 2026.")
    def recalculate_royalties_command(month, year):
        """Rebuild Phase 9 royalty snapshots and existing royalty amounts for a period."""
        from app.royalty_management import recalculate_royalties_for_period
        result = recalculate_royalties_for_period(month, year, commit=True)
        print(f"Royalties recalculated for {year}-{month:02d}: {result}")

    @app.cli.command("seed-royalty-growth-profile")
    def seed_royalty_growth_profile_command():
        """Ensure the default SA GDP growth royalty profile exists."""
        from app.royalty_management import ensure_default_growth_profile
        profile = ensure_default_growth_profile(commit=True)
        print(f"Royalty growth profile ready: {profile.name} ({profile.default_growth_percent}%)")


    @app.cli.command("rebuild-business-intelligence")
    @click.option("--month", type=int, required=False, help="Reporting month number, 1-12. Defaults to latest period.")
    @click.option("--year", type=int, required=False, help="Reporting year. Defaults to latest period.")
    def rebuild_business_intelligence_command(month, year):
        """Rebuild Phase 11 franchise health scores and executive insights."""
        from app.business_intelligence import rebuild_business_intelligence, latest_period
        period = latest_period() if not month or not year else {"month": month, "year": year}
        result = rebuild_business_intelligence(period["year"], period["month"], commit=True)
        print(f"Business intelligence rebuilt for {result['year']}-{result['month']:02d}: {result['snapshots']} snapshots, {result['insights']} insights")


    @app.cli.command("rebuild-insights")
    @click.option("--month", type=int, required=False, help="Reporting month number, 1-12. Defaults to latest period.")
    @click.option("--year", type=int, required=False, help="Reporting year. Defaults to latest period.")
    def rebuild_insights_command(month, year):
        """Rebuild Phase 12 plain-language insight narratives."""
        from app.insights_engine import rebuild_insight_narratives, latest_period
        period = latest_period() if not month or not year else {"month": month, "year": year}
        result = rebuild_insight_narratives(period["year"], period["month"], commit=True)
        print(f"Insight narratives rebuilt for {result['year']}-{result['month']:02d}: {result['narratives']} narratives")


    @app.cli.command("seed-workflow-defaults")
    def seed_workflow_defaults_command():
        """Seed Phase 13 workflow, business-rule and schedule defaults."""
        from app.workflow_engine import ensure_phase13_defaults
        result = ensure_phase13_defaults(commit=True)
        print(f"Workflow defaults ready: {result}")

    @app.cli.command("run-diagnostics-workflow")
    def run_diagnostics_workflow_command():
        """Run the Phase 13 system diagnostics workflow and create review tasks."""
        from app.workflow_engine import run_diagnostics_workflow
        instance = run_diagnostics_workflow(commit=True)
        print(f"Diagnostics workflow {instance.id}: {instance.status} - {instance.message}")

    @app.cli.command("workflow-summary")
    def workflow_summary_command():
        """Print Phase 13 workflow/task/notification counts."""
        from app.workflow_engine import ensure_phase13_defaults, workflow_summary
        ensure_phase13_defaults(commit=True)
        print(workflow_summary())


    @app.cli.command("assign-franchise-regions")
    def assign_franchise_regions_command():
        """Assign province/region to franchises from name, code and office address."""
        from app.franchise_master_data import assign_regions_from_existing_data, ensure_franchise_codes
        code_result = ensure_franchise_codes(commit=True)
        result = assign_regions_from_existing_data(commit=True)
        print(f"Franchise codes ready: {code_result['assigned']} assigned, {code_result['total_codes']} total")
        print(f"Franchise regions assigned: {result['updated']} updated, {result['unassigned']} unassigned")

    @app.cli.command("seed-franchise-codes")
    def seed_franchise_codes_command():
        """Ensure every franchise has a permanent MF### franchise code."""
        from app.franchise_master_data import ensure_franchise_codes
        result = ensure_franchise_codes(commit=True)
        print(f"Franchise codes ready: {result['assigned']} assigned, {result['changed']} changed, {result['total_codes']} total")

    @app.cli.command("franchise-master-report")
    def franchise_master_report_command():
        """Print franchise master data-integrity counts for Render shell."""
        from app.franchise_master_data import data_integrity_rows
        rows = data_integrity_rows()
        ready = sum(1 for row in rows if row['status'] == 'Ready')
        review = len(rows) - ready
        print({"total": len(rows), "ready": ready, "needs_review": review})
        for row in rows[:25]:
            if row['status'] != 'Ready':
                print(f"{row['business_name']}: {', '.join(row['issues'])}")

    @app.cli.command("check-franchise-expiry")
    def check_franchise_expiry():
        from app.franchise.notifications import send_agreement_expiry_reminders
        sent_count = send_agreement_expiry_reminders()
        print(f"Franchise agreement reminder emails sent: {sent_count}")


    @app.cli.command("stabilize-platform")
    @click.option("--month", type=int, required=False, help="Reporting month number. Omit to use latest period.")
    @click.option("--year", type=int, required=False, help="Reporting year. Omit to use latest period.")
    @click.option("--all-periods", is_flag=True, help="Rebuild royalties, BI, insights and performance cache for every imported period.")
    def stabilize_platform_command(month, year, all_periods):
        """Run the safe v100 platform repair/rebuild sequence.

        This command is intended for Render Shell after deploying v100. It seeds
        required defaults, recalculates royalties without stopping on one bad
        franchise, rebuilds BI/insight data, rebuilds performance cache and
        processes pending events.
        """
        from app.models import MonthlyFigure
        from app.events import ensure_default_subscriptions, process_pending_events
        from app.royalty_management import ensure_default_growth_profile, recalculate_royalties_for_period
        from app.business_intelligence import rebuild_business_intelligence, latest_period as bi_latest_period
        from app.insights_engine import rebuild_insight_narratives, latest_period as insights_latest_period
        from app.workflow_engine import ensure_phase13_defaults
        from app.performance.service import rebuild_performance_results

        print("v100 platform stabilization starting...")
        event_subs = ensure_default_subscriptions(commit=True)
        growth_profile = ensure_default_growth_profile(commit=True)
        workflow_defaults = ensure_phase13_defaults(commit=True)
        print(f"Defaults ready: event_subscriptions_created={event_subs}, growth_profile={growth_profile.name}, workflow_defaults={workflow_defaults}")

        if all_periods:
            periods = db.session.query(MonthlyFigure.year, MonthlyFigure.month).distinct().order_by(MonthlyFigure.year, MonthlyFigure.month).all()
            periods = [(int(y), int(m)) for y, m in periods]
        else:
            if not month or not year:
                latest = bi_latest_period() or insights_latest_period() or {}
                month = int(latest.get("month") or 0)
                year = int(latest.get("year") or 0)
            periods = [(int(year), int(month))] if month and year else []

        if not periods:
            print("No monthly figure periods found. Dashboards will show empty-state cards until data is imported.")
        for period_year, period_month in periods:
            print(f"Rebuilding period {period_year}-{period_month:02d}...")
            royalty_result = recalculate_royalties_for_period(period_month, period_year, commit=True)
            print(f"  royalties: {royalty_result}")
            try:
                bi_result = rebuild_business_intelligence(period_year, period_month, commit=True)
                print(f"  business_intelligence: {bi_result}")
            except Exception as exc:
                db.session.rollback()
                print(f"  business_intelligence failed: {exc}")
            try:
                insight_result = rebuild_insight_narratives(period_year, period_month, commit=True)
                print(f"  insights: {insight_result}")
            except Exception as exc:
                db.session.rollback()
                print(f"  insights failed: {exc}")
            try:
                franchise_ids = [row[0] for row in db.session.query(MonthlyFigure.franchise_id).filter_by(month=period_month, year=period_year).distinct().all()]
                cache_rows = rebuild_performance_results(period_month, period_year, franchise_ids, "annual_gross_scale")
                print(f"  performance_cache_rows: {cache_rows}")
            except Exception as exc:
                db.session.rollback()
                print(f"  performance cache failed: {exc}")

        try:
            processed = process_pending_events(limit=200, worker_id="v100-stabilize")
            print(f"Events processed: {processed}")
        except Exception as exc:
            db.session.rollback()
            print(f"Event processing failed: {exc}")
        print("v100 platform stabilization complete.")

    return app
