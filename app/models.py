from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app
from app.extensions import db, login_manager

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id"), primary_key=True),
)

user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
)


user_franchises = db.Table(
    "user_franchises",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("franchise_id", db.Integer, db.ForeignKey("franchises.id"), primary_key=True),
    db.Column("is_primary", db.Boolean, default=False, nullable=False),
)
class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.String(255))
    is_system_role = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    permissions = db.relationship("Permission", secondary=role_permissions, lazy="subquery", backref=db.backref("roles", lazy=True))

    def has_permission(self, code):
        # The Role Permissions screen is the single source of truth for every role,
        # including Admin. If a permission is unticked, that role no longer has it.
        return any(permission.code == code for permission in self.permissions)

class Permission(db.Model):
    __tablename__ = "permissions"
    id = db.Column(db.Integer, primary_key=True)
    module = db.Column(db.String(120), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    code = db.Column(db.String(160), unique=True, nullable=False, index=True)
    label = db.Column(db.String(160), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    surname = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime)
    deactivated_at = db.Column(db.DateTime)
    deactivation_reason = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    roles = db.relationship("Role", secondary=user_roles, lazy="subquery", backref=db.backref("users", lazy=True))
    assigned_franchises = db.relationship("Franchise", secondary=user_franchises, lazy="subquery", backref=db.backref("assigned_users", lazy=True))

    @property
    def full_name(self):
        return f"{self.name} {self.surname}".strip()

    @property
    def primary_role_name(self):
        return self.roles[0].name if self.roles else "No Role"

    @property
    def is_protected_admin(self):
        return self.email.lower() == "wjm@martinsdirect.com" or self.full_name.lower() == "wjm piek"

    def ensure_protected_admin_role(self):
        if not self.is_protected_admin:
            return
        admin_role = Role.query.filter_by(name="Admin").first()
        if admin_role and admin_role not in self.roles:
            self.roles.append(admin_role)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def accessible_franchises(self):
        # Global franchise access is controlled by permissions, not hardcoded role names.
        # Users with Franchise Management view/manage can see all franchises.
        if self.has_permission("franchise_management:view") or self.has_permission("franchise_management:manage"):
            return Franchise.query.order_by(Franchise.business_name).all()
        if self.assigned_franchises:
            return sorted(self.assigned_franchises, key=lambda item: item.business_name or "")
        if getattr(self, "franchise", None):
            return [self.franchise]
        return []

    def can_access_franchise(self, franchise_id):
        # Access to an individual franchise follows the same permission model.
        if self.has_permission("franchise_management:view") or self.has_permission("franchise_management:manage"):
            return True
        return any(franchise.id == franchise_id for franchise in self.accessible_franchises())

    def has_role(self, role_name):
        return any(role.name == role_name for role in self.roles)

    def has_permission(self, code):
        return any(role.has_permission(code) for role in self.roles)

    def get_reset_token(self):
        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        return serializer.dumps(self.email, salt="password-reset-salt")

    @staticmethod
    def verify_reset_token(token, max_age=1800):
        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        try:
            email = serializer.loads(token, salt="password-reset-salt", max_age=max_age)
        except (BadSignature, SignatureExpired):
            return None
        return User.query.filter_by(email=email).first()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Franchise(db.Model):
    __tablename__ = "franchises"
    id = db.Column(db.Integer, primary_key=True)
    business_name = db.Column(db.String(180), nullable=False, default="")
    franchise_code = db.Column(db.String(80), default="")
    ck_business_name = db.Column(db.String(255), default="")
    ck_number = db.Column(db.String(80), default="")
    pty_business_name = db.Column(db.String(255), default="")
    pty_number = db.Column(db.String(80), default="")
    vat_number = db.Column(db.String(80), default="")
    office_address = db.Column(db.Text, default="")
    office_number = db.Column(db.String(80), default="")
    after_hours_number = db.Column(db.String(80), default="")
    franchisee_name = db.Column(db.String(120), default="")
    franchisee_surname = db.Column(db.String(120), default="")
    franchisee_cell = db.Column(db.String(80), default="")
    franchisee_email = db.Column(db.String(255), default="")
    facebook_url = db.Column(db.String(255), default="")
    instagram_url = db.Column(db.String(255), default="")
    tiktok_url = db.Column(db.String(255), default="")
    website_url = db.Column(db.String(255), default="")
    public_email = db.Column(db.String(255), default="")
    agreement_start_date = db.Column(db.Date)
    agreement_end_date = db.Column(db.Date)
    minimum_royalty_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    royalty_gross_method = db.Column(db.String(20), nullable=False, default="old")
    imported_royalty_scale_text = db.Column(db.Text, default="")
    imported_royalty_percentage = db.Column(db.Numeric(5, 2), default=0)
    regional_manager_email = db.Column(db.String(255), default="")
    finance_manager_email = db.Column(db.String(255), default="")
    notification_60_sent_at = db.Column(db.DateTime)
    notification_30_sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def franchisee_full_name(self):
        return f"{self.franchisee_name} {self.franchisee_surname}".strip()

class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    action = db.Column(db.String(160), nullable=False)
    module = db.Column(db.String(120), nullable=False, index=True)
    details = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    user = db.relationship("User", backref=db.backref("audit_logs", lazy=True))

class RoyaltyScale(db.Model):
    __tablename__ = "royalty_scales"
    id = db.Column(db.Integer, primary_key=True)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=False, index=True)
    row_number = db.Column(db.Integer, nullable=False, default=1)
    amount_from = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    amount_to = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    percentage = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    franchise = db.relationship("Franchise", backref=db.backref("royalty_scales", lazy=True, cascade="all, delete-orphan"))


class MonthlyFigure(db.Model):
    __tablename__ = "monthly_figures"
    id = db.Column(db.Integer, primary_key=True)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=False, index=True)
    month = db.Column(db.Integer, nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    gross_turnover = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cash = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    funeral_receipts = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    claim_receipts = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    society_receipts = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cash_sales = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tombstone_receipts = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    obo_service_receipts = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    sales = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    insurance_receipts = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    insurance_payover = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    admin_fee = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    insurance_joinings = db.Column(db.Integer, nullable=False, default=0)
    mf_files = db.Column(db.Integer, nullable=False, default=0)
    cash_received = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    insurance_received = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    payover = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    other_income = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    number_of_funerals = db.Column(db.Integer, nullable=False, default=0)
    number_of_policies = db.Column(db.Integer, nullable=False, default=0)
    number_of_claims = db.Column(db.Integer, nullable=False, default=0)
    gross_revenue = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    royalty_percentage = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    royalty_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    minimum_royalty_applied = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(30), nullable=False, default="Draft", index=True)
    notes = db.Column(db.Text, default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    submitted_at = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)
    locked_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    franchise = db.relationship("Franchise", backref=db.backref("monthly_figures", lazy=True, cascade="all, delete-orphan"))
    created_by = db.relationship("User", backref=db.backref("monthly_figures_created", lazy=True))

    @property
    def period_label(self):
        return f"{self.year}-{self.month:02d}"
