# Performance Intelligence Phase 2

Phase 2 upgrades the fair target system into a transparent growth-bracket engine.

## Added

- Shortened the Phase 1 Alembic revision ID to `v68_perf_intel_p1` so PostgreSQL's `alembic_version.version_num` length limit is not exceeded.
- New migration `v69_perf_intel_p2`.
- Bracket target details per franchise and KPI:
  - bracket range used
  - baseline value used
  - basis KPI
  - growth percentage
  - generated target value
- Manual target screen now shows how each automatic target was calculated.
- New **Generate Fair Bracket Targets** action to save bracket-generated targets as Head Office targets.

## Business rule

Targets are no longer one-size-fits-all. Each KPI target is calculated from the franchise's own historical baseline and the matching growth bracket.

Example:

- R200,000 cash baseline can receive a higher growth percentage.
- R1,000,000 cash baseline receives a lower, more realistic growth percentage.

This keeps targets fair across small and large franchises.
