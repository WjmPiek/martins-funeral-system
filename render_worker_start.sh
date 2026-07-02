#!/usr/bin/env bash
set -euo pipefail

# Martins persistent job worker for Render Worker services.
# Configure a Render Worker with this start command:
#   bash render_worker_start.sh
# The worker polls PostgreSQL for queued jobs and stores all progress in the DB.

export FLASK_APP=${FLASK_APP:-run.py}
flask release-stale-jobs --stale-minutes 15 --worker-id render-worker-startup || true
exec flask run-job-worker --forever --sleep "${JOB_WORKER_SLEEP_SECONDS:-5}" --worker-id "${JOB_WORKER_ID:-render-worker}" --release-stale --stale-minutes "${JOB_STALE_MINUTES:-15}"
