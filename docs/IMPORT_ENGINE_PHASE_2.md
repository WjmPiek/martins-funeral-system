# Import Engine Phase 2 Stabilization

This update starts Version 2 stabilization of the Month-End import process.

## What changed

- PDF imports now require an explicit Reporting Month and Reporting Year.
- The PDF file name, PDF text, upload date and current calendar date no longer override the selected period.
- Imported monthly rows are always marked visible/published after save so Admin and Finance can see them immediately.
- Franchise users only see rows linked to their own franchise permissions.
- Missing agreement dates or royalty scales block trusted financial publishing, but do not hide the imported figures.
- Import Centre now separates:
  - Figures visible
  - Trusted financials
- Import jobs now record the uploading user.
- Needs Review jobs now finish correctly and remain visible in Import Centre.

## Business rule

The system can publish the imported figures while still marking royalties/performance as Needs Review when agreement or scale data is incomplete. This ensures Finance can see what Deon imported, but the system does not claim royalty calculations are trusted until validation passes.
