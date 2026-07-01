# Database Diagnostics

Adds an Admin-only Database Diagnostics page at:

`/admin/database-diagnostics`

The page checks:

- franchises missing royalty scales
- franchises missing agreement start/end dates
- franchise users not linked to a franchise
- franchise employees without a parent franchise user
- duplicate franchise names
- orphan monthly figures
- latest import jobs and progress
- latest monthly totals
- monthly figures with gross turnover but zero royalty amount

The page is linked under the Admin menu as **Database Diagnostics**.
