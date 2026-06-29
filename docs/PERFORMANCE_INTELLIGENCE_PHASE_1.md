# Performance Intelligence Phase 1

This phase creates the foundation for fair franchise performance targets using the existing monthly import data.

## What it adds

- Growth target brackets for each KPI:
  - Cash
  - Sales
  - Insurance Premiums
  - Joinings
  - Funerals
- A Performance Results snapshot table.
- A Growth Brackets management screen.
- A Recalculate action on the Performance page.
- A fair target mode called **Fair Growth Bracket**.

## Why this matters

A large franchise and a small franchise should not always receive the same growth percentage. Phase 1 uses brackets so that targets are more realistic.

Example default money brackets:

- R0 to R150k = 15%
- R150k to R300k = 12%
- R300k to R500k = 10%
- R500k to R750k = 8%
- R750k to R1.2m = 6%
- R1.2m+ = 5%

## Deploy

After pushing this patch, run:

```bash
flask db upgrade
```

Expected head:

```text
v68_performance_intelligence_phase1
```
