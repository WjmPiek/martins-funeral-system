# Platform Stabilization v100

This release hardens the enterprise dashboard and royalty rebuild pipeline after Phases 10-13.

## Fixed

- `decimal_value()` now safely handles `None`, blank and invalid numeric values.
- Royalty recalculation no longer stops the entire rebuild when one franchise/month has bad data.
- Bad rows are marked `Needs Review` and receive a note with the rebuild error.
- Recalculation result now reports `errors` and `error_details`.
- `rebuild-performance-cache` now supports optional `--month` and `--year` arguments while still allowing a full rebuild.

## Recommended post-deploy commands

```bash
flask db current
flask db upgrade
flask db current
flask seed-workflow-defaults
flask seed-royalty-growth-profile
flask rebuild-business-intelligence --month 5 --year 2026
flask rebuild-insights --month 5 --year 2026
flask recalculate-royalties --month 5 --year 2026
flask rebuild-performance-cache --month 5 --year 2026
```

If `recalculate-royalties` reports errors, open Royalty Management or Database Diagnostics to review the rows marked `Needs Review`.
