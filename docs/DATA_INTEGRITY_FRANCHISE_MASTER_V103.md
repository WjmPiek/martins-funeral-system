# v103 Data Integrity & Franchise Master Integration

This release adds a printable data-integrity report and a Franchise Master workbook workflow.

## New Admin page

Admin > Data Integrity

The page shows:
- Total franchises
- Ready vs Needs Review
- Missing province/region
- Missing agreement date
- Missing royalty scale
- Printable fix report
- Download Franchise Master Excel
- Import corrected Franchise Master Excel

## Franchise Master Excel

The workbook is generated from the live database and includes all existing franchise users/franchises. It matches imported rows by:

1. Franchise ID
2. Franchise Code
3. Business Name

Editable fields include:
- Business name
- Address
- Contact numbers
- Franchisee details
- Province
- Region
- District
- Municipality
- Agreement dates
- Royalty method
- Minimum royalty amount
- Royalty scale rows and percentages

## After deploy

Run:

```bash
flask db upgrade
flask assign-franchise-regions
flask stabilize-platform --all-periods
```

Expected head:

```text
v103_data_integrity_master (head)
```
