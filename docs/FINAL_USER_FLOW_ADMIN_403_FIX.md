# Final User Flow + Admin 403 Fix

This patch fixes the final Martins mother-company/franchise user hierarchy and the 403 after login.

## Fixed

- Admin and Super Admin are no longer blocked from Admin screens because of missing permission seed rows.
- Admin and Finance Manager log in to Admin > Users instead of being forced to Dashboard.
- Franchise and Regional users log in to Franchise Details because Dashboard is removed for franchise users.
- Admin > Users has a clear Create Martins User form.
- Admin-created users are only: Finance Manager, Finance Assistant, Regional Manager, Franchise User.
- Finance Manager / Finance Assistant are not linked to any franchise.
- Regional Manager / Franchise User can be linked to selected franchise(s).
- Franchise Details > Employees has the Add Employee form for Manager, Employee and Agent.
- Admin > Employees remains the master list to manage franchise-created employees.

## Migration

No migration is required if the database is already on `v76_user_creation_scope`.
