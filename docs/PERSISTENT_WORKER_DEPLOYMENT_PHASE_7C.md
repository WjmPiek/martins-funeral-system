# Phase 7C - Persistent Worker Deployment

This build completes the operational side of the persistent job queue.

## Added

- Continuous worker CLI mode:

```bash
flask run-job-worker --forever --sleep 5 --release-stale
```

- Queue-specific worker options:

```bash
flask run-job-worker --queue default --worker-id render-worker-1
```

- Stale job release CLI:

```bash
flask release-stale-jobs --stale-minutes 15
```

- Render worker start script:

```bash
bash render_worker_start.sh
```

- Operations Centre button to release all stale jobs.

## Render setup

Create a separate Render Worker service that uses the same repo, branch and environment variables as the web service.

Use this start command:

```bash
bash render_worker_start.sh
```

The worker does not store state in memory. Jobs, progress, locks, logs, attempts and results are stored in PostgreSQL.

## Safe restart behavior

If Render restarts the worker during an import:

1. The job remains in `import_jobs`.
2. The stale lock is detected by heartbeat age.
3. Admin can release stale jobs from the Operations Centre.
4. The worker can release stale jobs automatically on startup and while polling.
5. The queued job can be retried without uploading the file again, as long as the stored upload file is still present.

## Important

For long-term import retry after a full Render filesystem replacement, uploaded source files should eventually be stored in persistent object storage. This build makes the queue persistent in PostgreSQL and protects against normal worker restarts, but Render's ephemeral filesystem can still remove uploaded source files after redeploys.
