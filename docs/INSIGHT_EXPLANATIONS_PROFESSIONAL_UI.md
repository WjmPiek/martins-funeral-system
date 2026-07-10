# Insight Explanations Professional UI

## Changes

- Rebuilt the Insight Explanations page as a compact, professional dashboard.
- Added four working page tabs:
  - Executive Summary
  - Franchise Explanations
  - Royalty Explanations
  - Province Summaries
- Each tab now uses a `tab` query parameter and displays only its own dataset.
- Updated Franchise Management sidebar links to open the correct tab directly.
- Prevented royalty and unrelated BI narratives from being duplicated under Franchise Explanations.
- Added compact KPI cards, expandable franchise rows, a royalty trace table, province summary cards, empty-state guidance and responsive mobile styling.
- Preserved the royalty engine and all underlying calculations.

## Deployment

No database migration is required. Deploy the updated code and restart the Render web service.
