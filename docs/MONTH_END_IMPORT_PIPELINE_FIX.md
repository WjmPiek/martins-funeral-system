# Month-End Import Pipeline Fix

This update changes the monthly Excel import from a simple file upload into a proper month-end processing pipeline.

## What changed

1. Finance users with `monthly_figures:import` can run the import.
2. Imported branch rows are matched to franchise records as before.
3. After the raw figures are saved, the pipeline automatically:
   - validates franchise-user links,
   - checks agreement start dates,
   - checks royalty scale availability,
   - recalculates all imported royalty rows,
   - rebuilds performance/leaderboard cache rows,
   - shows warnings for rows that need review.
4. Royalty gross method now uses the agreement start date as the source of truth:
   - agreement year 2018 or later = New Gross Method,
   - agreement before 2018 = Old Gross Method,
   - missing agreement date = stored method fallback.

## Why this fixes the issue

The old calculation could keep using the default stored value `old` even when the agreement date should have selected the New Gross Method. This meant the imported figures were visible but payover/royalties could calculate from the wrong formula.

## Correct database field names

The Render database does not use `franchises.name` or `agreement_date`.
Use:

```sql
SELECT id, business_name, agreement_start_date, agreement_end_date
FROM franchises
LIMIT 10;
```

## Useful Render shell checks

```python
from app import db
from sqlalchemy import text

result = db.session.execute(text("""
SELECT id, business_name, agreement_start_date, agreement_end_date, royalty_gross_method
FROM franchises
ORDER BY business_name
LIMIT 20
"""))
for row in result:
    print(row)
```

```python
result = db.session.execute(text("""
SELECT f.business_name, mf.year, mf.month, mf.gross_revenue, mf.royalty_percentage, mf.royalty_amount
FROM monthly_figures mf
JOIN franchises f ON f.id = mf.franchise_id
WHERE mf.year = 2026 AND mf.month = 5
ORDER BY f.business_name
LIMIT 20
"""))
for row in result:
    print(row)
```
