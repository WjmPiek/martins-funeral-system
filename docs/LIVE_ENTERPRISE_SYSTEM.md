# Live Enterprise System Layer

This build adds the live-operational layer for Martins Funeral System.

## What changed

- Adds `live_events` and `live_notifications` tables.
- Adds `/live/status` API for lightweight browser polling.
- Adds live notification panel in the application shell.
- Month-end imports now publish a live event after validation, royalty recalculation and performance cache rebuild.
- Admin, Finance Manager, Finance Assistant and Regional Manager users receive company-level import notifications.
- Franchise users receive notifications only for franchises linked to their own account.
- Imported monthly rows are marked `Published` so they are visible immediately after successful import processing.
- Existing imported/calculated/approved/submitted rows are migrated to `Published`.

## Visibility rules

- Admin/Finance users see all imported data they have permission to view.
- Franchise users only see their assigned franchise data.
- Live notifications follow the same visibility rules.

## Migration

Run:

```bash
flask db upgrade
```

New revision:

```text
v88_live_system
```

## Runtime behavior

When a month-end import completes:

1. The import pipeline validates the period/franchise rows.
2. Monthly figures are marked Published.
3. Royalties are recalculated.
4. Performance and leaderboard cache is rebuilt.
5. A live event is created.
6. Admin/Finance users receive system update notifications.
7. Linked franchise users receive branch-specific notifications.
8. Open browsers poll `/live/status` and show the update without requiring a manual refresh.
