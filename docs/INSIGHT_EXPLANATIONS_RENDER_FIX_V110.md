# Insight Explanations Render and Data Fix

## Changes

- Corrected three malformed Jinja `url_for()` links in `base.html` that caused all pages extending the base template to return HTTP 500.
- Added automatic one-time rebuilding of stale insight narrative sets when source health or royalty data exists but a sub-tab has no narratives.
- Increased the narrative query ceiling to 240 records before separating records into their correct tabs.
- Added a Refresh action to Franchise Explanations, Royalty Explanations, and Province Summaries.
- Preserved the selected tab after rebuilding explanations.
- Kept each explanation category isolated to prevent duplicate information under different headings.

## Database migration

No migration is required.

## Validation

- Python source compilation passed.
- All Jinja templates parsed successfully.
