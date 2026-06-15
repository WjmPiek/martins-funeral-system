-- Martins Funeral System Attendance module database update
-- Preferred method: run `flask db upgrade` so Alembic records the migration.
-- Manual fallback: run this SQL in DBeaver/Render PostgreSQL if Alembic is not available.

CREATE TABLE IF NOT EXISTS attendance_staff (
    id SERIAL PRIMARY KEY,
    franchise_id INTEGER REFERENCES franchises(id),
    first_name VARCHAR(120) NOT NULL DEFAULT '',
    surname VARCHAR(120) NOT NULL DEFAULT '',
    email VARCHAR(255) DEFAULT '',
    phone VARCHAR(80) DEFAULT '',
    id_number VARCHAR(80) DEFAULT '',
    employee_number VARCHAR(80) DEFAULT '',
    position VARCHAR(120) DEFAULT '',
    staff_type VARCHAR(40) DEFAULT 'Employee',
    website_url VARCHAR(255) DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    created_by_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_attendance_staff_franchise_id ON attendance_staff(franchise_id);
CREATE INDEX IF NOT EXISTS ix_attendance_staff_employee_number ON attendance_staff(employee_number);
CREATE INDEX IF NOT EXISTS ix_attendance_staff_is_active ON attendance_staff(is_active);

CREATE TABLE IF NOT EXISTS attendance_offices (
    id SERIAL PRIMARY KEY,
    franchise_id INTEGER REFERENCES franchises(id),
    name VARCHAR(160) NOT NULL DEFAULT 'Office',
    address VARCHAR(255) DEFAULT '',
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    allowed_radius_m INTEGER NOT NULL DEFAULT 100,
    qr_token VARCHAR(120) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_attendance_offices_franchise_id ON attendance_offices(franchise_id);
CREATE INDEX IF NOT EXISTS ix_attendance_offices_qr_token ON attendance_offices(qr_token);

CREATE TABLE IF NOT EXISTS attendance_events (
    id SERIAL PRIMARY KEY,
    staff_id INTEGER NOT NULL REFERENCES attendance_staff(id),
    franchise_id INTEGER REFERENCES franchises(id),
    office_id INTEGER REFERENCES attendance_offices(id),
    action VARCHAR(20) NOT NULL,
    event_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    accuracy_meters DOUBLE PRECISION,
    distance_from_site_m DOUBLE PRECISION,
    gps_status VARCHAR(50) DEFAULT '',
    work_location_type VARCHAR(50) DEFAULT 'Office',
    source VARCHAR(50) DEFAULT 'web',
    device_info TEXT,
    employee_note TEXT,
    manager_note TEXT,
    approval_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    approved_by_id INTEGER REFERENCES users(id),
    approved_at TIMESTAMP,
    rejected_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_attendance_events_staff_id ON attendance_events(staff_id);
CREATE INDEX IF NOT EXISTS ix_attendance_events_franchise_id ON attendance_events(franchise_id);
CREATE INDEX IF NOT EXISTS ix_attendance_events_event_time ON attendance_events(event_time);
CREATE INDEX IF NOT EXISTS ix_attendance_events_approval_status ON attendance_events(approval_status);

CREATE TABLE IF NOT EXISTS attendance_leave_requests (
    id SERIAL PRIMARY KEY,
    staff_id INTEGER NOT NULL REFERENCES attendance_staff(id),
    franchise_id INTEGER REFERENCES franchises(id),
    leave_type VARCHAR(80) NOT NULL DEFAULT 'Annual Leave',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    manager_note TEXT,
    decided_by_id INTEGER REFERENCES users(id),
    decided_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_attendance_leave_requests_staff_id ON attendance_leave_requests(staff_id);
CREATE INDEX IF NOT EXISTS ix_attendance_leave_requests_status ON attendance_leave_requests(status);

INSERT INTO permissions (module, action, code, label, sort_order)
SELECT 'Attendance', v.action, 'attendance:' || v.action, 'Attendance - ' || INITCAP(v.action), 900 + v.sort_order
FROM (VALUES ('view',1),('add',2),('edit',3),('delete',4),('export',5),('approve',6),('import',7),('manage',8)) AS v(action, sort_order)
WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = 'attendance:' || v.action);

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissions p
WHERE r.name = 'Admin' AND p.module = 'Attendance'
ON CONFLICT DO NOTHING;
