# Martin's Funerals Web System Starter

Flask + PostgreSQL + Render starter for:
- Client applications
- Policy product admin and audit logs
- Email signing links
- Electronic signature using drawn signature + typed name + OTP
- Signed application PDF and welcome pack PDF
- Lapsed policy import and recovery call logging
- Default linked roles and permissions

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python seed.py
python run.py
```

First production admin user:

Run `python seed.py` once. You can set `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD`; otherwise a temporary password is printed. Change the seeded password immediately in production. Do not commit real passwords to GitHub or documentation.

## Render deployment

1. Push this folder to GitHub.
2. In Render, create a Blueprint from `render.yaml`.
3. Add Gmail SMTP app password variables.
4. Set `BASE_URL` to your Render web URL.
5. Run `python seed.py` once in Render Shell.

## Gmail SMTP

Use a Gmail App Password, not your normal Gmail password.

## Important production upgrades

- Move uploaded files to S3/Google Drive when volume grows.
- Add proper SMS OTP provider.
- Add migrations with `flask db init`, `flask db migrate`, `flask db upgrade`.
- Add daily report scheduler worker or Render cron job.


## Script Flow Readability Update
- Sales script now runs in shorter human-speaking steps instead of large paragraphs.
- Each screen shows one conversation point or confirmation.
- Agent text is split into separate speech blocks.
- Progress counter now reflects the expanded guided flow.


## SVG Document Templates

The system now includes the CorelDRAW-exported SVG document templates in `app/static/svg_templates/` and converted PDF backgrounds in `app/static/pdf_templates/`.

Application template selection:
- Family / standard applications: `family_application.svg` -> `application_single_family.pdf`
- Member + Product applications: `member_product_application.svg` -> `application_member_product.pdf`

Terms template selection:
- Family / standard applications: `family_terms.svg` -> `family_terms.pdf`
- Member + Product applications: `member_product_terms.svg` -> `member_product_terms.pdf`

The PDF overlay engine scales legacy field coordinates to A4 so values stay aligned next to headings on the new SVG-derived templates.

## Phase 1 telesales workflow

This build adds the first proper call-centre workflow layer:

- Agent dashboard with a **Next Client** button.
- Due-now queue for clients that must be called today.
- Callback tracking through `next_action_date`.
- Required call outcomes.
- Lead status pipeline using `lapsed_policies.recovery_status`.
- Call notes/history from `recovery_call_logs`.

Phase 1 uses existing database columns only. No database migration is required for these changes.

Pipeline statuses used in Phase 1:

```text
New
Imported
Called
No Answer
Callback
Interested
Application Started
Signature Sent
FICA Outstanding
QA Review
Approved
Rejected
Closed
Reinstated
```


## Phase 2 - Callback + Client Timeline

Added on top of Phase 1:

- Callback Worklist at `/recovery/callbacks`
- Overdue, today, upcoming and unscheduled callback sections
- Client Timeline page for every lead
- Timeline records call logs, script sessions, applications, signing links, signatures and FICA uploads
- Callback link added to the top navigation
- Agent dashboard callback card now opens the callback worklist and shows overdue count

No new database columns were added in Phase 2. Existing tables are used so the Render PostgreSQL deployment remains safer.


## Phase 3 - Manager Dashboard

Added manager reporting and worklist screens without adding database columns.

- `/manager` Manager Dashboard
- Agent performance today
- Calls, open leads, callbacks, conversion and pending-work metrics
- Branch filter
- Lead status breakdown
- Pending callbacks, pending signatures, FICA review and QA pending panels

Only Admin, Manager and Branch Manager roles see the Manager link.


## Phase 4 - QA / Compliance

Adds QA/compliance dashboard, application review checklist, approval/rejection decisions, FICA document review, review history, and audit logging. See `PHASE4_NOTES.txt`.


## Phase 5 - Document Tracking

Added document tracking for applications:

- Document dashboard at `/documents`
- Application document status panel
- Required signature document tracking
- Required FICA document tracking
- Missing/rejected document filters
- Pending review filter
- Completion percentage per application
- Staff FICA upload
- Missing-document resend by Email or WhatsApp

No new database columns or tables were added in Phase 5.

## Branch Access Control Update

This package adds branch-level data isolation:
- Agents can only see their assigned branch data.
- Branch Managers/Managers/QA/Compliance can only see their assigned branch data.
- Admin can view all branches or filter by branch.
- Admin can assign branches from **User Approvals / User Branch Access**.

Before going live, make sure every Agent and Branch Manager has a branch value that exactly matches the branch names used in imported leads and applications.


## Phase 15 - Protected User / Agent Management

- Admin and Branch Manager user management added at `/auth/users`.
- Admin can create Branch Managers and Agents and allocate any branch.
- Branch Managers can create/manage Agents only for their own branch.
- Admin users are protected and cannot be edited or deleted.
- User actions are audit logged.

## Role & User Management Phase

This package makes `wjm@martinsdirect.com` the protected Super Admin. Admin can add/view/permanently delete any non-admin user. Branch Managers can add and view Agents only in their own branch. Agents only see their own allocated records. Super Admin/Admin accounts are protected from edit, delete, downgrade and reassignment. When a non-admin user is permanently deleted, linked history is reassigned to the Super Admin before the user row is removed.


## Phase 15 - CRM Workspace Redesign

This package adds a unified CRM workspace at `/workspace` so the dashboard/agent workspace no longer disappears when users move between tabs. Admin can select any branch/agent, Branch Managers are locked to their own branch, and Agents are locked to their own data. No database schema changes are required.

## Upload & System Fix Package

This build fixes the external client FICA upload flow for ID copy and Proof of Address from email signing links.

Key fixes:
- Uses a robust reflected insert for `client_fica_documents`, so older Render/PostgreSQL schemas with legacy columns do not block uploads.
- Runs the FICA document schema guard on startup even when `AUTO_CREATE_TABLES` is disabled.
- Keeps upload history and marks the newest document as active/Received.
- Keeps Super Admin access working for QA, Reports and Settings.
- Improves permanent user deletion by reassigning user history to the protected Super Admin before deleting the user.

Tested locally:
- App loads and registers routes.
- Client email signing link accepts ID copy upload.
- Client email signing link accepts Proof of Address upload.
- Application status changes from FICA Outstanding to Documents Received after required documents are uploaded.
- Key admin pages render after login.
- User deletion reassigns lapsed policy history to Super Admin before permanent delete.


## Production safety defaults added

This cleaned package removes bundled Git history, Python bytecode caches and sample upload files from the distributable zip.

Recommended Render environment variables:

```text
AUTO_CREATE_TABLES=0      # after migrations are in place
UPLOAD_FOLDER=/var/data/uploads  # only if you add a Render persistent disk
```

For long-term document storage, use Google Drive, S3, Supabase Storage or another persistent storage provider instead of Render's normal application filesystem.

Daily workflow priority:

1. Workspace
2. Next Client
3. My Clients / Import Leads
4. Callbacks
5. Applications
6. Documents
7. QA / Reports / Wallboard / Targets
8. Admin, Security and Settings

## 2026 CRM Production Improvements Added

This package includes the first production-ready CRM improvements:

- Lead Pipeline Kanban board at `/recovery/pipeline`.
- Drag-and-drop lead status updates with audit logging.
- Dark mode toggle saved in the browser.
- Mobile-friendly pipeline and existing responsive tables.
- Login brute-force protection for repeated failed attempts.
- Health check endpoint at `/healthz` for Render monitoring.
- PostgreSQL backup helper: `scripts/backup_postgres.ps1`.
- Migration helper: `scripts/create_migration.ps1`.
- Safer Git flow: deploy/test from `develop`, merge to `main` only after approval.

### Render Deployment Notes

Current safe start command:

```bash
gunicorn run:app
```

Pre-deploy command should remain blank until a `migrations/` folder has been created and tested. After migrations are created, set Render Pre-Deploy Command to:

```bash
flask db upgrade
```

### Recommended Render Environment Variables

```bash
FLASK_ENV=production
SECRET_KEY=<long random value>
DATABASE_URL=<Render PostgreSQL internal connection string>
BASE_URL=https://your-render-service.onrender.com
UPLOAD_FOLDER=/var/data/uploads
AUTO_CREATE_TABLES=1
```

After a proper migration workflow is confirmed, change:

```bash
AUTO_CREATE_TABLES=0
```
