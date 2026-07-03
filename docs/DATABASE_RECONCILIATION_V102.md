# v102 Database Reconciliation & Schema Repair

This release repairs the schema mismatch caused by the v100 platform and region branches.

## Included
- Merges `v100_platform_stabilization` and `v100_region_ui_stabilization` into one Alembic head.
- Ensures `franchises.province` exists.
- Backfills South African provinces from franchise names.
- Ensures the default SA GDP growth profile exists.
- Normalizes null monthly numeric values used by dashboards and calculations.
- Leaves historical calculation formulas unchanged.

## Deploy commands

```bash
flask db heads
flask db upgrade
flask db current
flask assign-franchise-regions
flask stabilize-platform --all-periods
```

Expected final version:

```text
v102_schema_reconciliation (head)
```
