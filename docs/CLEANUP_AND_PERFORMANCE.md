# Cleanup and Performance Update

This cleanup removes development artefacts and speeds up analytics pages.

## Removed from the clean package

- `.git/` history folder from the ZIP package
- `.env` secrets file
- `instance/` local database folder
- Python cache folders and compiled files
- local backup file `martins_funeral_system.backup`
- old one-off patch scripts
- old phase-by-phase patch notes

## Kept

- application source code
- templates and static assets
- migrations
- manuals seed files
- active deployment files

## Performance improvements

- Added request-level caching in `app/performance/service.py` so repeated KPI, target, graph and leaderboard calculations share the same SQL results within a page load.
- Added migration `v79_perf_cleanup` with database indexes for analytics and role/franchise lookups.
- Kept calculations live and accurate after every request/import; cache is not shared between requests.

## Deploy steps

```bash
flask db upgrade
```

Expected head after this update:

```text
v79_perf_cleanup
```
