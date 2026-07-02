# Phase 10 - Executive Dashboard

Adds an Admin/Finance Executive Dashboard for directors and senior users.

## Included

- Company-wide KPI overview for a selected month/year
- Gross turnover, royalties, payover, franchises reporting, funerals and joinings
- Month-on-month comparison indicators
- Top 10 and bottom 10 franchises by gross turnover
- Province performance summary
- Executive alerts for imports, royalties, events, cache and workers
- Recent import status
- Quick links to Import Centre, Royalty Management, Operations Centre, Performance Graphs, Leaderboard and Database Diagnostics

## Security

The page uses the existing Admin/Finance Operations Centre access gate. Franchise users cannot access it.

## Migration

`v96_exec_dashboard` is a phase marker migration only. No database schema changes are required.

After deploy:

```bash
flask db current
flask db upgrade
flask db current
```

Expected head:

```text
v96_exec_dashboard (head)
```
