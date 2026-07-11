# Graphs & Analytics Performance V123

V123 reduces the amount of work and HTML produced by the Graphs & Analytics module.

## Changes

- Monthly Targets uses server-side pagination and franchise search.
- Target calculations are limited to the franchises visible on the current page.
- Saving targets updates only the current page and bulk-loads existing target records.
- Annual Budget uses server-side pagination and franchise search.
- Annual budget calculations are limited to the selected page instead of every franchise.
- Initial HTML size is reduced from multi-megabyte responses to a small paginated response.
- Existing formulas, target brackets, annual budget formulas and generated target actions are unchanged.
- Existing V121/V122 graph caches and read-only request behaviour remain active for all Graphs & Analytics routes.

## Expected impact

- `/performance/targets`: substantially smaller response and faster calculation.
- `/performance/annual-budget`: no longer calculates and renders every franchise in one request.
- Browser rendering and scrolling are faster because only a controlled number of rows/cards are present.

No database migration is required.
