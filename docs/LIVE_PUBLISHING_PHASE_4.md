# Phase 4 - Live Publishing and Refresh

This phase turns successful imports into a live publishing event.

## What changed

- Added a trusted-financials publishing event after clean reconciliation.
- Admin, Finance Manager, and Finance Assistant receive a company-wide notification.
- Franchise users receive only notifications for their own linked franchise.
- Dashboard, royalties, monthly figures, leaderboard, and performance graph pages can refresh automatically when trusted data is published.
- Import Centre and upload pages do not auto-refresh while a user may be working in a form.
- Added database indexes for faster live refresh polling.

## Flow

1. Finance/Admin imports month-end figures.
2. Imported rows are made visible to the correct roles.
3. Royalties are recalculated.
4. Reconciliation must pass.
5. Performance summaries are rebuilt.
6. A trusted publishing event is created.
7. Connected users are notified and relevant pages refresh.

## Alembic

New revision:

- `v89_live_refresh`

Run:

```bash
flask db upgrade
```
