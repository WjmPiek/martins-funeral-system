# Phase 7B - Persistent Import Worker Integration

This build connects the persistent PostgreSQL job queue to the month-end import flow.

## Included

- PDF imports are saved to `instance/job_uploads/` and queued as `monthly_pdf_import` jobs.
- Excel imports are saved to `instance/job_uploads/` and queued as `monthly_excel_import` jobs.
- Upload pages return immediately with a Job ID instead of blocking while the import runs.
- Admin/Finance can monitor the queued/running import in Import Centre.
- Operations Centre `Run next job` processes queued import jobs.
- CLI workers can process queued jobs with `flask run-next-job` or `flask run-job-worker`.
- Job handlers update progress stages and write logs to `import_job_logs`.
- Imported data is published only after validation, royalty recalculation and pipeline processing.

## Worker commands

Run one queued job:

```bash
flask run-next-job
```

Run until the queue is empty:

```bash
flask run-job-worker
```

## Notes

This build does not need a new database migration because Phase 7 already added the required queue fields in `v92_job_queue`.
