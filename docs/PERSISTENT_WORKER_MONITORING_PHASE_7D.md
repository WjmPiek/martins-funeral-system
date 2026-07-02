# Persistent Worker Monitoring Phase 7D

Adds a durable `worker_heartbeats` table and Operations Centre worker monitor.

## What changed

- New migration `v93_worker_heartbeat`.
- Worker heartbeat table stored in PostgreSQL.
- CLI worker updates heartbeat while polling and processing.
- Job progress updates refresh the worker heartbeat while imports run.
- Operations Centre now shows online workers, queue, active job, heartbeat time, host and status.

## Deploy

```bash
flask db current
flask db upgrade
flask db current
```

Expected head: `v93_worker_heartbeat`.

## Worker command

```bash
flask run-job-worker --forever --release-stale --worker-id render-worker-1
```
