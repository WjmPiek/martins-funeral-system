# Import Visibility and Reporting Period Fix

This update fixes a month-end import visibility problem where Finance/Admin imports were saved but were difficult to find or appeared under the wrong period.

## Changes

- PDF imports now require an explicit Reporting Month and Reporting Year.
- The selected month/year is the source of truth and is not overridden by PDF text or upload date.
- PDF imports upsert the existing monthly figure for the same franchise/month/year instead of creating hidden duplicates.
- After PDF import, royalties are recalculated and the import pipeline runs for that franchise and period.
- After import, the user is redirected to Monthly Figures for the imported period.
- Monthly Figures and Royalties default to the latest imported period instead of the current calendar month.
- Admin, Finance Manager and Finance Assistant users see all imported branches for the selected period.
- Franchise users continue to see only their own branch data.

## Why this was needed

Month-end reports are usually uploaded after the reporting month has ended. Previously, pages defaulted to the current calendar month, and PDF month/year detection could read the wrong date from the document. This made correctly imported figures appear missing.
