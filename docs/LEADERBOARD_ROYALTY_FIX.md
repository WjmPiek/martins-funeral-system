# Leaderboard Display and Royalty Bracket Fix

## Leaderboard
- The leaderboard page now shows only:
  - Number/rank
  - Franchise name
  - Movement
- The current period rank determines the row position.
- Movement is calculated from previous rank minus current rank:
  - Previous 16, current 13 = Up by 3
  - Previous 13, current 16 = Down by 3
  - Same position = Same
- Cash, sales, target percentages, score, royalties and all figures were removed from the leaderboard view.
- The franchise dashboard leaderboard card also no longer shows target percentage.

## Royalty calculation
- Royalty calculation now prioritizes each franchise user's own structured royalty scale brackets.
- Open-ended final brackets with blank/0 Amount To are treated as open-ended instead of ignored.
- The raw imported scale text is used only when structured brackets are missing.
- Matching franchise records are checked before falling back to a flat imported percentage.
- The flat imported percentage is now only a last-resort fallback.

After deploying, run `flask db upgrade` only if new migrations are included. This patch does not include a migration.
