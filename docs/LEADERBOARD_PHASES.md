# Leaderboard Build Phases

## Phase 1 - Leaderboard foundation
- New `/leaderboard` module and sidebar link.
- Role permission `leaderboard:view`.
- Rank franchises by weighted performance.
- Show franchise name, leaderboard number, and movement.

## Phase 2 - Rank movement
- Compare current ranking to previous month or same month last year.
- Movement colors:
  - Green = Up
  - Red = Down
  - Orange = Same

## Phase 3 - Targets
- New `franchise_targets` table.
- Target capture screen at `/leaderboard/targets`.
- Monthly targets for gross turnover, sales, insurance joinings, MF files, and royalty amount.

## Phase 4 - Target scoring
- Leaderboard score is weighted by target achievement:
  - Gross turnover 40%
  - Sales 20%
  - Insurance joinings 15%
  - MF files 10%
  - Royalty amount 15%
- If targets are not captured yet, the system falls back to gross turnover ranking.

## Phase 5 - Role visibility
- Admin and finance users can see allowed branches according to existing franchise access rules.
- Franchise-side users only see franchises they are allowed to access.
- Target management is controlled by `leaderboard:manage_targets`.

## Future phase suggestions
- Add daily/weekly leaderboards once daily sales/services data exists.
- Add group-level leaderboard views if group membership is formalized in its own table.
- Add leaderboard snapshots if you want historical rank reports that never change after month-end lock.
