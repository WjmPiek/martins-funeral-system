# Core Business Repair v106

This release repairs **Admin -> Data Integrity** and makes the Franchise Master workflow the production repair centre.

## Included

- Data Integrity page now always renders a useful page instead of going blank.
- Printable Needs Review report.
- Populated Franchise Master Excel export from the live database.
- Franchise Master import uses **Franchise Code first** as the primary match key.
- Automatic MF### franchise code allocation for records without a code.
- Defensive schema reconciliation for franchise master fields.
- Alias routes for `/admin/franchise-master`.
- Import Centre remains simplified to only two imports:
  1. Franchise Master
  2. Month-End Figures PDF

## Deploy commands

```bash
flask db upgrade
flask seed-franchise-codes
flask assign-franchise-regions
flask stabilize-platform --all-periods
flask db current
```

Expected final DB version:

```text
v106_core_business_repair (head)
```

## Finance workflow

1. Go to **Admin -> Data Integrity**.
2. Click **Download Franchise Master Excel**.
3. Complete Province, Region, Agreement Date and Royalty Scale rows.
4. Import the completed file back into **Admin -> Data Integrity**.
5. Run stabilization or allow the import pipeline to refresh reports automatically.

