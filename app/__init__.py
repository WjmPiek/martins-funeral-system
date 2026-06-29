import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def _ensure_lapsed_policy_contact_columns(app):
    """Small Render/PostgreSQL safety patch: add contact/suspense columns when the DB already exists."""
    from sqlalchemy import text
    with app.app_context():
        try:
            if not str(db.engine.url).startswith("postgresql"):
                return
            statements = [
                "ALTER TABLE lapsed_policies ADD COLUMN IF NOT EXISTS company_name VARCHAR(160)",
                "ALTER TABLE lapsed_policies ADD COLUMN IF NOT EXISTS id_number VARCHAR(30)",
                "ALTER TABLE lapsed_policies ADD COLUMN IF NOT EXISTS email_address VARCHAR(255)",
                "ALTER TABLE lapsed_policies ADD COLUMN IF NOT EXISTS suspense_reason TEXT",
                "UPDATE lapsed_policies SET company_name = COALESCE(NULLIF(company_name,''), NULLIF(franchise,''), NULLIF(branch,'')) WHERE company_name IS NULL OR company_name = ''",
                "UPDATE lapsed_policies SET suspense_reason = TRIM(BOTH ', ' FROM CONCAT(CASE WHEN id_number IS NULL OR TRIM(id_number) = '' THEN 'ID number, ' ELSE '' END, CASE WHEN (cell_number IS NULL OR TRIM(cell_number) = '') AND (home_tel IS NULL OR TRIM(home_tel) = '') THEN 'contact number, ' ELSE '' END, CASE WHEN email_address IS NULL OR TRIM(email_address) = '' THEN 'email address, ' ELSE '' END)) WHERE recovery_status <> 'Suspense' AND ((id_number IS NULL OR TRIM(id_number) = '') OR ((cell_number IS NULL OR TRIM(cell_number) = '') AND (home_tel IS NULL OR TRIM(home_tel) = '')) OR (email_address IS NULL OR TRIM(email_address) = ''))",
                "UPDATE lapsed_policies SET recovery_status = 'Suspense', assigned_agent_id = NULL, next_action_date = NULL, comments = CONCAT(COALESCE(comments,''), CASE WHEN COALESCE(comments,'') = '' THEN '' ELSE E'\\n' END, 'SUSPENSE: Missing ', COALESCE(NULLIF(suspense_reason,''),'required contact details'), '. Client cannot be contacted until business client/branch fixes these policy details.') WHERE recovery_status <> 'Suspense' AND COALESCE(suspense_reason,'') <> ''",
            ]
            with db.engine.begin() as conn:
                for stmt in statements:
                    conn.execute(text(stmt))
        except Exception:
            app.logger.exception("Could not ensure lapsed policy contact/suspense columns")


def _ensure_client_fica_document_columns(app):
    """Render/PostgreSQL safety patch for existing databases.

    Older live databases may have the client_fica_documents table from an
    earlier phase without the newer upload metadata/status columns.  When the
    external client signing page tries to save an ID copy or proof of address,
    PostgreSQL then rejects the INSERT/UPDATE and the upload appears to do
    nothing.  This keeps the schema compatible without wiping any data.
    """
    from sqlalchemy import text
    with app.app_context():
        try:
            if not str(db.engine.url).startswith("postgresql"):
                return
            statements = [
                "ALTER TABLE client_fica_documents ADD COLUMN IF NOT EXISTS document_type VARCHAR(80)",
                "ALTER TABLE client_fica_documents ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255)",
                "ALTER TABLE client_fica_documents ADD COLUMN IF NOT EXISTS file_path VARCHAR(500)",
                "ALTER TABLE client_fica_documents ADD COLUMN IF NOT EXISTS status VARCHAR(40) DEFAULT 'Received'",
                "ALTER TABLE client_fica_documents ADD COLUMN IF NOT EXISTS uploaded_at TIMESTAMP",
                "ALTER TABLE client_fica_documents ADD COLUMN IF NOT EXISTS uploaded_ip VARCHAR(80)",
                "ALTER TABLE client_fica_documents ADD COLUMN IF NOT EXISTS user_agent VARCHAR(500)",
                "UPDATE client_fica_documents SET status = 'Received' WHERE status IS NULL OR TRIM(status) = ''",
                "UPDATE client_fica_documents SET uploaded_at = NOW() WHERE uploaded_at IS NULL",
            ]
            with db.engine.begin() as conn:
                for stmt in statements:
                    conn.execute(text(stmt))
        except Exception:
            app.logger.exception("Could not ensure client FICA document columns")


def create_app():
    app = Flask(__name__)
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key and os.getenv("FLASK_ENV") == "production":
        raise RuntimeError("SECRET_KEY must be set in production")
    app.config["SECRET_KEY"] = secret_key or "dev-secret-change-me"
    db_url = os.getenv("DATABASE_URL", "sqlite:///dev.db")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # Render/Postgres can close idle SSL connections. These options force
    # SQLAlchemy to test/recycle connections instead of reusing dead ones.
    if db_url.startswith("postgresql"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
            "pool_recycle": 280,
            "pool_timeout": 30,
            "pool_size": 5,
            "max_overflow": 2,
        }
    upload_folder = os.getenv("UPLOAD_FOLDER")
    if upload_folder:
        upload_folder = os.path.abspath(upload_folder)
    else:
        upload_folder = os.path.join(app.root_path, "static", "uploads")
    app.config["UPLOAD_FOLDER"] = upload_folder
    app.config["BASE_URL"] = os.getenv("BASE_URL", "http://localhost:5000")

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from app.models import User

    # Auto-create missing tables for small Render deployments. This keeps new
    # helper tables, such as QR login tokens, from breaking existing databases.
    # Proper Flask migrations can still be added later.
    if os.getenv("AUTO_CREATE_TABLES", "1") == "1":
        with app.app_context():
            db.create_all()
            try:
                _ensure_lapsed_policy_contact_columns(app)
            except Exception:
                pass
            try:
                _ensure_client_fica_document_columns(app)
            except Exception:
                pass
            try:
                from app.models import Role, User
                super_role = Role.query.filter_by(name="Super Admin").first()
                if not super_role:
                    super_role = Role(name="Super Admin", description="Protected Super Admin account")
                    db.session.add(super_role)
                    db.session.flush()
                super_user = User.query.filter(db.func.lower(User.email) == "wjm@martinsdirect.com").first()
                if super_user:
                    super_user.role = super_role
                    super_user.active = True
                    db.session.commit()
                else:
                    db.session.commit()
            except Exception:
                db.session.rollback()

    try:
        _ensure_lapsed_policy_contact_columns(app)
    except Exception:
        pass
    try:
        _ensure_client_fica_document_columns(app)
    except Exception:
        pass

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))


    @app.teardown_request
    def shutdown_session(exception=None):
        if exception is not None:
            db.session.rollback()
        db.session.remove()

    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.applications import applications_bp
    from app.routes.signing import signing_bp
    from app.routes.policies import policies_bp
    from app.routes.recovery import recovery_bp
    from app.routes.qa import qa_bp
    from app.routes.documents import documents_bp
    from app.routes.advanced import advanced_bp
    from app.routes.security_center import security_center_bp
    from app.routes.settings import settings_bp
    from app.routes.reports import reports_bp
    from app.routes.role_portals import role_portals_bp
    from app.routes.allocation import allocation_bp
    from app.routes.wallboard import wallboard_bp
    from app.routes.targets import targets_bp
    from app.routes.analytics import analytics_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(signing_bp)
    app.register_blueprint(policies_bp)
    app.register_blueprint(recovery_bp)
    app.register_blueprint(qa_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(advanced_bp)
    app.register_blueprint(security_center_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(role_portals_bp)
    app.register_blueprint(allocation_bp)
    app.register_blueprint(wallboard_bp)
    app.register_blueprint(targets_bp)
    app.register_blueprint(analytics_bp)

    return app
