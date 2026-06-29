# Physical Graph Rendering Fix

This patch replaces the old text/bar data display for Performance Intelligence graphs with real inline SVG graphs rendered in the browser without external chart libraries.

## What changed

- Added shared chart helper template: `app/templates/performance/_graph_charts.html`
- Updated franchise performance page: `app/templates/performance/franchise.html`
- Updated KPI performance page: `app/templates/performance/kpi.html`

## What it fixes

- Users were seeing values/data but not proper physical graphs.
- The new graph renderer draws real SVG line charts for:
  - Actual vs Target
  - Same Month Previous Year
  - Forecast vs Target
  - Rolling 12-Month Total
  - Growth Trend

## How it works

- No database migration needed.
- No CDN or internet dependency needed.
- The graph reads the existing `graph_data` already supplied by the Performance service.
- Each graph still includes an expandable data table for checking the source values.

## Deploy

Copy the files into the project, then run:

```powershell
git add .
git commit -m "Fix performance physical graph rendering"
git push origin development
```

Then redeploy Render. No `flask db upgrade` is needed for this patch.
