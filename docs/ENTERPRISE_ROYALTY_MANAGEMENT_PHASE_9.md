# Phase 9 — Enterprise Royalty Management

This phase turns the royalty calculation into a traceable management subsystem without changing the existing royalty formula by default.

## What was added

- Versioned royalty agreement profiles
- Admin-managed SA GDP growth profile
- Royalty calculation snapshots per monthly figure
- Diagnostics for missing agreement dates, missing scales and blocked calculations
- Admin Royalty Management page
- Recalculate Royalties action for a selected month/year
- CLI commands:
  - `flask seed-royalty-growth-profile`
  - `flask recalculate-royalties --month 6 --year 2026`
- Migration: `v95_royalty_mgmt`

## Important business rule

The current royalty scale calculation is preserved. Phase 9 wraps it with audit data, formula versioning, diagnostics and repeatable snapshots.

## Deployment

After deploying, run:

```bash
flask db current
flask db upgrade
flask db current
flask seed-royalty-growth-profile
```

Expected head:

```text
v95_royalty_mgmt (head)
```
