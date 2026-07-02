# Phase 5 - Performance & Cache Stabilization

This phase adds a persistent performance cache layer so dashboards and graphs do not recalculate heavy data on every login/page load.

## Added

- `performance_page_cache` table for expensive JSON payloads.
- Cache helpers in `app/performance/cache.py`.
- Graph payload cache for:
  - all-franchise aggregate graphs
  - individual franchise graphs
- Automatic cache invalidation/rebuild during trusted financial publishing.
- Database diagnostics cache status panel.
- Additional DB indexes for monthly figures, performance results and active franchises.

## Behaviour

1. Month-end import finishes.
2. Royalties are recalculated.
3. Trusted financials are published.
4. Phase 5 invalidates stale cache rows for that month/year.
5. Performance result rows are rebuilt.
6. Graph cache rows are warmed before users are notified.
7. Admin/Finance/Franchise users open dashboards from cached data.

## Migration

- Revision: `v90_perf_cache`
- Previous: `v89_live_refresh`

Run on Render:

```bash
flask db current
flask db upgrade
flask db current
```

Expected head after deploy:

```text
v90_perf_cache (head)
```
