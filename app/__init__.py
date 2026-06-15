from flask import Flask
from config import Config
from app.extensions import db, migrate, login_manager, mail


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

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

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(franchise_bp)
    app.register_blueprint(monthly_bp)
    app.register_blueprint(royalties_bp)

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

    @app.cli.command("check-franchise-expiry")
    def check_franchise_expiry():
        from app.franchise.notifications import send_agreement_expiry_reminders
        sent_count = send_agreement_expiry_reminders()
        print(f"Franchise agreement reminder emails sent: {sent_count}")

    return app
