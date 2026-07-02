# Phase 12 - Enterprise Insights & Explanation Engine

This phase adds a plain-language explanation layer on top of the existing Martins Funeral System data.

## What it adds

- Admin Insight Explanations dashboard
- Executive summary narratives
- Franchise growth/decline explanations
- Province summaries
- Royalty calculation explanations using existing royalty snapshots
- BI insight explanations
- Rebuild action for Admin/Finance
- CLI rebuild command: `flask rebuild-insights`
- New migration: `v98_insights_engine`

## Important safety rule

This phase does **not** change royalty calculations, target calculations, imports, leaderboards, dashboards or payover values. It only reads trusted data already stored by earlier phases and generates explanatory narratives.

## Deploy commands

After deploying, run:

```bash
flask db current
flask db upgrade
flask db current
```

Expected head:

```text
v98_insights_engine (head)
```

Then optionally seed/rebuild:

```bash
flask rebuild-insights
```

## Admin navigation

Admin / Finance users can open:

- Executive Dashboard
- Business Intelligence
- Insight Explanations

## Data source

The explanations are generated from:

- monthly_figures
- royalty_calculation_snapshots
- franchise_health_snapshots
- business_insights
- heatmap province data

## Auditability

Every explanation is stored in `insight_narratives` with the period, type, severity, optional franchise/province, and source JSON used to generate the explanation.
