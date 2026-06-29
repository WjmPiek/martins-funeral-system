# Franchise Details Selector and Royalty Setup Alerts

This patch improves the Franchise Details screen.

## Added

- Search bar and franchise drop-down at the top of Franchise Details.
- Selecting a franchise loads that franchise immediately.
- Direct correction links for franchises with incomplete royalty setup.
- Alerts for missing:
  - agreement start date
  - agreement end date
  - minimum royalty amount
  - royalty scale brackets
- Franchise users only see alerts for franchises assigned to them.
- Admin / franchise-management users see all accessible franchise alerts.
- The save form keeps the selected `franchise_id`, so the correct franchise is updated.

## Files changed

- `app/franchise/routes.py`
- `app/templates/franchise/details.html`

## Migration

No database migration required.
