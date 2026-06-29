# Security, User Hierarchy and Growth Target Fix

This patch completes the Martins Funerals South Africa / franchise hierarchy and adds automatic growth calculations.

## User hierarchy fixed

- Admin/Super Admin bypass missing permission-row 403 errors on Admin screens.
- Admin > Users creates mother-company users only:
  - Finance Manager
  - Finance Assistant
  - Regional Manager
  - Franchise User
- Franchise Details > Employees creates franchise employees only:
  - Franchise Manager
  - Franchise Employee
  - Franchise Agent
- Admin > Employees is a master management list for franchise-created employees.
- Admin/Finance users are removed from incorrect franchise-user links by migration.
- Protected admin user is kept active and assigned the Admin role.

## Growth formulas added

The performance service now calculates:

- Monthly growth: `(Current Month - Previous Month) / Previous Month x 100`
- Year-to-date growth: `(Current YTD - Previous YTD) / Previous YTD x 100`
- Annual growth: `(Current Year - Previous Year) / Previous Year x 100`
- Average monthly growth: average of the last 12 monthly growth percentages
- Three-year growth: `(Current Period - Same Period 3 Years Ago) / Same Period 3 Years Ago x 100`

Growth status:

- Green / Growing: greater than 10%
- Yellow / Stable: 0% to 10%
- Red / Declining: below 0%

## Automatic fair targets

When performance results are rebuilt, generated fair targets are stored automatically in `franchise_targets` if no Head Office manual target exists yet.

Default fair growth brackets are seeded for:

- Cash
- Sales
- Insurance Premiums
- Joinings
- Funerals

## Deployment

After pushing to Render, run:

```bash
flask db upgrade
```

Expected head:

```text
v78_security_growth
```
