# Enterprise Analytics UI and Insights Fix V120

## Changes

- Fixed `/performance/insights` HTTP 500 error caused by treating the dictionary `items` method as a list.
- The route now passes `insight_items`, `insight_counts`, and `insight_franchise` explicitly to Jinja.
- Rebuilt Performance Insights with a professional filter toolbar, KPI summary cards, decision cards, severity indicators, recommended actions, and drill-down links.
- Rebuilt Performance Graph filters into a compact responsive toolbar with aligned fields, Apply and Reset actions.
- Rebuilt Leaderboard filters and summary cards with clearer movement status presentation.
- Added a shared V120 analytics styling layer for consistent buttons, selects, input focus states, cards, spacing, and mobile layouts.
- Preserved all performance, target, leaderboard, royalty, franchise activation, and calculation logic.

## Database

No migration is required. V119 remains the database head.

## Deployment

Deploy the updated application and restart the Render web service. A browser hard refresh may be required to load the new CSS.
