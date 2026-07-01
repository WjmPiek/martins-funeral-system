# Import Centre validation workflow

This build adds a controlled Import Centre for month-end Excel imports.

## What happens after Deon/Finance uploads a month-end workbook

1. The system imports the raw monthly figures.
2. The pipeline validates that branches matched franchise records.
3. The pipeline checks agreement start dates and royalty scales.
4. The pipeline recalculates royalties from the current agreement formula and scale.
5. The pipeline reconciles saved rows vs recalculated rows.
6. Only clean imports publish performance cache/graphs/leaderboard summaries.
7. Imports with missing scales, missing agreements, missing franchise-user links, or 0% royalty exceptions are marked Needs Review.

## Where to check it

Admin menu:

- Imports & Data -> Import Centre
- Admin -> Import Centre

Each import report shows:

- uploaded file
- uploaded by
- status
- matched franchises
- saved rows
- recalculated rows
- royalties calculated
- performance rows published
- review items/errors

## Status meaning

- Completed: import reconciled and was published to graph/leaderboard/performance summaries.
- Needs Review: figures were imported, but graph/leaderboard publish was held back because something needs correction.
- Failed: import crashed or could not be read.
