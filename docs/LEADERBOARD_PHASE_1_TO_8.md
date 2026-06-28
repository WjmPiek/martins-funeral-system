# Leaderboard Phase 1 to 8 Build Plan

Each phase is designed to build on the previous phase. Do not deploy a later phase without the earlier database migration and permission updates.

## Phase 1 - Base Leaderboard
- Add `FranchiseTarget` database table.
- Add Leaderboard blueprint and sidebar link.
- Rank franchises from monthly figures.
- Fallback ranking uses gross turnover until targets are captured.

## Phase 2 - Rank Movement
- Compare current rank to previous month.
- Show Up in green, Down in red, Same in orange.
- Keep movement calculation in backend so dashboard and reports use the same result.

## Phase 3 - Franchise Dashboard Widget
- Show each franchise user's own leaderboard position on their dashboard.
- Show rank, total franchises in comparison set, movement, and target percentage.
- Add button from dashboard to full leaderboard.

## Phase 4 - Targets and Time Comparison
- Manage monthly targets per franchise.
- Compare previous month or same month last year.
- Prepare structure for daily/weekly targets once daily source data exists.

## Phase 5 - Role Visibility
- Admin sees all franchises.
- Branch Manager sees assigned/group franchises.
- Franchise User sees only assigned franchise/group context.
- No one outside the allowed franchise list can see that franchise ranking.

## Phase 6 - Weighted Score
- Score uses gross turnover, sales, insurance joinings, MF files, and royalty amount.
- Target achievement is capped per metric so one large metric does not hide weak areas.
- Weights can be adjusted later from settings.

## Phase 7 - Audit and Reports
- Target changes write to audit log.
- Leaderboard data can be reused for future PDF/Excel reports.
- Suggested next report: monthly group leaderboard PDF.

## Phase 8 - Production Hardening
- Keep leaderboard calculations in shared helper functions.
- Reuse same helper on dashboard and leaderboard page.
- Ready for future scheduled reminders and exports.

## Dashboard answer
Yes. The leaderboard now appears on each selected franchise dashboard when the user has `leaderboard:view`. It shows where that franchise falls on the leaderboard for the current period.
