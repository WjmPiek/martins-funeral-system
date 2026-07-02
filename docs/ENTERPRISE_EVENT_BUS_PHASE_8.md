# Phase 8 - Enterprise Event Bus & Live Synchronisation

This phase introduces the first complete enterprise subsystem: a PostgreSQL-backed event bus.

## Added

- `system_events` table for durable business events.
- `event_subscriptions` table for Admin-visible subsystem registry.
- `event_processing_logs` table for processing/replay diagnostics.
- `app/events.py` service module with:
  - `emit_event(...)`
  - `process_pending_events(...)`
  - `retry_event(...)`
  - `release_stale_events(...)`
  - `ensure_default_subscriptions(...)`
- Operations Centre event monitor.
- Operations Centre buttons:
  - Process Pending Events
  - Release Stale Events
  - Retry failed event
- CLI commands:
  - `flask process-events`
  - `flask process-events --release-stale`
  - `flask seed-event-subscriptions`
- Migration: `v94_event_bus`.

## Why this matters

Imports, royalties, cache rebuilds, notifications, dashboards, attendance and claims can now coordinate through a durable event stream rather than directly depending on each other.

## Initial event types

- `monthly_import_published`
- `trusted_financials_published`
- `job.completed`
- `job.failed`
- `job.retry_scheduled`
- `cache.rebuilt`
- future hooks for `attendance.updated` and `claim.created`

## Deploy

```bash
flask db current
flask db upgrade
flask db current
flask seed-event-subscriptions
```

Expected head:

```text
v94_event_bus (head)
```

## Manual processing

```bash
flask process-events --limit 50 --release-stale
```

The event bus is safe to run manually from Render Shell. Future phases can add a dedicated worker that continuously processes events.
