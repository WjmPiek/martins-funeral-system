# Performance Engine: Phase 1 to 10

This build turns imported monthly figures into live targets, comparisons, graphs, franchise dashboard cards and leaderboard rankings.

## KPI Fields

The engine uses the existing `monthly_figures` table:

| KPI | Source column |
| --- | --- |
| Cash | `cash` |
| Sales | `sales` |
| Insurance Premiums | `insurance_receipts` |
| Joinings | `insurance_joinings` |
| Funerals | `number_of_funerals` |

Manual targets are stored in the existing `franchise_targets` table. If no manual target exists, the engine can calculate automatic targets from historical data.

## Phase 1 - Dynamic Monthly Targets
Adds target calculations for Cash, Sales, Insurance Premiums, Joinings and Funerals.

## Phase 2 - Previous Month and Previous Year Comparisons
Adds comparisons against previous month, same month last year and 3-year same-month average.

## Phase 3 - Smart Target Modes
Adds manual, previous year, previous year + growth, 3-year average and 3-year average + growth target modes.

## Phase 4 - Franchise Graphs
Adds a 12-month Actual vs Target graph for each KPI.

## Phase 5 - Franchise Dashboard Card
Adds the performance card to the franchise dashboard showing rank, movement and KPI target percentages.

## Phase 6 - KPI Leaderboards
Adds leaderboards per KPI and overall score.

## Phase 7 - Weighted Performance Score
Adds one weighted score:

- Cash: 30%
- Sales: 25%
- Insurance Premiums: 20%
- Joinings: 15%
- Funerals: 10%

Each KPI is capped at 150% achievement for scoring, so one very strong KPI cannot hide weak KPIs.

## Phase 8 - Target Management Screen
Adds `/performance/targets` for Head Office to capture monthly targets. Manual targets override automatic targets.

## Phase 9 - Executive Performance Dashboard Foundation
Adds `/performance` as the central performance leaderboard with filters for month, year, KPI and target mode.

## Phase 10 - Branch Health Foundation
The weighted score and KPI percentages create the foundation for a future Health Score that can also include Attendance, Claims and Manual compliance.

## Deployment

1. Deploy to the Render test service first.
2. Run `flask db upgrade`.
3. Give the right roles the new permissions:
   - `performance:view`
   - `performance:manage_targets`
4. Import or enter monthly figures as normal.
5. Open `/performance`.

## Notes

This build calculates target percentages dynamically from PostgreSQL. Do not import spreadsheet formulas. Import only the real monthly values. The system calculates target, difference, cumulative-style comparisons and leaderboard positions live.
