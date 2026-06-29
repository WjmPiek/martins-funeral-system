# Admin Users 403 Role Detection Fix

This patch fixes the `/admin/users` Forbidden error after deployment.

## Problem

The screen could show a user as Admin while `current_user.has_role("Admin")` returned false in the route guard. This caused `/admin/users` and related Admin pages to return 403 even for the protected Martins admin account.

## Fix

- Strengthened Admin role detection in `app/admin/routes.py`.
- Treats `wjm@martinsdirect.com` / `Wjm Piek` as Admin even if legacy role links are inconsistent.
- Reads legacy/display role fields in addition to the many-to-many `roles` relationship.
- Admin/Super Admin bypasses permission-row checks for Admin pages.

## Migration

No migration required.
