# v105 - Two Import Workflow and Franchise Code Matching

This release simplifies the import workflow to two user-facing imports only:

1. Franchise Master Excel
2. Month-End Figures PDF

All other imports/rebuilds are hidden from Finance/Admin import screens and treated as internal system processing.

## Franchise Code rule

Franchise Code is now the primary identifier for imported data.

- Franchise Master exports every franchise with its permanent code.
- Month-end/legacy imports try Franchise Code first.
- Business name matching remains only as a fallback for old files.
- Unknown franchises are no longer auto-created from monthly imports; they must be corrected in Franchise Master first.

## Automatic downstream processing

After month-end figures are imported, the existing pipeline continues to refresh:

- royalty snapshots
- performance cache
- BI
- insights
- live publishing
- event notifications

## User-facing import screens

The Import Centre now shows only the controlled workflow and utility actions. Legacy routes remain in code for backwards compatibility, but they are not promoted as normal user actions.
