# Regional Manager and Franchise User access scope

This patch restricts Regional Manager, Franchise Manager and Franchise User roles to the tabs requested for now.

## Regional Manager

Data scope:
- Sees only franchises linked to the Regional Manager user account.
- Does not get Franchise Management view/manage permissions, because those permissions expose all franchises.

Visible tabs:
- Dashboard
- Franchise Details
- Performance
- Royalty
- Monthly Figures
- Heatmap
- Manuals

Franchise Agreement and Royalty Scale:
- View only.
- Fields are locked unless the user is Admin or Finance Manager.

## Franchise Manager / Franchise User

Data scope:
- Sees only assigned franchise data.

Visible tabs:
- Dashboard
- Franchise Details
- Performance
- Royalty
- Monthly Figures
- Heatmap
- Manuals

Franchise Agreement and Royalty Scale:
- View only.
- Fields are locked unless the user is Admin or Finance Manager.

## Migration

Run:

```bash
flask db upgrade
```

Expected head:

```text
v73_role_scope
```

The migration resets only these roles:
- Regional Manager
- Franchise Manager
- Franchise User

Admin and Finance Manager permissions are not reset by this migration.
