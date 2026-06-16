-- V64 sidebar/permissions fix
-- Safe to run more than once.

INSERT INTO permissions (module, action, code, label, sort_order)
VALUES
('Dashboard', 'view', 'dashboard:view', 'Dashboard - View', 10),
('Franchise Settings', 'view', 'franchise_settings:view', 'Franchise Settings - View', 20),
('Franchise Details', 'view', 'franchise_details:view', 'Franchise Details - View', 30),
('Joinings', 'view', 'joinings:view', 'Joinings - View', 40),
('Funeral Services', 'view', 'funeral_services:view', 'Funeral Services - View', 50),
('Insurance Claims', 'view', 'insurance_claims:view', 'Insurance Claims - View', 60),
('Heat Map', 'view', 'heat_map:view', 'Heat Map - View', 70),
('Royalties', 'view', 'royalties:view', 'Royalties - View', 80),
('Monthly Figures', 'view', 'monthly_figures:view', 'Monthly Figures - View', 90),
('Finance', 'view', 'finance:view', 'Finance - View', 100),
('Users', 'view', 'users:view', 'Users - View', 110),
('Users', 'add', 'users:add', 'Users - Add', 111),
('Users', 'edit', 'users:edit', 'Users - Edit', 112),
('Users', 'delete', 'users:delete', 'Users - Delete', 113),
('User Roles', 'view', 'user_roles:view', 'User Roles - View', 120),
('User Roles', 'add', 'user_roles:add', 'User Roles - Add', 121),
('User Roles', 'edit', 'user_roles:edit', 'User Roles - Edit', 122),
('User Roles', 'delete', 'user_roles:delete', 'User Roles - Delete', 123),
('Franchise Management', 'view', 'franchise_management:view', 'Franchise Management - View', 130),
('Franchise Management', 'manage', 'franchise_management:manage', 'Franchise Management - Manage', 131),
('Imports & Data', 'view', 'imports_data:view', 'Imports & Data - View', 140),
('Imports & Data', 'import', 'imports_data:import', 'Imports & Data - Import', 141),
('Audit Logs', 'view', 'audit_logs:view', 'Audit Logs - View', 150),
('System Administration', 'view', 'system_administration:view', 'System Administration - View', 160)
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissions p
WHERE r.name = 'Admin'
ON CONFLICT DO NOTHING;
