# Final user management rebuild

This patch separates Martins Funerals South Africa mother-company users from franchise employee users.

## Admin > Users

Admin creates only Martins/mother-company and registered franchise-owner accounts:

- Finance Manager
- Finance Assistant
- Regional Manager
- Franchise User

Finance Manager and Finance Assistant are not linked to franchises.
Regional Manager and Franchise User must be linked to active franchise data.

## Franchise Details > Employees

A Franchise User creates employees only under their own linked franchise:

- Manager
- Employee
- Agent

These users never see the Admin system and only see the franchise data they are linked to.

## Admin > Employees

Admin does not normally create franchise employees here. This is a master management/audit screen for franchise-created employees. Admin can edit, reset password, activate/deactivate, relink and change employee type.

## Migration

No new migration is needed if v76_user_creation_scope is already the database head.
