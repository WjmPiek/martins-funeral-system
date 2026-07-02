# Dashboard Template Visibility Fix

This fix resolves blank pages in the new enterprise sections.

## Root cause
The base template renders authenticated page bodies through:

```jinja
{% block app_content %}{% endblock %}
```

Some newer enterprise templates were created with:

```jinja
{% block content %}{% endblock %}
```

Because the block names did not match, the route loaded successfully but the page body rendered empty.

## Fixed templates
- `app/templates/admin/executive_dashboard.html`
- `app/templates/admin/business_intelligence.html`
- `app/templates/admin/insights_dashboard.html`
- `app/templates/admin/royalty_management.html`
- performance templates that used the old block name

## Correct rebuild commands
Use these command names:

```bash
flask rebuild-business-intelligence
flask rebuild-insights
flask recalculate-royalties --month 5 --year 2026
flask rebuild-performance-cache --month 5 --year 2026
flask seed-workflow-defaults
flask workflow-summary
```

