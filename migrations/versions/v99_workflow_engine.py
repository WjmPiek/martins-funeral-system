"""Enterprise workflow and automation suite

Revision ID: v99_workflow_engine
Revises: v98_insights_engine
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "v99_workflow_engine"
down_revision = "v98_insights_engine"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("workflow_key", sa.String(length=120), nullable=False),
        sa.Column("module", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("step_template_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workflow_definitions_name", "workflow_definitions", ["name"], unique=True)
    op.create_index("ix_workflow_definitions_workflow_key", "workflow_definitions", ["workflow_key"], unique=True)
    op.create_index("ix_workflow_definitions_module", "workflow_definitions", ["module"])
    op.create_index("ix_workflow_definitions_is_active", "workflow_definitions", ["is_active"])

    op.create_table(
        "workflow_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workflow_definition_id", sa.Integer(), sa.ForeignKey("workflow_definitions.id"), nullable=True),
        sa.Column("workflow_key", sa.String(length=120), nullable=False),
        sa.Column("module", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("title", sa.String(length=220), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("current_step_key", sa.String(length=120), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("priority", sa.String(length=30), nullable=False, server_default="normal"),
        sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("import_jobs.id"), nullable=True),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("message", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    for col in ["workflow_definition_id", "workflow_key", "module", "status", "current_step_key", "priority", "import_job_id", "franchise_id", "created_by_user_id", "year", "month", "started_at", "completed_at", "created_at"]:
        op.create_index(f"ix_workflow_instances_{col}", "workflow_instances", [col])

    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workflow_instance_id", sa.Integer(), sa.ForeignKey("workflow_instances.id"), nullable=False),
        sa.Column("step_key", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=220), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    for col in ["workflow_instance_id", "step_key", "status", "sort_order", "created_at"]:
        op.create_index(f"ix_workflow_steps_{col}", "workflow_steps", [col])

    op.create_table(
        "business_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_key", sa.String(length=140), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("module", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("severity", sa.String(length=30), nullable=False, server_default="warning"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_business_rules_rule_key", "business_rules", ["rule_key"], unique=True)
    for col in ["module", "severity", "is_active", "created_at"]:
        op.create_index(f"ix_business_rules_{col}", "business_rules", [col])

    op.create_table(
        "enterprise_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("module", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("task_type", sa.String(length=80), nullable=False, server_default="general"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=30), nullable=False, server_default="normal"),
        sa.Column("assigned_role", sa.String(length=120), nullable=True),
        sa.Column("assigned_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
        sa.Column("workflow_instance_id", sa.Integer(), sa.ForeignKey("workflow_instances.id"), nullable=True),
        sa.Column("business_rule_id", sa.Integer(), sa.ForeignKey("business_rules.id"), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    for col in ["module", "task_type", "status", "priority", "assigned_role", "assigned_user_id", "franchise_id", "workflow_instance_id", "business_rule_id", "source", "due_at", "completed_at", "created_at"]:
        op.create_index(f"ix_enterprise_tasks_{col}", "enterprise_tasks", [col])

    op.create_table(
        "enterprise_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("module", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("notification_type", sa.String(length=80), nullable=False, server_default="info"),
        sa.Column("severity", sa.String(length=30), nullable=False, server_default="info"),
        sa.Column("target_role", sa.String(length=120), nullable=True),
        sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
        sa.Column("workflow_instance_id", sa.Integer(), sa.ForeignKey("workflow_instances.id"), nullable=True),
        sa.Column("system_event_id", sa.Integer(), sa.ForeignKey("system_events.id"), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("read_at", sa.DateTime(), nullable=True),
    )
    for col in ["module", "notification_type", "severity", "target_role", "target_user_id", "franchise_id", "workflow_instance_id", "system_event_id", "is_read", "created_at"]:
        op.create_index(f"ix_enterprise_notifications_{col}", "enterprise_notifications", [col])

    op.create_table(
        "scheduled_job_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("job_key", sa.String(length=120), nullable=False),
        sa.Column("command", sa.String(length=220), nullable=False, server_default=""),
        sa.Column("schedule_text", sa.String(length=220), nullable=False, server_default="Manual"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_scheduled_job_definitions_name", "scheduled_job_definitions", ["name"], unique=True)
    op.create_index("ix_scheduled_job_definitions_job_key", "scheduled_job_definitions", ["job_key"], unique=True)
    for col in ["is_active", "last_run_at", "next_run_at"]:
        op.create_index(f"ix_scheduled_job_definitions_{col}", "scheduled_job_definitions", [col])

    op.create_table(
        "enterprise_audit_timeline",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("action", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=220), nullable=False, server_default=""),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(length=30), nullable=False, server_default="info"),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("workflow_instance_id", sa.Integer(), sa.ForeignKey("workflow_instances.id"), nullable=True),
        sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("import_jobs.id"), nullable=True),
        sa.Column("system_event_id", sa.Integer(), sa.ForeignKey("system_events.id"), nullable=True),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    for col in ["module", "action", "severity", "user_id", "workflow_instance_id", "import_job_id", "system_event_id", "franchise_id", "created_at"]:
        op.create_index(f"ix_enterprise_audit_timeline_{col}", "enterprise_audit_timeline", [col])


def downgrade():
    op.drop_table("enterprise_audit_timeline")
    op.drop_table("scheduled_job_definitions")
    op.drop_table("enterprise_notifications")
    op.drop_table("enterprise_tasks")
    op.drop_table("business_rules")
    op.drop_table("workflow_steps")
    op.drop_table("workflow_instances")
    op.drop_table("workflow_definitions")
