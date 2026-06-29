# Mother Company / Franchise User Hierarchy Fix

## Purpose
This patch fixes the user-creation flow so Martins Funerals South Africa creates its own users separately from franchise-created users.

## Martins Funerals South Africa Admin Users
Created under **Admin > Users > Users**:
- Finance Manager
- Finance Assistant
- Regional Manager
- Franchise User

Rules:
- Finance Manager and Finance Assistant are mother-company users and are not linked to one franchise.
- Regional Manager must be linked to selected franchise(s).
- Franchise User must be linked to selected franchise(s).
- No Admin-created user is automatically placed under one franchise user.

## Franchise Users
Created by a Franchise User under **Franchise Details > Employees**:
- Manager
- Employee
- Agent

Rules:
- These users are children of the logged-in franchise user.
- They only receive the selected franchise scope that belongs to that franchise user.
- They never see the Admin system.

## Migration repair
The previous `v76_user_creation_scope` migration pointed to a missing `v75_user_scope_ui` migration. This patch changes the down revision to `v74_franchise_employees` and creates the required hierarchy roles if missing.

After pushing, run:

```bash
flask db current
flask db upgrade
flask db current
```

Expected head:

```text
v76_user_creation_scope
```
