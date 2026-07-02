from flask import Flask, request, url_for
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


    @app.cli.command("rebuild-performance-cache")
    def rebuild_performance_cache():
        """Pre-calculate performance_results for every imported monthly period."""
        from app.models import MonthlyFigure
        from app.performance.service import rebuild_performance_results
        periods = db.session.query(MonthlyFigure.month, MonthlyFigure.year).distinct().order_by(MonthlyFigure.year, MonthlyFigure.month).all()
        total = 0
        for month, year in periods:
            franchise_ids = [row[0] for row in db.session.query(MonthlyFigure.franchise_id).filter_by(month=month, year=year).distinct().all()]
            saved = rebuild_performance_results(month, year, franchise_ids, "annual_gross_scale")
            total += saved
            print(f"{year}-{month:02d}: {saved} rows")
        print(f"Performance cache rebuilt. Total rows saved: {total}")

    @app.cli.command("check-franchise-expiry")
    def check_franchise_expiry():
        from app.franchise.notifications import send_agreement_expiry_reminders
        sent_count = send_agreement_expiry_reminders()
        print(f"Franchise agreement reminder emails sent: {sent_count}")

    return app
