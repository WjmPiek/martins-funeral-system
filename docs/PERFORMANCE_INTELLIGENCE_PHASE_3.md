# Performance Intelligence Phase 3 - Annual Budget Builder

Phase 3 adds an annual budget builder on top of Phase 1 and Phase 2.

## What it does

- Builds a full 12-month target budget for every franchise.
- Supports Cash, Sales, Insurance Premiums, Joinings and Funerals.
- Uses the previous 3 years to calculate seasonal monthly weighting.
- Applies the correct fair growth bracket per franchise and KPI.
- Saves the generated values into the existing `franchise_targets` table.

## Why this matters

A franchise does not perform evenly every month. Phase 3 avoids a simple `annual target / 12` split and instead uses historical monthly patterns to create realistic targets.

Example:

- If March is usually stronger, March receives a larger target share.
- If February is usually weaker, February receives a smaller target share.
- The annual growth expectation still comes from the fair bracket system.

## New screen

`/performance/annual-budget`

Admin can preview the annual budget first, then click **Generate Annual Budget Targets**.

## Migration

`v70_perf_intel_p3`

This migration is intentionally light because the feature uses the existing target table.
