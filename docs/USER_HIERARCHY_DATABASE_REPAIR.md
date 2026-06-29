# User Hierarchy Database Repair

This patch adds migration `v77_user_hierarchy_fix`.

It repairs the database side of the Martins Funerals South Africa user hierarchy:

- Ensures mother-company roles exist: Admin, Finance Manager, Finance Assistant, Regional Manager.
- Ensures franchise-side roles exist: Franchise User, Franchise Manager, Franchise Employee, Franchise Agent.
- Ensures core permission rows exist using the current `permissions` schema.
- Assigns all existing permissions to the Admin role.
- Ensures the protected Martins admin user is active and has the Admin role.
- Removes franchise links from Admin, Finance Manager and Finance Assistant accounts.
- Clears parent-franchise-user links from mother-company and franchise-owner accounts.
- Keeps franchise employee accounts under their franchise owner.

After pushing, run:

```bash
flask db current
flask db upgrade
flask db current
```

Expected head:

```text
v77_user_hierarchy_fix
```

This migration does not remove existing franchise assignments for Regional Manager or Franchise User accounts.
