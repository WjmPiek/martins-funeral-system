"""Import progress, improved contract matching and UI/currency polish

Revision ID: v87_import_ui
Revises: v86_async_perf
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "v87_import_ui"
down_revision = "v86_async_perf"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("message", sa.String(length=255), nullable=True),
        sa.Column("total_steps", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra_json", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
    )
    op.create_index("ix_import_jobs_kind", "import_jobs", ["kind"])
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"])
    op.create_index("ix_import_jobs_started_at", "import_jobs", ["started_at"])
    op.create_index("ix_import_jobs_created_by_id", "import_jobs", ["created_by_id"])


def downgrade():
    op.drop_index("ix_import_jobs_created_by_id", table_name="import_jobs")
    op.drop_index("ix_import_jobs_started_at", table_name="import_jobs")
    op.drop_index("ix_import_jobs_status", table_name="import_jobs")
    op.drop_index("ix_import_jobs_kind", table_name="import_jobs")
    op.drop_table("import_jobs")
