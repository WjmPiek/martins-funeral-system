# Martins Direct Basic Portal

Basic Flask starter system with:

- PostgreSQL database
- User registration
- Login/logout
- Multiple users
- Forgot password with secure reset token
- Dashboard placeholder for future modules

## 1. Create PostgreSQL database

```sql
CREATE DATABASE martins_basic_portal;
```

## 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

On Windows:

```bash
venv\Scripts\activate
```

## 3. Install requirements

```bash
pip install -r requirements.txt
```

## 4. Create environment file

Copy `.env.example` to `.env` and update your PostgreSQL username/password.

```bash
cp .env.example .env
```

Example:

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/martins_basic_portal
SECRET_KEY=change-this-secret-key
```

## 5. Initialize database migrations

```bash
flask --app run.py db init
flask --app run.py db migrate -m "Initial users table"
flask --app run.py db upgrade
```

## 6. Run the system

```bash
python run.py
```

Open:

```text
http://127.0.0.1:5000
```

## Password reset email

To send real reset emails, configure SMTP details in `.env`.

During development, if email is not configured, the reset link will be shown in the Flask terminal and also flashed on screen for testing.

## Future modules

Add future modules as separate blueprints inside `app/`, for example:

```text
app/users/
app/claims/
app/reports/
app/analytics/
```

## Dashboard layout update

The dashboard now includes:

- Left sidebar with module tabs
- Logo area at the top-left of the sidebar
- Top-right user area showing `Logged in as Name Surname`
- Module cards ready to be connected to future routes

To replace the placeholder logo, save your company logo as:

```text
app/static/img/logo-placeholder.svg
```

Or update the image filename in:

```text
app/templates/base.html
```

## Layout and PDF/Print Standards

The portal now includes global CSS rules for readable text, aligned forms, responsive tables, and PDF/print output.

Use these helper classes when adding modules:

- Wrap wide tables in `<div class="table-responsive">...</div>`.
- Add `class="table-compact"` to tables with many columns.
- Add `class="pdf-landscape"` to the report/table container when the page has many columns and should print/export as landscape.
- Use `class="form-grid"` for aligned label/input form rows.
- Use `class="form-actions"` for aligned form buttons.

For future automatic PDF export, the backend can count table columns and apply `pdf-landscape` when the column count is high.

## Role and Permission Engine

This version includes a configurable role-management foundation.

Admin menu:

```text
Users
User Roles
```

Default role templates included:

```text
Admin
Regional Manager
Finance Manager
Finance Assistant
Franchise Manager
Franchise User
Read Only User
```

Each role can be configured with checkbox permissions per module/page:

```text
View
Add
Edit
Delete
Export
Approve
Import
Manage
```

Modules currently included in the permission matrix:

```text
Dashboard
Franchise Settings
Franchise Details
Joinings
Funeral Services
Insurance Claims
Heat Map
Royalties
Monthly Figures
Finance
Users
User Roles
Franchise Management
Imports & Data
Audit Logs
System Administration
PDF Templates
Email Templates
Backup Management
```

### First admin user

The first registered user automatically becomes `Admin` so that the system can be configured.

After logging in as the first user, go to:

```text
Admin > User Roles > Create/Update Default Roles
```

This creates/updates the default permission matrix.

### Sidebar permissions

The sidebar now hides/shows module tabs based on the logged-in user's permissions. Admin users see everything.

### Database migration note

Because this version adds roles and permissions, create a new migration if you already initialized the previous database:

```bash
flask --app run.py db migrate -m "Add roles and permissions"
flask --app run.py db upgrade
```

For a fresh database, run the normal migration steps from this README.

## Franchise Details Module

The `Franchise Settings > Franchise Details` page now contains a professional franchise profile form with:

- Business/franchise name
- PTY number
- VAT number
- Office address
- Office number
- 24-hour number
- Franchisee name and surname
- Franchisee cell phone number
- Franchisee email address
- Facebook, Instagram, TikTok, website and public email fields
- Franchise agreement from/to dates
- Regional manager and finance manager reminder email fields
- Five-row royalty scale with amount bands and percentages

Agreement dates and royalty scale fields are protected. They can be adjusted by Admin users and users with `Franchise Agreement: Manage` / `Royalty Scale: Manage` permissions, which are included in the Finance Manager template.

## Agreement Expiry Notifications

The system includes a command for scheduled reminders:

```bash
flask check-franchise-expiry
```

Run this command daily from cron, Render cron jobs, or another scheduler. It sends reminder emails to the captured Regional Manager and Finance Manager email addresses when the agreement has 60 days or 30 days remaining.

## Verification checklist - latest build

This package has been checked against the current requested foundation. Included now:

- Martins Funerals System naming across the app.
- PostgreSQL-ready Flask application using SQLAlchemy and Flask-Migrate.
- User registration with name, surname, email and password.
- Login and logout.
- Secure forgot-password flow using an email reset link with a temporary token.
- Dashboard with left sidebar, logo area and top-right "Logged in as" user display.
- Sidebar module structure for Dashboard, Franchise Settings, Joinings, Funeral Services, Insurance Claims, Heat Map, Royalties, Monthly Figures and Finance.
- Admin section with Users, User Roles, Franchise Management, Finance, Imports & Data, Audit Logs and System Administration placeholders.
- Role templates: Admin, Regional Manager, Finance Manager, Finance Assistant, Franchise Manager, Franchise User and Read Only User.
- Checkbox permission matrix per role and module/action: view, add, edit, delete, export, approve, import and manage.
- Admin has unrestricted access by design.
- Sidebar visibility is controlled by role permissions.
- Professional Franchise Details form with business name, franchise code, PTY number, VAT number, address, office number, 24-hour number, franchisee details, social media, website and public email.
- Franchise agreement from/to dates with 60-day and 30-day reminder email logic.
- Agreement dates and royalty scale are restricted to Admin / Finance Manager permissions.
- Five royalty scale rows with amount-from, amount-to and percentage.
- Audit log foundation for important changes and PDF exports.
- Global PDF report utility with cover page, franchise name, logo placeholder/path support, address, contact details, generated-by details, bold headings and confidentiality notice.
- PDF table rules include automatic text wrapping, repeating table headers and automatic landscape orientation when there are more than 8 columns.
- Franchise Details PDF export button.

Important setup notes:

- Run the default role/permission seeding after installation from the Admin role screen, or visit `/admin/seed` as Admin.
- Configure email settings in `.env` before password reset emails and agreement expiry reminders can send in production.
- Add a cron job or scheduled task to run `flask check-franchise-expiry` daily for the 60-day and 30-day agreement reminder emails.
- The first registered user becomes Admin automatically.
