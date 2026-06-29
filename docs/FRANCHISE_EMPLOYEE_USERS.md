# Franchise Employee Users

This patch lets franchise users and franchise managers create employee users under their own linked franchise.

## What it adds

- New role: `Franchise Employee`
- New permission module: `Franchise Employees`
- Franchise users/managers can create employee users under their own linked franchise only.
- Franchise users/managers can edit, activate/deactivate and soft-delete their own employee users.
- Admin can view, edit and deactivate all employee users created under any franchise user.
- Employee users are linked to the same franchise data scope and cannot see unrelated franchise data.
- Admin sidebar includes `Franchise Employee Users`.
- Franchise sidebar includes `Employee Users`.

## Important behavior

Delete/deactivate is a soft delete. The user is marked inactive so audit history and related data remain intact.

## Migration

Run after deployment:

```bash
flask db upgrade
```

Expected head:

```text
v74_franchise_employees
```
