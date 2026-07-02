from datetime import datetime, timedelta, timezone
import json

from app.extensions import db
from app.models import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStep,
    BusinessRule,
    EnterpriseTask,
    EnterpriseNotification,
    ScheduledJobDefinition,
    EnterpriseAuditTimeline,
    ImportJob,
    SystemEvent,
)


def utcnow():
    return datetime.now(timezone.utc)


DEFAULT_WORKFLOWS = [
    {
        "workflow_key": "month_end_import",
        "name": "Month-end Import Workflow",
        "module": "imports",
        "description": "Controls the month-end upload from validation through publishing and user notification.",
        "steps": [
            {"key": "upload", "label": "Upload accepted"},
            {"key": "validate_file", "label": "Validate file and reporting period"},
            {"key": "match_franchises", "label": "Match franchises"},
            {"key": "validate_agreements", "label": "Validate agreements"},
            {"key": "validate_scales", "label": "Validate royalty scales"},
            {"key": "calculate_royalties", "label": "Calculate royalties"},
            {"key": "rebuild_cache", "label": "Rebuild dashboards and cache"},
            {"key": "publish", "label": "Publish trusted results"},
            {"key": "notify", "label": "Notify users"},
        ],
    },
    {
        "workflow_key": "royalty_rebuild",
        "name": "Royalty Rebuild Workflow",
        "module": "royalties",
        "description": "Validates rules and rebuilds royalty snapshots, summaries, dashboards and insights.",
        "steps": [
            {"key": "validate_period", "label": "Validate reporting period"},
            {"key": "validate_agreements", "label": "Validate agreement profiles"},
            {"key": "validate_scales", "label": "Validate royalty scales"},
            {"key": "calculate", "label": "Recalculate royalties"},
            {"key": "snapshot", "label": "Store calculation snapshots"},
            {"key": "publish", "label": "Publish royalty results"},
        ],
    },
    {
        "workflow_key": "system_diagnostics",
        "name": "System Diagnostics Workflow",
        "module": "operations",
        "description": "Runs operational checks and creates tasks for issues needing review.",
        "steps": [
            {"key": "database", "label": "Check database health"},
            {"key": "imports", "label": "Check import health"},
            {"key": "royalties", "label": "Check royalty diagnostics"},
            {"key": "workers", "label": "Check workers and jobs"},
            {"key": "events", "label": "Check event bus"},
            {"key": "tasks", "label": "Create follow-up tasks"},
        ],
    },
]


DEFAULT_RULES = [
    ("import.reporting_period_required", "Reporting period is required", "imports", "danger", "Month-end imports must use an explicit reporting month and year."),
    ("import.duplicate_period_block", "Duplicate import needs review", "imports", "warning", "Duplicate imports for a reporting period should be reviewed before publishing."),
    ("franchise.active_required", "Franchise must be active", "franchises", "warning", "Imported data should be linked to an active franchise."),
    ("royalty.agreement_required", "Agreement required", "royalties", "danger", "Royalty calculation requires an agreement profile valid for the reporting period."),
    ("royalty.scale_required", "Royalty scale required", "royalties", "danger", "Royalty calculation requires at least one scale row for the franchise."),
    ("jobs.worker_required", "Worker should be online", "operations", "warning", "Queued background jobs require a running worker or Admin manual processing."),
    ("events.no_failed_events", "Failed events need retry", "events", "warning", "Failed event-bus rows should be retried or reviewed."),
]


DEFAULT_SCHEDULES = [
    ("Monthly diagnostics", "monthly_diagnostics", "flask run-workflow system_diagnostics", "Monthly after imports"),
    ("Rebuild business intelligence", "rebuild_business_intelligence", "flask rebuild-business-intelligence", "After trusted month-end publish"),
    ("Rebuild insights", "rebuild_insights", "flask rebuild-insights", "After BI rebuild"),
    ("Release stale jobs", "release_stale_jobs", "flask release-stale-jobs", "Every 15 minutes / manual"),
    ("Process events", "process_events", "flask process-events --release-stale", "Continuous worker / manual"),
]


def emit_timeline(module, action, title, detail="", severity="info", user_id=None, workflow_instance_id=None, import_job_id=None, system_event_id=None, franchise_id=None, commit=False):
    row = EnterpriseAuditTimeline(
        module=module or "system",
        action=action or "info",
        title=title or "",
        detail=detail or "",
        severity=severity or "info",
        user_id=user_id,
        workflow_instance_id=workflow_instance_id,
        import_job_id=import_job_id,
        system_event_id=system_event_id,
        franchise_id=franchise_id,
    )
    db.session.add(row)
    if commit:
        db.session.commit()
    return row


def create_notification(title, message="", module="system", severity="info", target_role=None, target_user_id=None, franchise_id=None, workflow_instance_id=None, system_event_id=None, commit=False):
    row = EnterpriseNotification(
        title=title,
        message=message or "",
        module=module or "system",
        severity=severity or "info",
        notification_type=severity or "info",
        target_role=target_role,
        target_user_id=target_user_id,
        franchise_id=franchise_id,
        workflow_instance_id=workflow_instance_id,
        system_event_id=system_event_id,
    )
    db.session.add(row)
    if commit:
        db.session.commit()
    return row


def create_task(title, description="", module="system", task_type="general", priority="normal", assigned_role="Admin", franchise_id=None, workflow_instance_id=None, business_rule_id=None, source="workflow", due_days=7, commit=False):
    existing = EnterpriseTask.query.filter_by(title=title, status="open", franchise_id=franchise_id, module=module).first()
    if existing:
        return existing
    row = EnterpriseTask(
        title=title,
        description=description or "",
        module=module or "system",
        task_type=task_type or "general",
        priority=priority or "normal",
        assigned_role=assigned_role,
        franchise_id=franchise_id,
        workflow_instance_id=workflow_instance_id,
        business_rule_id=business_rule_id,
        source=source or "workflow",
        due_at=utcnow() + timedelta(days=due_days) if due_days else None,
    )
    db.session.add(row)
    if commit:
        db.session.commit()
    return row


def ensure_default_workflows(commit=False):
    created = 0
    for spec in DEFAULT_WORKFLOWS:
        row = WorkflowDefinition.query.filter_by(workflow_key=spec["workflow_key"]).first()
        if not row:
            row = WorkflowDefinition(workflow_key=spec["workflow_key"], name=spec["name"], module=spec["module"])
            db.session.add(row)
            created += 1
        row.name = spec["name"]
        row.module = spec["module"]
        row.description = spec["description"]
        row.step_template_json = json.dumps(spec["steps"])
        row.is_active = True
    if commit:
        db.session.commit()
    return created


def ensure_default_rules(commit=False):
    created = 0
    for key, name, module, severity, description in DEFAULT_RULES:
        row = BusinessRule.query.filter_by(rule_key=key).first()
        if not row:
            row = BusinessRule(rule_key=key, name=name, module=module, severity=severity, description=description, is_active=True)
            db.session.add(row)
            created += 1
        else:
            row.name = name
            row.module = module
            row.severity = severity
            row.description = description
    if commit:
        db.session.commit()
    return created


def ensure_default_schedules(commit=False):
    created = 0
    for name, key, command, schedule_text in DEFAULT_SCHEDULES:
        row = ScheduledJobDefinition.query.filter_by(job_key=key).first()
        if not row:
            row = ScheduledJobDefinition(name=name, job_key=key, command=command, schedule_text=schedule_text, is_active=True)
            db.session.add(row)
            created += 1
        else:
            row.name = name
            row.command = command
            row.schedule_text = schedule_text
    if commit:
        db.session.commit()
    return created


def ensure_phase13_defaults(commit=False):
    created = {
        "workflows": ensure_default_workflows(commit=False),
        "rules": ensure_default_rules(commit=False),
        "schedules": ensure_default_schedules(commit=False),
    }
    if commit:
        db.session.commit()
    return created


def start_workflow(workflow_key, title=None, module=None, import_job_id=None, franchise_id=None, user_id=None, year=None, month=None, context=None, commit=False):
    definition = WorkflowDefinition.query.filter_by(workflow_key=workflow_key).first()
    if not definition:
        ensure_default_workflows(commit=False)
        definition = WorkflowDefinition.query.filter_by(workflow_key=workflow_key).first()
    instance = WorkflowInstance(
        workflow_definition_id=definition.id if definition else None,
        workflow_key=workflow_key,
        module=module or (definition.module if definition else "system"),
        title=title or (definition.name if definition else workflow_key),
        status="running",
        progress_percent=0,
        import_job_id=import_job_id,
        franchise_id=franchise_id,
        created_by_user_id=user_id,
        year=year,
        month=month,
        context_json=json.dumps(context or {}),
        started_at=utcnow(),
        message="Workflow started.",
    )
    db.session.add(instance)
    db.session.flush()
    steps = definition.step_template if definition else []
    for index, step in enumerate(steps, start=1):
        db.session.add(WorkflowStep(workflow_instance_id=instance.id, step_key=step.get("key"), label=step.get("label"), sort_order=index * 10))
    emit_timeline(instance.module, "workflow.started", instance.title, "Workflow started.", "info", user_id=user_id, workflow_instance_id=instance.id, import_job_id=import_job_id, franchise_id=franchise_id)
    if commit:
        db.session.commit()
    return instance


def update_workflow_step(instance, step_key, status="completed", message="", commit=False):
    if not instance:
        return None
    step = WorkflowStep.query.filter_by(workflow_instance_id=instance.id, step_key=step_key).first()
    now = utcnow()
    if step:
        if status in {"running", "completed", "failed", "blocked"} and not step.started_at:
            step.started_at = now
        if status in {"completed", "failed", "blocked", "skipped"}:
            step.completed_at = now
        step.status = status
        step.message = message or step.message
    instance.current_step_key = step_key
    total = WorkflowStep.query.filter_by(workflow_instance_id=instance.id).count() or 1
    done = WorkflowStep.query.filter(WorkflowStep.workflow_instance_id == instance.id, WorkflowStep.status.in_(["completed", "skipped"])).count()
    instance.progress_percent = min(100, int(done * 100 / total))
    if status in {"failed", "blocked"}:
        instance.status = "needs_review" if status == "blocked" else "failed"
        instance.message = message or f"Step {step_key} {status}."
    elif done >= total:
        instance.status = "completed"
        instance.progress_percent = 100
        instance.completed_at = now
        instance.message = "Workflow completed."
    else:
        instance.status = "running"
        instance.message = message or instance.message
    emit_timeline(instance.module, f"workflow.step.{status}", step.label if step else step_key, message or status, "danger" if status == "failed" else "warning" if status == "blocked" else "info", workflow_instance_id=instance.id, import_job_id=instance.import_job_id, franchise_id=instance.franchise_id)
    if commit:
        db.session.commit()
    return step


def complete_workflow(instance, message="Workflow completed.", commit=False):
    if not instance:
        return None
    now = utcnow()
    for step in WorkflowStep.query.filter_by(workflow_instance_id=instance.id).all():
        if step.status in ("pending", "running"):
            step.status = "completed"
            step.completed_at = now
            if not step.started_at:
                step.started_at = now
    instance.status = "completed"
    instance.progress_percent = 100
    instance.completed_at = now
    instance.message = message
    emit_timeline(instance.module, "workflow.completed", instance.title, message, "info", workflow_instance_id=instance.id, import_job_id=instance.import_job_id, franchise_id=instance.franchise_id)
    create_notification(f"Workflow completed: {instance.title}", message, module=instance.module, severity="success", target_role="Admin", workflow_instance_id=instance.id)
    if commit:
        db.session.commit()
    return instance


def run_diagnostics_workflow(user_id=None, commit=False):
    instance = start_workflow("system_diagnostics", title="System diagnostics workflow", module="operations", user_id=user_id, context={"source": "manual"})
    update_workflow_step(instance, "database", "completed", "Database connection is available.")

    failed_imports = ImportJob.query.filter(ImportJob.status.in_(["failed", "needs_review", "warning"])).count()
    update_workflow_step(instance, "imports", "completed" if failed_imports == 0 else "blocked", f"{failed_imports} import jobs need attention.")
    if failed_imports:
        create_task("Review failed or needs-review imports", f"{failed_imports} import jobs require review before month-end data is fully trusted.", module="imports", task_type="import_review", priority="high", assigned_role="Admin", workflow_instance_id=instance.id)

    try:
        from sqlalchemy import text
        missing_scales = db.session.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT f.id FROM franchises f
                LEFT JOIN royalty_scales rs ON rs.franchise_id = f.id
                GROUP BY f.id
                HAVING COUNT(rs.id) = 0
            ) AS missing
        """)).scalar() or 0
    except Exception:
        missing_scales = 0
    update_workflow_step(instance, "royalties", "completed" if missing_scales == 0 else "blocked", f"{missing_scales} franchises missing royalty scales.")
    if missing_scales:
        create_task("Add missing royalty scales", f"{missing_scales} franchises have no royalty scale configured.", module="royalties", task_type="royalty_setup", priority="high", assigned_role="Admin", workflow_instance_id=instance.id)

    try:
        from app.models import WorkerHeartbeat
        online = [w for w in WorkerHeartbeat.query.order_by(WorkerHeartbeat.heartbeat_at.desc()).limit(20).all() if w.is_online and w.status != "stopped"]
        worker_count = len(online)
    except Exception:
        worker_count = 0
    update_workflow_step(instance, "workers", "completed" if worker_count else "blocked", f"{worker_count} online workers detected.")
    if not worker_count:
        create_task("Start Render background worker", "No online worker heartbeat was detected. Queued imports and event processing may wait.", module="operations", task_type="worker", priority="normal", assigned_role="Admin", workflow_instance_id=instance.id)

    failed_events = SystemEvent.query.filter_by(status="failed").count()
    update_workflow_step(instance, "events", "completed" if failed_events == 0 else "blocked", f"{failed_events} failed system events.")
    if failed_events:
        create_task("Retry failed event-bus rows", f"{failed_events} event-bus rows are failed and should be retried or reviewed.", module="events", task_type="event_retry", priority="normal", assigned_role="Admin", workflow_instance_id=instance.id)

    open_tasks = EnterpriseTask.query.filter_by(status="open").count()
    update_workflow_step(instance, "tasks", "completed", f"{open_tasks} open enterprise tasks.")
    if instance.status not in {"failed", "needs_review"}:
        complete_workflow(instance, "Diagnostics completed with no blocking issues.")
    else:
        instance.message = "Diagnostics completed with review tasks."
        create_notification("Diagnostics need review", instance.message, module="operations", severity="warning", target_role="Admin", workflow_instance_id=instance.id)
    if commit:
        db.session.commit()
    return instance


def workflow_summary():
    return {
        "definitions": WorkflowDefinition.query.count(),
        "running": WorkflowInstance.query.filter_by(status="running").count(),
        "needs_review": WorkflowInstance.query.filter(WorkflowInstance.status.in_(["needs_review", "failed"])).count(),
        "open_tasks": EnterpriseTask.query.filter_by(status="open").count(),
        "unread_notifications": EnterpriseNotification.query.filter_by(is_read=False).count(),
        "active_rules": BusinessRule.query.filter_by(is_active=True).count(),
        "schedules": ScheduledJobDefinition.query.filter_by(is_active=True).count(),
    }
