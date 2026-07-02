# Phase 11 - Enterprise Business Intelligence

This build adds the Martins Funeral System Enterprise Business Intelligence layer.

## What it does

- Adds franchise health scoring for each reporting period.
- Adds Business Intelligence dashboard under Admin.
- Adds province intelligence and target-achievement warnings.
- Adds generated executive insights such as fastest growth and largest decline.
- Adds CLI rebuild command: `flask rebuild-business-intelligence`.
- Adds migration `v97_business_intelligence`.

## Important

This phase is analytical only. It does not change royalty calculations, royalty scales, agreement rules, monthly figures, or payover values.

## New database tables

- `franchise_health_snapshots`
- `business_insights`

## Deployment

After deploying the ZIP, run:

```bash
flask db current
flask db upgrade
flask db current
flask rebuild-business-intelligence
```

Expected head:

```text
v97_business_intelligence (head)
```
