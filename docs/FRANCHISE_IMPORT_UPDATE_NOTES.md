# Martins Direct Franchise Import Update

This build simplifies Imports & Data to two upload actions only:

1. Franchise Master Import
   - Upload: Martins Funerals Franchise Master.xlsx
   - Imports franchises, franchise users, grouped franchises, contacts, contracts, royalty settings and royalty brackets.
   - Recalculates existing monthly royalty values after master import.

2. Monthly Figures Import
   - Upload: Syfers - Alle Takke GROEP.xlsx
   - Imports monthly figures only.
   - Does not create franchises, users, contacts, contracts or groups.
   - Unmatched franchise names are skipped and listed for review.

## Deployment steps

1. Replace the application files on the Render development branch with this package.
2. Deploy to Render development.
3. Open the Render Shell.
4. Run `flask db upgrade`.
5. Upload the Franchise Master workbook first.
6. Upload the Syfers monthly figures workbook second.
7. Check counts for franchises, user_franchises, royalty_scales and monthly_figures.

## Important

Do not import monthly figures before the Franchise Master import has completed successfully.
