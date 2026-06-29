# Graph, Leaderboard and Old Franchise Live Fix

This patch fixes four issues:

1. Performance graphs open on the previous completed month when first viewed.
2. Funerals now uses imported MF Files plus older number_of_funerals records, so funeral graphs and calculations show data.
3. Leaderboards are always sorted by the current live rank after movement is calculated. If a branch drops five places, it appears five places lower.
4. Old/no-data franchise users are separated from active franchise users, and an Old Franchises admin link is added.

No migration is required if v72_perf_inactive is already applied.
