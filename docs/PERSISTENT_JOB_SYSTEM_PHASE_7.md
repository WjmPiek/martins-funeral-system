# Phase 7 - Persistent Job System

This phase adds a durable PostgreSQL-backed job queue for long-running work such as month-end imports, royalty recalculation, performance cache rebuilds and live publishing.

## What changed

- `ImportJob` is now a persistent queue record as well as an import-progress record.
- Added `ImportJobLog` for permanent job execution logs.
- Added `app/jobs.py` with queue helpers:
  - enqueue jobs
  - claim jobs safely
  - run jobs
  - retry failed jobs
  - cancel jobs
  - release stale Render-locked jobs
- Added Operations Centre controls:
  - Run Next Job
  - Retry failed/needs-review jobs
  - Cancel running/queued jobs
  - Release stale jobs
  - View job execution log
- Added CLI commands:
  - `flask enqueue-noop-job`
  - `flask run-next-job`
  - `flask run-job-worker`
- Added migration `v92_job_queue`.

## Deployment

Run:

```bash
flask db current
flask db upgrade
flask db current
```

Expected result:

```text
v92_job_queue (head)
```

## Render worker option

For a future true worker service, create a Render Background Worker using the same repo and environment variables with command:

```bash
flask run-job-worker
```

The queue is stored in PostgreSQL, so job state survives web service restarts.

## Notes

Existing imports still run safely in the web process, but their job records are now durable and auditable. The next integration step is moving each specific import handler fully into the persistent queue so uploads return immediately and the worker performs the heavy processing.
