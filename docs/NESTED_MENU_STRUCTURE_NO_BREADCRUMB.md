# Nested menu structure no breadcrumb

This patch updates the sidebar into grouped expandable main tabs without adding breadcrumbs.

## Franchise-side menu

Dashboard is hidden for franchise-only users.

Franchise Details has a red badge of 2 and these sub tabs:
- Franchise Details
- Employees

Monthly Figures has a red badge of 4 and these sub tabs:
- Performance
- Monthly Figures
- Royalties
- Finance

Heat Map and Manuals remain normal direct links.

## Admin menu

Users has a red badge of 4 and these sub tabs:
- Users
- Employees
- User Roles
- Old Franchises

Franchise Employee Users is renamed to Employees.

## Notes

- No database migration is required.
- Main tabs expand/collapse directly in the sidebar.
- Sub tabs load the normal page content area.
