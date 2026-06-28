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


class FranchiseTarget(db.Model):
    __tablename__ = "franchise_targets"
    id = db.Column(db.Integer, primary_key=True)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=False, index=True)
    metric = db.Column(db.String(80), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    month = db.Column(db.Integer, nullable=False, index=True)
    target_value = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    franchise = db.relationship("Franchise", backref=db.backref("targets", lazy=True, cascade="all, delete-orphan"))
    __table_args__ = (
        db.UniqueConstraint("franchise_id", "metric", "year", "month", name="uq_franchise_target_period_metric"),
    )


class HeatmapRecord(db.Model):
    __tablename__ = "heatmap_records"
    id = db.Column(db.Integer, primary_key=True)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=True, index=True)
    mf_file = db.Column(db.String(120), default="", index=True)
    deceased_name = db.Column(db.String(120), default="")
    deceased_surname = db.Column(db.String(120), default="")
    dod = db.Column(db.String(50), default="")
    address = db.Column(db.String(255), default="")
    city = db.Column(db.String(120), default="", index=True)
    province = db.Column(db.String(120), default="", index=True)
    country = db.Column(db.String(120), default="South Africa")
    full_address = db.Column(db.String(512), default="")
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    weight = db.Column(db.Float, default=1.0)
    next_of_kin_name = db.Column(db.String(120), default="")
    next_of_kin_surname = db.Column(db.String(120), default="")
    relationship = db.Column(db.String(120), default="")
    relation = db.Column(db.String(50), default="")
    contact_number = db.Column(db.String(120), default="")
    source_filename = db.Column(db.String(255), default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    franchise = db.relationship("Franchise", backref=db.backref("heatmap_records", lazy=True, cascade="all, delete-orphan"))
    created_by = db.relationship("User", backref=db.backref("heatmap_records_created", lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "franchiseId": self.franchise_id,
            "franchiseName": self.franchise.business_name if self.franchise else "Unassigned",
            "mfFile": self.mf_file or "",
            "deceasedName": self.deceased_name or "",
            "deceasedSurname": self.deceased_surname or "",
            "dod": self.dod or "",
            "address": self.address or "",
            "city": self.city or "",
            "province": self.province or "",
            "country": self.country or "South Africa",
            "fullAddress": self.full_address or "",
            "latitude": self.latitude,
            "longitude": self.longitude,
            "weight": self.weight if self.weight is not None else 1,
            "nextOfKinName": self.next_of_kin_name or "",
            "nextOfKinSurname": self.next_of_kin_surname or "",
            "relationship": self.relationship or "",
            "relation": self.relation or "",
            "contactNumber": self.contact_number or "",
            "sourceFilename": self.source_filename or "",
            "updatedAt": self.updated_at.isoformat() if self.updated_at else "",
        }



class AttendanceStaff(db.Model):
    __tablename__ = "attendance_staff"
    id = db.Column(db.Integer, primary_key=True)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=True, index=True)
    first_name = db.Column(db.String(120), nullable=False, default="")
    surname = db.Column(db.String(120), nullable=False, default="")
    email = db.Column(db.String(255), default="", index=True)
    phone = db.Column(db.String(80), default="")
    id_number = db.Column(db.String(80), default="")
    employee_number = db.Column(db.String(80), default="", index=True)
    position = db.Column(db.String(120), default="")
    staff_type = db.Column(db.String(40), default="Employee", index=True)
    website_url = db.Column(db.String(255), default="")
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    notes = db.Column(db.Text, default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    franchise = db.relationship("Franchise", backref=db.backref("attendance_staff", lazy=True, cascade="all, delete-orphan"))
    created_by = db.relationship("User", backref=db.backref("attendance_staff_created", lazy=True))

    @property
    def full_name(self):
        return f"{self.first_name} {self.surname}".strip()


class AttendanceOffice(db.Model):
    __tablename__ = "attendance_offices"
    id = db.Column(db.Integer, primary_key=True)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=True, index=True)
    name = db.Column(db.String(160), nullable=False, default="Office")
    address = db.Column(db.String(255), default="")
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    allowed_radius_m = db.Column(db.Integer, nullable=False, default=100)
    qr_token = db.Column(db.String(120), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    franchise = db.relationship("Franchise", backref=db.backref("attendance_offices", lazy=True, cascade="all, delete-orphan"))


class AttendanceEvent(db.Model):
    __tablename__ = "attendance_events"
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey("attendance_staff.id"), nullable=False, index=True)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=True, index=True)
    office_id = db.Column(db.Integer, db.ForeignKey("attendance_offices.id"), nullable=True, index=True)
    action = db.Column(db.String(20), nullable=False, index=True)  # sign_in or sign_out
    event_time = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    accuracy_meters = db.Column(db.Float)
    distance_from_site_m = db.Column(db.Float)
    gps_status = db.Column(db.String(50), default="")
    work_location_type = db.Column(db.String(50), default="Office")
    source = db.Column(db.String(50), default="web")
    device_info = db.Column(db.Text, default="")
    employee_note = db.Column(db.Text, default="")
    manager_note = db.Column(db.Text, default="")
    approval_status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    approved_at = db.Column(db.DateTime)
    rejected_reason = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    staff = db.relationship("AttendanceStaff", backref=db.backref("attendance_events", lazy=True, cascade="all, delete-orphan"))
    franchise = db.relationship("Franchise")
    office = db.relationship("AttendanceOffice")
    approved_by = db.relationship("User")


class AttendanceLeaveRequest(db.Model):
    __tablename__ = "attendance_leave_requests"
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey("attendance_staff.id"), nullable=False, index=True)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=True, index=True)
    leave_type = db.Column(db.String(80), nullable=False, default="Annual Leave")
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text, default="")
    status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    manager_note = db.Column(db.Text, default="")
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    decided_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    staff = db.relationship("AttendanceStaff", backref=db.backref("leave_requests", lazy=True, cascade="all, delete-orphan"))
    franchise = db.relationship("Franchise")
    decided_by = db.relationship("User")

class MFFManual(db.Model):
    __tablename__ = "mff_manuals"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    confidentiality_note = db.Column(db.String(500), default="Confidential - internal use only")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

class MFFManualVersion(db.Model):
    __tablename__ = "mff_manual_versions"
    id = db.Column(db.Integer, primary_key=True)
    manual_id = db.Column(db.Integer, db.ForeignKey("mff_manuals.id"), nullable=False, index=True)
    version_label = db.Column(db.String(80), nullable=False, default="v1.0")
    filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100), nullable=False, default="application/pdf")
    storage_path = db.Column(db.String(600), nullable=False, default="")
    sha256 = db.Column(db.String(64), nullable=False, default="")
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    is_published = db.Column(db.Boolean, nullable=False, default=True, index=True)
    manual = db.relationship("MFFManual", backref=db.backref("versions", lazy=True, cascade="all, delete-orphan", order_by="desc(MFFManualVersion.uploaded_at)"))
    uploaded_by = db.relationship("User")
    __table_args__ = (db.UniqueConstraint("manual_id", "version_label", name="uq_mff_manual_version_label"),)

class MFFIndexDocument(db.Model):
    __tablename__ = "mff_index_documents"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.String(600), nullable=False, default="")
    content_type = db.Column(db.String(120), nullable=False, default="application/pdf")
    manual_id = db.Column(db.Integer, db.ForeignKey("mff_manuals.id"), nullable=True, index=True)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    manual = db.relationship("MFFManual", backref=db.backref("index_documents", lazy=True))
    uploaded_by = db.relationship("User")

class MFFManualAcknowledgement(db.Model):
    __tablename__ = "mff_manual_acknowledgements"
    id = db.Column(db.Integer, primary_key=True)
    manual_version_id = db.Column(db.Integer, db.ForeignKey("mff_manual_versions.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    attested_name = db.Column(db.String(255), nullable=False)
    attested_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    ip_address = db.Column(db.String(64), default="")
    user_agent = db.Column(db.String(500), default="")
    manual_version = db.relationship("MFFManualVersion")
    user = db.relationship("User")
    __table_args__ = (db.UniqueConstraint("manual_version_id", "user_id", name="uq_mff_ack_manual_user"),)



class InsurancePolicyMonthlyRaw(db.Model):
    __tablename__ = "insurance_policy_monthly_raw"
    id = db.Column(db.Integer, primary_key=True)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=True, index=True)
    franchise_name = db.Column(db.String(255), nullable=False, index=True)
    import_month = db.Column(db.Date, nullable=False, index=True)
    retail_premium = db.Column(db.Numeric(18, 2), default=0)
    risk_premium = db.Column(db.Numeric(18, 2), default=0)
    claims = db.Column(db.Numeric(18, 2), default=0)
    claim_count = db.Column(db.Numeric(18, 2), default=0)
    claim_paid_franchise = db.Column(db.Numeric(18, 2), default=0)
    claim_paid_client = db.Column(db.Numeric(18, 2), default=0)
    repudiated_pending = db.Column(db.Numeric(18, 2), default=0)
    grand_total_claims = db.Column(db.Numeric(18, 2), default=0)
    policy_qty = db.Column(db.Numeric(18, 2), default=0)
    original_risk_premium = db.Column(db.Numeric(18, 2), default=0)
    r1_policy_fee = db.Column(db.Numeric(18, 2), default=0)
    underwriter_2_1_fee = db.Column(db.Numeric(18, 2), default=0)
    risk_after_r1 = db.Column(db.Numeric(18, 2), default=0)
    single_monthly_premium_total = db.Column(db.Numeric(18, 2), default=0)
    current_scenario = db.Column(db.String(120), default="100% Claim Ratio")
    source_file = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    franchise = db.relationship("Franchise")
    __table_args__ = (db.UniqueConstraint("franchise_name", "import_month", name="uq_ins_policy_franchise_month"),)


class InsuranceClaimsMonthlyRaw(db.Model):
    __tablename__ = "insurance_claims_monthly_raw"
    id = db.Column(db.Integer, primary_key=True)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=True, index=True)
    claim_key = db.Column(db.String(255), default="", index=True)
    claims_franchise_name = db.Column(db.String(255), nullable=False, index=True)
    claim_month = db.Column(db.Date, nullable=False, index=True)
    claims_amount = db.Column(db.Numeric(18, 2), default=0)
    claim_count = db.Column(db.Numeric(18, 2), default=0)
    claim_paid_franchise = db.Column(db.Numeric(18, 2), default=0)
    claim_paid_client = db.Column(db.Numeric(18, 2), default=0)
    repudiated_pending = db.Column(db.Numeric(18, 2), default=0)
    grand_total_claims = db.Column(db.Numeric(18, 2), default=0)
    source_file = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    franchise = db.relationship("Franchise")
    __table_args__ = (db.UniqueConstraint("claim_key", "claims_franchise_name", "claim_month", name="uq_ins_claim_key_franchise_month"),)


class InsurancePolicyDataDetailRaw(db.Model):
    __tablename__ = "insurance_policydata_detail_raw"
    id = db.Column(db.Integer, primary_key=True)
    source_file = db.Column(db.String(255), nullable=False, index=True)
    import_month = db.Column(db.Date, nullable=False, index=True)
    row_number = db.Column(db.Integer, nullable=False)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=True, index=True)
    franchise_name = db.Column(db.String(255), nullable=False, index=True)
    relation = db.Column(db.String(80), default="", index=True)
    is_mem = db.Column(db.Boolean, nullable=False, default=False, index=True)
    retail_premium = db.Column(db.Numeric(18, 2), default=0)
    original_risk_premium = db.Column(db.Numeric(18, 2), default=0)
    mpia = db.Column(db.Numeric(18, 2), default=0)
    single_premium = db.Column(db.Numeric(18, 6), default=0)
    r1_policy_fee = db.Column(db.Numeric(18, 2), default=0)
    adv_fund_2_1_fee = db.Column(db.Numeric(18, 2), default=0)
    risk_after_r1 = db.Column(db.Numeric(18, 2), default=0)
    new_risk_premium = db.Column(db.Numeric(18, 2), default=0)
    raw_data = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    franchise = db.relationship("Franchise")
    __table_args__ = (db.UniqueConstraint("source_file", "import_month", "row_number", name="uq_ins_policydata_source_month_row"),)


class InsuranceImportHistory(db.Model):
    __tablename__ = "insurance_import_history"
    id = db.Column(db.Integer, primary_key=True)
    import_type = db.Column(db.String(80), nullable=False, index=True)
    source_file = db.Column(db.String(255), default="")
    imported_months = db.Column(db.Text, default="")
    row_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default="success", index=True)
    message = db.Column(db.Text, default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = db.relationship("User")


class InsuranceFranchiseMapping(db.Model):
    __tablename__ = "insurance_franchise_mapping"
    id = db.Column(db.Integer, primary_key=True)
    source_name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    mapped_name = db.Column(db.String(255), nullable=False, index=True)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=True, index=True)
    approved = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    franchise = db.relationship("Franchise")


class InsuranceClaimCase(db.Model):
    __tablename__ = "insurance_claim_cases"
    id = db.Column(db.Integer, primary_key=True)
    claim_ref = db.Column(db.String(120), nullable=False, unique=True, index=True)
    franchise_id = db.Column(db.Integer, db.ForeignKey("franchises.id"), nullable=True, index=True)
    franchise_name = db.Column(db.String(255), default="", index=True)
    claimant_name = db.Column(db.String(255), default="")
    policy_number = db.Column(db.String(120), default="", index=True)
    id_number = db.Column(db.String(80), default="")
    claim_type = db.Column(db.String(120), default="Funeral Claim", index=True)
    claim_date = db.Column(db.Date, nullable=True, index=True)
    date_of_death = db.Column(db.Date, nullable=True)
    claim_amount = db.Column(db.Numeric(18, 2), default=0)
    status = db.Column(db.String(60), nullable=False, default="Open", index=True)
    priority = db.Column(db.String(40), default="Normal")
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    notes = db.Column(db.Text, default="")
    closed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    franchise = db.relationship("Franchise")
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])


class InsuranceClaimNote(db.Model):
    __tablename__ = "insurance_claim_notes"
    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey("insurance_claim_cases.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    user_email = db.Column(db.String(255), default="")
    note = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    claim = db.relationship("InsuranceClaimCase", backref=db.backref("claim_notes", lazy=True, cascade="all, delete-orphan", order_by="desc(InsuranceClaimNote.created_at)"))
    user = db.relationship("User")


class InsuranceClaimAttachment(db.Model):
    __tablename__ = "insurance_claim_attachments"
    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey("insurance_claim_cases.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(600), nullable=False)
    content_type = db.Column(db.String(120), default="")
    size_bytes = db.Column(db.Integer, default=0)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    claim = db.relationship("InsuranceClaimCase", backref=db.backref("attachments", lazy=True, cascade="all, delete-orphan", order_by="desc(InsuranceClaimAttachment.created_at)"))
    uploaded_by = db.relationship("User")


class InsuranceClaimDocumentType(db.Model):
    __tablename__ = "insurance_claim_document_types"
    id = db.Column(db.Integer, primary_key=True)
    document_type = db.Column(db.String(160), nullable=False, unique=True)
    claim_type = db.Column(db.String(120), default="Funeral Claim")
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class InsuranceClaimDocumentRule(db.Model):
    __tablename__ = "insurance_claim_document_rules"
    id = db.Column(db.Integer, primary_key=True)
    document_type_id = db.Column(db.Integer, db.ForeignKey("insurance_claim_document_types.id"), nullable=False, index=True)
    rule_key = db.Column(db.String(120), nullable=False)
    rule_value = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    document_type = db.relationship("InsuranceClaimDocumentType", backref=db.backref("rules", lazy=True, cascade="all, delete-orphan"))
