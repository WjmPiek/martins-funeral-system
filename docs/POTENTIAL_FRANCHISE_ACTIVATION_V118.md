# Potential Franchise Activation V118

All franchise users and their linked branches are placed in **Admin > Potential Franchises** after migration. Raw master data and monthly figures are retained, but potential branches are excluded from accessible franchise scope, performance, leaderboards, targets, royalty rebuilds, caches, insights and executive decisions.

Only Admin or Finance Manager can activate a branch. Activation enables its owner and employee accounts and makes stored data eligible for the next cache/royalty rebuild. Imports cannot activate a branch.

Deploy steps:
1. `flask db upgrade`
2. Restart web and worker services.
3. Sign in as Admin or Finance Manager.
4. Open **Administration > Potential Franchises** and activate approved branches one by one.
5. Rebuild/warm the required reporting periods after activation.
