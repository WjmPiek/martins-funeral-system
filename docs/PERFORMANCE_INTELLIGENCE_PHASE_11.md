# Performance Intelligence Phase 11 - Identity, Security and History

Phase 11 adds the foundation for secure personalised dashboards and frozen performance history.

## Included

- Performance History snapshots
- Capture History button for Head Office
- User Access Overview page
- User dashboard preference model
- Data-scope-aware history views
- Admin permissions for history and user access review

## New pages

- `/performance/history`
- `/performance/access-overview`

## New migration

- `v71_perf_intel_p11`

## How it works

Every time Head Office captures a month, the system stores the calculated KPI values for each franchise and KPI:

- Cash
- Sales
- Insurance Premiums
- Joinings
- Funerals

Each snapshot stores actual, target, target achievement, growth, forecast, rank and movement.  This creates a historical record that does not change when growth brackets or formulas are changed later.

## Security model

The pages use the existing role/permission and user-franchise assignment model:

- Admin users with franchise-management permissions can see all franchises.
- Franchise users only see assigned franchises.
- Branch or regional managers only see the franchises assigned to their user account.
- The access overview page is restricted to `users:manage`.

## Recommended next test

1. Deploy to Render development.
2. Run `flask db upgrade`.
3. Open Performance History.
4. Capture the current month.
5. Login as a franchise user and confirm only assigned franchise history is visible.
6. Open User Access Overview as Admin and confirm user modules and franchise scopes are correct.
