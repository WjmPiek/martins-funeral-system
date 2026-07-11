# Enterprise Performance Refactor V121

## Purpose

V121 removes analytics rebuilding from normal user page requests. The system now treats imports, explicit Admin refresh actions, and CLI commands as the only places where heavy performance and graph caches are built.

## Main changes

- `ensure_performance_results()` is now a read-only readiness check and never starts a rebuild inside a GET request.
- Aggregate and franchise graph payloads return an immediate `cache_status: missing` response when a cache is not ready instead of calculating years of data while the browser waits.
- Month-end imports rebuild the selected period and warm the aggregate graph cache before publishing trusted financials.
- Common target modes bulk-load prior periods instead of querying once for every franchise/metric cell.
- Accessible franchise lists are cached once per request.
- Live-status polling changed from every 10 seconds to every 45 seconds and pauses while the browser tab is hidden.
- Every response now includes `Server-Timing` and `X-Response-Time-Ms` headers. Requests slower than 1.5 seconds are logged as `SLOW_REQUEST`.

## New commands

Create indexes and refresh PostgreSQL planner statistics:

```bash
flask optimize-performance-indexes
```

Warm one reporting period before users open dashboards:

```bash
flask warm-analytics-cache --month 6 --year 2026
```

Existing full performance rebuild command remains available:

```bash
flask rebuild-performance-cache --month 6 --year 2026
```

## Deployment sequence

```bash
flask db upgrade
flask optimize-performance-indexes
flask warm-analytics-cache --month 6 --year 2026
```

Restart the Render web service after completing the commands.

## Render start command

For a 2 GB / 1 CPU service, begin with:

```bash
gunicorn run:app --workers 2 --threads 4 --worker-class gthread --timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100
```

Monitor memory and PostgreSQL connection usage before increasing worker counts.

## Expected behavior

- Cached graph and dashboard pages should respond quickly.
- A missing cache no longer blocks for 40-60 seconds.
- Imports take longer because they prepare analytics before publishing, but users no longer pay that calculation cost on every page view.
- Slow routes are identifiable in Render logs using the `SLOW_REQUEST` marker.
