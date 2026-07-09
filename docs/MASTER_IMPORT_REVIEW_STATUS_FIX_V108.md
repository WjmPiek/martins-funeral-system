# v108 Master Import Review Status Fix

This patch makes the Master Import workbook the controlling source for franchise allocation and master-data readiness.

## Fixes

- Accepts `Import ID`, `Unique ID`, `Unique Import ID`, and `Master Import ID` as the same source-of-truth ID.
- Accepts `Standardized Town Name` and `Standardized Town` as the same field.
- Stores standardized town, province code, district code and municipality code from the Master Import sheet.
- Refreshes matching lookups after each row is created/updated so duplicate or linked rows map to the same franchise record correctly.
- Data Integrity no longer marks a franchise as `Needs Review` because of an old/stale royalty snapshot that was created before the latest Master Import upload.
- Master readiness now reflects current master data: franchise code, province/region, agreement date and structured royalty scale rows.

## Important

After deployment:

```bash
flask db upgrade
```

Then re-upload the latest Master Import workbook. This will update the franchise records and royalty scales. Old royalty review badges from prior imports should no longer incorrectly mark complete master records such as Pretoria North or Westonaria as missing master data.
