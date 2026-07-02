# Migration Chain Repair - v88

Fixed Alembic migration chain error on Render.

## Problem

`v88_live_enterprise_system.py` referenced `down_revision = "v87_import_progress_ui_currency"`, but the actual revision ID inside `v87_import_progress_ui_currency.py` is `v87_import_ui`. Alembic uses the internal `revision` variable, not the filename.

## Fix

Changed `v88_live_enterprise_system.py` to:

```python
down_revision = "v87_import_ui"
```

## After deploy

Run on Render:

```bash
flask db current
flask db upgrade
flask db current
```

Expected result: current migration should advance to `v88_live_system`.
