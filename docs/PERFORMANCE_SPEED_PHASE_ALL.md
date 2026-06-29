# Performance Speed Phase - 1 to 3 Second Target

This update changes the Martins Funeral System performance pages from live recalculation to a pre-calculated read path.

## Goal

Target page response time: 1-3 seconds for:

- Graphs
- Royalties / performance results
- Monthly Figures performance follow-up
- Decision Centre
- Executive Dashboard
- Manual Targets
- Growth Brackets

## What changed

### Phase 1 - Database indexes

Migration `v80_perf_fast_cache` adds fast lookup indexes for:

- `performance_results`
- `performance_snapshots`
- `monthly_figures`
- `franchises`

Run after deploy:

```bash
flask db upgrade
```

### Phase 2 - Pre-calculated results

After Monthly Figures Excel import, the system now calls the performance engine once and stores results in `performance_results`.

This means dashboards read saved result rows instead of recalculating every metric on every click.

### Phase 3 - Fast read path

Performance pages now prefer `performance_results` when available.

The following pages are wired to ensure/prefer cached rows:

- `/performance/`
- `/performance/dashboard`
- `/performance/kpi/<metric>`
- `/performance/franchise/<id>`
- `/performance/decision-centre`
- `/performance/executive`
- `/performance/leaderboards`
- `/performance/insights`

### Phase 4 - Manual rebuild options

From the Performance page, Head Office can run:

- Recalculate Current Month
- Rebuild All Performance Cache

Render shell option:

```bash
flask rebuild-performance-cache
```

Use this once after deploy to prepare all historic months.

## Deployment steps

```bash
git checkout development
git pull origin development
# copy/update these files
git add .
git commit -m "Add performance fast cache engine"
git push origin development
```

Then in Render Shell:

```bash
flask db upgrade
flask rebuild-performance-cache
```

After that, restart the Render service.

## Important note

If a page is still slow after this update, check Render logs for the exact slow URL. The next step is to split that page into AJAX sections so the shell loads immediately and cards/graphs load separately.
