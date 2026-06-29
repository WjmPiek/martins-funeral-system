# Performance Intelligence Phase 12 - Inactive Franchise Control

## Purpose
Franchises with no imported KPI data for the last 3 months should not distort the system.
They are hidden from:

- Performance calculations
- Growth targets
- Graphs
- Leaderboards
- Performance history snapshots
- Executive dashboards
- Decision Centre lists

They remain in the database and can be reactivated by Super Admin/Admin/Finance Manager users.

## How inactivity is detected
A franchise is considered inactive when there is no non-zero imported KPI value in the 3-month period ending with the selected reporting month.
The KPI fields checked are:

- Cash
- Sales
- Insurance Premiums
- Joinings
- Funerals

## New fields on franchises
- `is_performance_active`
- `performance_inactive_at`
- `performance_inactive_reason`
- `performance_reactivated_at`
- `performance_reactivated_by_id`

## New permission
- `performance:manage_inactive`

This is granted to Admin, Super Admin, Finance Manager and Finance roles where those roles exist.

## New page
`/performance/inactive-franchises`

This page lets authorised users:

1. Check franchises for the selected reporting period.
2. Auto-hide franchises with no KPI data in the last 3 months.
3. Reactivate a hidden franchise when Head Office or Finance confirms it should be included again.

## Important behaviour
Hidden franchises are not deleted.
Their historic monthly figures remain untouched.
When reactivated, they immediately become part of calculations, targets, graphs and leaderboards again.
