"""Insurance claims module

Revision ID: v63_insurance_claims_module
Revises: v62_mff_manuals_module
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "v63_insurance_claims_module"
down_revision = "v62_mff_manuals_module"
branch_labels = None
depends_on = None


def _has_table(inspector, name):
    return name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "insurance_policy_monthly_raw"):
        op.create_table("insurance_policy_monthly_raw",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
            sa.Column("franchise_name", sa.String(255), nullable=False),
            sa.Column("import_month", sa.Date(), nullable=False),
            sa.Column("retail_premium", sa.Numeric(18,2), server_default="0"),
            sa.Column("risk_premium", sa.Numeric(18,2), server_default="0"),
            sa.Column("claims", sa.Numeric(18,2), server_default="0"),
            sa.Column("claim_count", sa.Numeric(18,2), server_default="0"),
            sa.Column("claim_paid_franchise", sa.Numeric(18,2), server_default="0"),
            sa.Column("claim_paid_client", sa.Numeric(18,2), server_default="0"),
            sa.Column("repudiated_pending", sa.Numeric(18,2), server_default="0"),
            sa.Column("grand_total_claims", sa.Numeric(18,2), server_default="0"),
            sa.Column("policy_qty", sa.Numeric(18,2), server_default="0"),
            sa.Column("original_risk_premium", sa.Numeric(18,2), server_default="0"),
            sa.Column("r1_policy_fee", sa.Numeric(18,2), server_default="0"),
            sa.Column("underwriter_2_1_fee", sa.Numeric(18,2), server_default="0"),
            sa.Column("risk_after_r1", sa.Numeric(18,2), server_default="0"),
            sa.Column("single_monthly_premium_total", sa.Numeric(18,2), server_default="0"),
            sa.Column("current_scenario", sa.String(120), server_default="100% Claim Ratio"),
            sa.Column("source_file", sa.String(255), server_default=""),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
            sa.UniqueConstraint("franchise_name", "import_month", name="uq_ins_policy_franchise_month"),
        )
        op.create_index("ix_ins_policy_month", "insurance_policy_monthly_raw", ["import_month"])
        op.create_index("ix_ins_policy_franchise", "insurance_policy_monthly_raw", ["franchise_name"])

    if not _has_table(inspector, "insurance_claims_monthly_raw"):
        op.create_table("insurance_claims_monthly_raw",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
            sa.Column("claim_key", sa.String(255), server_default=""),
            sa.Column("claims_franchise_name", sa.String(255), nullable=False),
            sa.Column("claim_month", sa.Date(), nullable=False),
            sa.Column("claims_amount", sa.Numeric(18,2), server_default="0"),
            sa.Column("claim_count", sa.Numeric(18,2), server_default="0"),
            sa.Column("claim_paid_franchise", sa.Numeric(18,2), server_default="0"),
            sa.Column("claim_paid_client", sa.Numeric(18,2), server_default="0"),
            sa.Column("repudiated_pending", sa.Numeric(18,2), server_default="0"),
            sa.Column("grand_total_claims", sa.Numeric(18,2), server_default="0"),
            sa.Column("source_file", sa.String(255), server_default=""),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
            sa.UniqueConstraint("claim_key", "claims_franchise_name", "claim_month", name="uq_ins_claim_key_franchise_month"),
        )
        op.create_index("ix_ins_claim_month", "insurance_claims_monthly_raw", ["claim_month"])
        op.create_index("ix_ins_claim_key", "insurance_claims_monthly_raw", ["claim_key"])
        op.create_index("ix_ins_claim_franchise", "insurance_claims_monthly_raw", ["claims_franchise_name"])

    if not _has_table(inspector, "insurance_policydata_detail_raw"):
        op.create_table("insurance_policydata_detail_raw",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_file", sa.String(255), nullable=False),
            sa.Column("import_month", sa.Date(), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
            sa.Column("franchise_name", sa.String(255), nullable=False),
            sa.Column("relation", sa.String(80), server_default=""),
            sa.Column("is_mem", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("retail_premium", sa.Numeric(18,2), server_default="0"),
            sa.Column("original_risk_premium", sa.Numeric(18,2), server_default="0"),
            sa.Column("mpia", sa.Numeric(18,2), server_default="0"),
            sa.Column("single_premium", sa.Numeric(18,6), server_default="0"),
            sa.Column("r1_policy_fee", sa.Numeric(18,2), server_default="0"),
            sa.Column("adv_fund_2_1_fee", sa.Numeric(18,2), server_default="0"),
            sa.Column("risk_after_r1", sa.Numeric(18,2), server_default="0"),
            sa.Column("new_risk_premium", sa.Numeric(18,2), server_default="0"),
            sa.Column("raw_data", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
            sa.UniqueConstraint("source_file", "import_month", "row_number", name="uq_ins_policydata_source_month_row"),
        )
        op.create_index("ix_ins_policydata_month", "insurance_policydata_detail_raw", ["import_month"])
        op.create_index("ix_ins_policydata_franchise", "insurance_policydata_detail_raw", ["franchise_name"])
        op.create_index("ix_ins_policydata_relation", "insurance_policydata_detail_raw", ["relation"])
        op.create_index("ix_ins_policydata_is_mem", "insurance_policydata_detail_raw", ["is_mem"])

    if not _has_table(inspector, "insurance_import_history"):
        op.create_table("insurance_import_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("import_type", sa.String(80), nullable=False),
            sa.Column("source_file", sa.String(255), server_default=""),
            sa.Column("imported_months", sa.Text(), server_default=""),
            sa.Column("row_count", sa.Integer(), server_default="0"),
            sa.Column("status", sa.String(50), server_default="success"),
            sa.Column("message", sa.Text(), server_default=""),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("ix_ins_import_type", "insurance_import_history", ["import_type"])
        op.create_index("ix_ins_import_status", "insurance_import_history", ["status"])

    if not _has_table(inspector, "insurance_franchise_mapping"):
        op.create_table("insurance_franchise_mapping",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_name", sa.String(255), nullable=False, unique=True),
            sa.Column("mapped_name", sa.String(255), nullable=False),
            sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
            sa.Column("approved", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("ix_ins_map_source", "insurance_franchise_mapping", ["source_name"])
        op.create_index("ix_ins_map_mapped", "insurance_franchise_mapping", ["mapped_name"])

    if not _has_table(inspector, "insurance_claim_cases"):
        op.create_table("insurance_claim_cases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("claim_ref", sa.String(120), nullable=False, unique=True),
            sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
            sa.Column("franchise_name", sa.String(255), server_default=""),
            sa.Column("claimant_name", sa.String(255), server_default=""),
            sa.Column("policy_number", sa.String(120), server_default=""),
            sa.Column("id_number", sa.String(80), server_default=""),
            sa.Column("claim_type", sa.String(120), server_default="Funeral Claim"),
            sa.Column("claim_date", sa.Date(), nullable=True),
            sa.Column("date_of_death", sa.Date(), nullable=True),
            sa.Column("claim_amount", sa.Numeric(18,2), server_default="0"),
            sa.Column("status", sa.String(60), server_default="Open", nullable=False),
            sa.Column("priority", sa.String(40), server_default="Normal"),
            sa.Column("assigned_to_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("ix_ins_claim_cases_status", "insurance_claim_cases", ["status"])
        op.create_index("ix_ins_claim_cases_franchise", "insurance_claim_cases", ["franchise_name"])
        op.create_index("ix_ins_claim_cases_created", "insurance_claim_cases", ["created_at"])
        op.create_index("ix_ins_claim_cases_archived", "insurance_claim_cases", ["archived"])

    if not _has_table(inspector, "insurance_claim_notes"):
        op.create_table("insurance_claim_notes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("claim_id", sa.Integer(), sa.ForeignKey("insurance_claim_cases.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("user_email", sa.String(255), server_default=""),
            sa.Column("note", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("ix_ins_claim_notes_claim", "insurance_claim_notes", ["claim_id", "created_at"])

    if not _has_table(inspector, "insurance_claim_attachments"):
        op.create_table("insurance_claim_attachments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("claim_id", sa.Integer(), sa.ForeignKey("insurance_claim_cases.id"), nullable=False),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("stored_filename", sa.String(255), nullable=False),
            sa.Column("file_path", sa.String(600), nullable=False),
            sa.Column("content_type", sa.String(120), server_default=""),
            sa.Column("size_bytes", sa.Integer(), server_default="0"),
            sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("ix_ins_claim_attachments_claim", "insurance_claim_attachments", ["claim_id", "created_at"])

    if not _has_table(inspector, "insurance_claim_document_types"):
        op.create_table("insurance_claim_document_types",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_type", sa.String(160), nullable=False, unique=True),
            sa.Column("claim_type", sa.String(120), server_default="Funeral Claim"),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("ix_ins_doc_types_active", "insurance_claim_document_types", ["is_active", "sort_order"])
    if not _has_table(inspector, "insurance_claim_document_rules"):
        op.create_table("insurance_claim_document_rules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_type_id", sa.Integer(), sa.ForeignKey("insurance_claim_document_types.id"), nullable=False),
            sa.Column("rule_key", sa.String(120), nullable=False),
            sa.Column("rule_value", sa.Text(), server_default=""),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("ix_ins_doc_rules_type", "insurance_claim_document_rules", ["document_type_id", "rule_key"])

    permissions = [
        ("Insurance Claims", "view", "insurance_claims:view", "View Insurance Claims", 310),
        ("Insurance Claims", "add", "insurance_claims:add", "Add Insurance Claims", 311),
        ("Insurance Claims", "edit", "insurance_claims:edit", "Edit Insurance Claims", 312),
        ("Insurance Claims", "delete", "insurance_claims:delete", "Delete Insurance Claims", 313),
        ("Insurance Claims", "export", "insurance_claims:export", "Export Insurance Claims", 314),
        ("Insurance Claims", "approve", "insurance_claims:approve", "Approve Insurance Claims", 315),
        ("Insurance Claims", "import", "insurance_claims:import", "Import Insurance Claims", 316),
        ("Insurance Claims", "manage", "insurance_claims:manage", "Manage Insurance Claims", 317),
    ]
    for module, action, code, label, sort_order in permissions:
        bind.execute(sa.text("""
            INSERT INTO permissions (module, action, code, label, sort_order)
            SELECT :module, :action, :code, :label, :sort_order
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
        """), dict(module=module, action=action, code=code, label=label, sort_order=sort_order))
    bind.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.name = 'Admin' AND p.code LIKE 'insurance_claims:%'
        AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id)
    """))

    default_docs = ["Death Certificate", "BI-1663", "Policy Schedule", "ID Copy", "Bank Confirmation", "Claim Form"]
    for idx, doc in enumerate(default_docs, start=1):
        bind.execute(sa.text("""
            INSERT INTO insurance_claim_document_types (document_type, claim_type, sort_order, is_active)
            SELECT :doc, 'Funeral Claim', :sort_order, true
            WHERE NOT EXISTS (SELECT 1 FROM insurance_claim_document_types WHERE document_type = :doc)
        """), {"doc": doc, "sort_order": idx})


def downgrade():
    for table in [
        "insurance_claim_document_rules", "insurance_claim_document_types", "insurance_claim_attachments", "insurance_claim_notes",
        "insurance_claim_cases", "insurance_franchise_mapping", "insurance_import_history", "insurance_policydata_detail_raw",
        "insurance_claims_monthly_raw", "insurance_policy_monthly_raw"
    ]:
        op.drop_table(table)
