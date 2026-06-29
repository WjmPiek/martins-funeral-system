# User Creation Role Scope Fix

This patch fixes the problem where newly created users could be treated as if they belonged under one franchise user.

## Admin user creation

Admin/Finance Manager must select the user role first:

- Finance Manager: admin-side user, no franchise link
- Finance Assistant: admin-side user, no franchise link
- Regional Manager: must select one or more active franchises
- Franchise User: must select one or more active franchises

Admin-created Franchise Users are owners/scoped users, not employee users under another franchise user.

## Franchise user creation

Franchise users create only their own franchise-side users:

- Franchise Manager
- Franchise Employee
- Franchise Agent

The role must be selected and can be edited later by the franchise owner. These users are linked only to the owner franchise.

## Repair migration

Migration `v76_user_creation_scope` removes accidental franchise links and parent-franchise relationships from Admin/Finance Manager/Finance Assistant users.
