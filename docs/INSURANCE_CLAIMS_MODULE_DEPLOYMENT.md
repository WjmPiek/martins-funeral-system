# Built-in Insurance Claims module

This package integrates the franchise_claims_system directly into Martins Funeral System under the Insurance Claims sidebar tab.

## Database update
Preferred after deployment:

```bash
flask db upgrade
```

The migration is:

```text
migrations/versions/v63_insurance_claims_module.py
```

Manual SQL is included at:

```text
database_updates/insurance_claims_full_update.sql
```

## Render persistent storage
Set this if you want claim attachments stored on Render persistent disk:

```env
INSURANCE_CLAIMS_STORAGE_ROOT=/var/data/insurance_claims
```

The import logic keeps PolicyData and claims files separate. PolicyData imports use MEM rows for monthly risk/policy totals when a Relation column exists.
