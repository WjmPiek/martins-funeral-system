# User Menu and Individual Actions Fix

This patch changes user management and navigation as requested.

## Changes

- Removed global cleanup buttons from the Users by Franchise page.
- Added per-user actions inside each Manage User modal:
  - Clean this user scope
  - Clear this user's franchise links
  - Deactivate this user
- Franchise Details remains the main menu item.
- Employees is now a sub item under Franchise Details.
- Monthly Figures remains the main menu item.
- Royalties and Finance are sub items under Monthly Figures.
- Dashboard is hidden for franchise-only users.
- Admin Users is the main admin user page.
- Employees and User Roles are sub items under Users.
- Franchise Employee Users was renamed to Employees.

## Migration

No database migration is required.
