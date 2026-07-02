# Royalty Engine Phase 3

This phase centralizes royalty calculations in `app/royalty_engine.py` so Excel imports, PDF imports, royalty pages and diagnostics use the same business rules.

## Included

- Agreement date is the source of truth for old/new gross method.
- 2018 or newer agreement start date = New Gross Method.
- Before 2018 = Old Gross Method.
- Missing agreement date blocks trusted financial publishing and marks the import as Needs Review.
- Expired/future agreement periods create review warnings.
- Royalty scale validation checks structured scales, imported scale text, matching branch scale fallback and imported percentage fallback.
- Royalty Engine reviews are stored in the import report and shown in Import Centre detail.
- Existing route functions now delegate to the central engine for consistent calculations.

## Important behavior

Imported figures can still become visible to Admin/Finance and the matching Franchise User, but graphs/leaderboard/trusted financial publishing stay blocked when a franchise has missing agreement dates, missing scale data or 0% royalty with a positive royalty base.
