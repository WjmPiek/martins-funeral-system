# Performance Stabilization V122

## Fixes

- Fixed `flask warm-analytics-cache` outside an HTTP request. CLI jobs no longer require a logged-in Flask user or session.
- Added safe request-context guards around franchise selection helpers.
- Added a production Gunicorn configuration using two threaded workers.
- Added `start_web.sh` for the Render Start Command.
- Removed compiled Python cache files from the deployment package.

## Render Start Command

Set the Render web service Start Command to:

```bash
./start_web.sh
```

Do not run Gunicorn manually inside Render Shell while the web service is already running. Port 10000 is already occupied by the live service.

## Cache warm command

```bash
flask warm-analytics-cache --month 6 --year 2026
```

## Important

Old source files and documentation do not normally slow requests unless imported or executed. Cleanup should remove dead registered routes, duplicate context processors and repeated queries only after usage is verified. Blindly deleting historical modules can break imports, migrations and live endpoints.
