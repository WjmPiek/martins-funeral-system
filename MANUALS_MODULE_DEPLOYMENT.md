# MFF Manuals built into Martins Funeral System

This package includes the MFF Manual app directly inside the Martins Funeral System as a native `Manuals` sidebar tab.

## Database update
Preferred on Render after deployment:

```bash
flask db upgrade
```

Manual SQL alternative:

```text
database_updates/mff_manuals_full_update.sql
```

## Storage
Uploaded manual PDFs are stored in `MANUALS_STORAGE_ROOT` if configured. On Render, set it to a persistent disk path, for example:

```env
MANUALS_STORAGE_ROOT=/var/data/mff_manuals
```

Seed PDFs from the uploaded MFF Manual app are bundled in `app/manuals_seed/` and auto-imported into the database on first Manuals page load after the migration has run.
