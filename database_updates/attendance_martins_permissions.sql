-- Martins Funeral System database update for the new Attendance sidebar module.
-- Run this on the Martins Funeral System PostgreSQL database after deploying the code.

BEGIN;

INSERT INTO permissions (module, action, code, label, sort_order) VALUES
('Attendance', 'view', 'attendance:view', 'Attendance View', 901),
('Attendance', 'add', 'attendance:add', 'Attendance Add', 902),
('Attendance', 'edit', 'attendance:edit', 'Attendance Edit', 903),
('Attendance', 'delete', 'attendance:delete', 'Attendance Delete', 904),
('Attendance', 'export', 'attendance:export', 'Attendance Export', 905),
('Attendance', 'approve', 'attendance:approve', 'Attendance Approve', 906),
('Attendance', 'import', 'attendance:import', 'Attendance Import', 907),
('Attendance', 'manage', 'attendance:manage', 'Attendance Manage', 908)
ON CONFLICT (code) DO UPDATE SET
    module = EXCLUDED.module,
    action = EXCLUDED.action,
    label = EXCLUDED.label,
    sort_order = EXCLUDED.sort_order;

-- Admin gets all Attendance permissions.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p ON p.code LIKE 'attendance:%'
WHERE r.name = 'Admin'
ON CONFLICT DO NOTHING;

-- Default role access.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code IN ('attendance:view','attendance:export')
WHERE r.name IN ('Regional Manager','Franchise Manager')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code IN ('attendance:view','attendance:export','attendance:approve')
WHERE r.name = 'Finance Manager'
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code IN ('attendance:view','attendance:export')
WHERE r.name = 'Finance Assistant'
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code = 'attendance:view'
WHERE r.name IN ('Franchise User','Read Only User')
ON CONFLICT DO NOTHING;

COMMIT;
