# V125 Compact UI and Automatic Inline Import

- Reduced global font sizes, spacing and table-cell padding so data fits inside cards and columns.
- Long text wraps instead of being cut off.
- Tables use compact fixed layouts with scroll fallback only when unavoidable.
- PDF and Excel import jobs are processed immediately by the web service when no background worker exists.
- PDF franchise allocation now attempts permanent franchise code, master import ID, standardized town and business name matching from the PDF text before falling back to a manually selected franchise.
- The existing import pipeline still validates, recalculates royalties, rebuilds performance results and publishes the selected period.
- Existing queued jobs can be processed with `flask run-next-job`.
