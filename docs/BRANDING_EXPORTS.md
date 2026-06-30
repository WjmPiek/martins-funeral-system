# Branding and export standard

This version centralises the Martins logo in `app/static/img/logo.png` and uses it on the login page, authenticated header, PDF reports and future Excel exports.

Use `app.branding.apply_workbook_branding(workbook, title, subtitle)` in any new Excel export before saving the workbook. The helper inserts the logo without stretching it and keeps the report printable on desktop and mobile-generated downloads.
