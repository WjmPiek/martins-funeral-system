# Gross Old Royalty Fix

This patch fixes Gross Old royalty calculation by:

1. Normalizing old stored method labels such as `Gross = Old`, `Gross Old`, `old-gross`, `Gross = New Gross Method`, and `new` into canonical database values: `old` or `new`.
2. Ensuring Gross Old uses:

   `Sales + Insurance Receipts`

3. Ensuring New Gross uses:

   `Sales + Admin Fee`

4. Recalculating existing monthly figures in migration `v67_gross_old_royalty_fix`.
5. Keeping the displayed Gross Method consistent with the calculated method on Monthly Figures and Royalties screens.
6. Handling open-ended royalty scale brackets where `amount_to` is blank or zero.

After deploying, run:

```bash
flask db current
flask db upgrade
flask db current
```

Expected final head:

```text
v67_gross_old_royalty_fix (head)
```
