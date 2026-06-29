# Performance Intelligence Phase 6 - Graph Engine

Phase 6 adds decision graphs to the Performance Intelligence platform.

## Added

- Actual vs Target graph data
- Same Month Previous Year comparison graph data
- Rolling 12-month trend graph data
- Forecast vs Target graph data
- Growth Trend graph data
- Graph sections on the franchise performance page
- Graph sections on each KPI page

## KPIs supported

- Cash
- Sales
- Insurance Premiums
- Joinings
- Funerals

## Deployment

No new migration is required for Phase 6. Push the files and let Render redeploy.

```bash
flask db current
```

Expected head remains whatever Phase 5/previous database head is, normally:

```text
v70_perf_intel_p3
```

## Notes

The graphs are rendered with lightweight HTML/CSS so they do not require a new JavaScript chart library yet. A later phase can replace these with Chart.js or another interactive charting library if desired.
