# Phase 13 - Enterprise Workflow & Automation Suite

This phase adds the first enterprise operations subsystem above the event bus, jobs, royalty engine, BI and insights layers.

## Included

- Workflow definitions and workflow instances
- Workflow step tracking
- Configurable business rules
- Enterprise task centre
- Enterprise notification centre
- Scheduled automation definitions
- Unified enterprise audit timeline
- Admin page: **Workflows & Automation**
- CLI commands:
  - `flask seed-workflow-defaults`
  - `flask run-diagnostics-workflow`
  - `flask workflow-summary`
- New migration: `v99_workflow_engine`

## Purpose

The system can now manage operational work instead of only showing reports. Month-end imports, royalty rebuilds, diagnostics and future modules can be represented as visible workflows with tasks and notifications.

## Safe deployment

After deploying, run:

```bash
flask db current
flask db upgrade
flask db current
flask seed-workflow-defaults
```

Expected head:

```text
v99_workflow_engine (head)
```

## Notes

This phase does not change royalty calculation formulas. It adds coordination, visibility and operations management around the existing enterprise platform.
