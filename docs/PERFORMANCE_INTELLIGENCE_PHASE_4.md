# Performance Intelligence Phase 4

Phase 4 adds the franchise-facing performance dashboard.

## Included

- New `/performance/dashboard` page.
- Franchise business health score out of 100.
- KPI cards for Cash, Sales, Insurance Premiums, Joinings and Funerals.
- Target percentage per KPI.
- Actual vs target difference.
- Previous month, same month last year and 3-year average comparison.
- Decision indicators that highlight KPIs above target, close to target or below target.
- Dashboard route respects the logged-in user's franchise access.
- Leaderboard remains simple: rank, franchise name and movement only.

## Notes

No database migration is required for Phase 4. It uses the Phase 1-3 target and performance engine tables.

## Deploy

Push to the development branch and redeploy Render. Run `flask db current` only to confirm the database is already at the latest head.
