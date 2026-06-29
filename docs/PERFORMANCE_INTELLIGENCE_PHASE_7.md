# Performance Intelligence Phase 7 - Leaderboard Decision Centre

Phase 7 adds an improved leaderboard system on top of Phase 6.

## Included

- Overall leaderboard.
- KPI-specific leaderboards for Cash, Sales, Insurance, Joinings and Funerals.
- Current rank controls where the franchise appears.
- Previous month rank only calculates movement.
- Display stays simple: rank, franchise name, and Up/Down/Same.
- Shows biggest climber and biggest dropper for decision making.
- Adds `/performance/leaderboards`.

## Movement logic

- Previous rank 16 and current rank 13 = Up by 3.
- Previous rank 13 and current rank 16 = Down by 3.
- Same rank = Same.

## Notes

No database migration is required for Phase 7.
Push the files and redeploy Render.
