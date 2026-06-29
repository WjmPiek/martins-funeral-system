# Mother Company and Franchise User Flow Final Fix

This patch separates user creation according to the Martins Funerals business structure.

## Admin > Users
Admin creates only Martins-side and registered franchise owner accounts:
- Finance Manager
- Finance Assistant
- Regional Manager
- Franchise User

Finance users are not linked to a franchise. Regional Managers and Franchise Users must receive a franchise scope.

## Franchise Details > Employees
Franchise Users create only their own franchise employees:
- Manager
- Employee
- Agent

These users are linked to the same franchise and never see the Admin system.

## Admin > Employees / Franchise Employees
This is the master oversight list for all employees created by franchise users. Admin can edit, deactivate, reset password and relink employees, but the normal creation flow is still through the Franchise User's Employees page.

## Migration repair
The v76 migration now points to v74_franchise_employees because v75_user_scope_ui was missing from the deployed migration chain.
