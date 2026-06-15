"""MFF manuals module

Revision ID: v62_mff_manuals_module
Revises: v61_attendance_module
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

revision = "v62_mff_manuals_module"
down_revision = "v61_attendance_module"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "mff_manuals" not in tables:
        op.create_table("mff_manuals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("confidentiality_note", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_mff_manuals_title", "mff_manuals", ["title"])
    if "mff_manual_versions" not in tables:
        op.create_table("mff_manual_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("manual_id", sa.Integer(), sa.ForeignKey("mff_manuals.id"), nullable=False),
            sa.Column("version_label", sa.String(length=80), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=100), nullable=False),
            sa.Column("storage_path", sa.String(length=600), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=False),
            sa.Column("is_published", sa.Boolean(), nullable=False),
            sa.UniqueConstraint("manual_id", "version_label", name="uq_mff_manual_version_label"),
        )
        op.create_index("ix_mff_manual_versions_manual_id", "mff_manual_versions", ["manual_id"])
        op.create_index("ix_mff_manual_versions_is_published", "mff_manual_versions", ["is_published"])
    if "mff_index_documents" not in tables:
        op.create_table("mff_index_documents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("storage_path", sa.String(length=600), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=False),
            sa.Column("manual_id", sa.Integer(), sa.ForeignKey("mff_manuals.id"), nullable=True),
            sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
        )
        op.create_index("ix_mff_index_documents_title", "mff_index_documents", ["title"])
        op.create_index("ix_mff_index_documents_manual_id", "mff_index_documents", ["manual_id"])
        op.create_index("ix_mff_index_documents_is_active", "mff_index_documents", ["is_active"])
    if "mff_manual_acknowledgements" not in tables:
        op.create_table("mff_manual_acknowledgements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("manual_version_id", sa.Integer(), sa.ForeignKey("mff_manual_versions.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("attested_name", sa.String(length=255), nullable=False),
            sa.Column("attested_at", sa.DateTime(), nullable=False),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=500), nullable=True),
            sa.UniqueConstraint("manual_version_id", "user_id", name="uq_mff_ack_manual_user"),
        )
        op.create_index("ix_mff_manual_acknowledgements_manual_version_id", "mff_manual_acknowledgements", ["manual_version_id"])
        op.create_index("ix_mff_manual_acknowledgements_user_id", "mff_manual_acknowledgements", ["user_id"])

    permissions = [
        ("Manuals", "view", "manuals:view", "View Manuals", 910),
        ("Manuals", "manage", "manuals:manage", "Manage Manuals", 911),
        ("Manuals", "upload", "manuals:upload", "Upload Manuals", 912),
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
        WHERE r.name = 'Admin' AND p.code IN ('manuals:view','manuals:manage','manuals:upload')
        AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id)
    """))


def downgrade():
    op.drop_table("mff_manual_acknowledgements")
    op.drop_table("mff_index_documents")
    op.drop_table("mff_manual_versions")
    op.drop_table("mff_manuals")
