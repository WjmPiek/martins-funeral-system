# V119 Existing Franchise Data Restore

V118 bulk-disabled all franchise records and franchise-side accounts and deleted generated caches/snapshots. V119 restores only records carrying the V118 deactivation reasons, removes automatic three-month deactivation from the user listing flow, and keeps Potential Franchises as an explicit Head Office workflow.

Raw monthly figures, franchise master data, agreements, and royalty scales were never deleted. Generated performance, royalty, BI, and insight rows must be rebuilt after migration.

## Deploy

```bash
flask db upgrade
flask stabilize-platform --all-periods
```

If the complete rebuild is too heavy for the Render shell, run the latest period first using the individual rebuild commands.
