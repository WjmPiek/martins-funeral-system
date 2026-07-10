# Manual Franchise Master Edit v109

## Added
- Every franchise row on Admin > Data Integrity is editable from an Edit button.
- Ready franchise names are clickable and also have an Edit button.
- Manual edits write directly to PostgreSQL.
- Franchise allocation, contact details, agreement dates, minimum royalty and up to 10 royalty scale rows can be edited.
- The linked franchise login user can be updated or created and is marked as the primary franchise user.
- Download Franchise Master Excel exports the latest live database values after manual edits.
- Export now includes Master Import ID, Standardized Town, Province Code, District Code and Municipality Code.
- Data Integrity tables use fixed layout, compact widths and wrapped text so all columns remain inside the card.

## Deployment
No database migration is required for this patch because it uses the v107/v108 database fields.

Deploy the code and restart the Render web service. Run `flask db upgrade` only if v107/v108 was not deployed previously.
