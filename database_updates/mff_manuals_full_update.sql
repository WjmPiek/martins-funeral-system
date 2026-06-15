-- MFF Manuals module database update for Martins Funeral System
-- Preferred: deploy the code and run: flask db upgrade
-- Manual option: run this SQL in DBeaver/Render PostgreSQL.

CREATE TABLE IF NOT EXISTS mff_manuals (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    confidentiality_note VARCHAR(500),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_mff_manuals_title ON mff_manuals (title);

CREATE TABLE IF NOT EXISTS mff_manual_versions (
    id SERIAL PRIMARY KEY,
    manual_id INTEGER NOT NULL REFERENCES mff_manuals(id),
    version_label VARCHAR(80) NOT NULL DEFAULT 'v1.0',
    filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL DEFAULT 'application/pdf',
    storage_path VARCHAR(600) NOT NULL DEFAULT '',
    sha256 VARCHAR(64) NOT NULL DEFAULT '',
    uploaded_by_user_id INTEGER REFERENCES users(id),
    uploaded_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_published BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_mff_manual_version_label UNIQUE (manual_id, version_label)
);
CREATE INDEX IF NOT EXISTS ix_mff_manual_versions_manual_id ON mff_manual_versions (manual_id);
CREATE INDEX IF NOT EXISTS ix_mff_manual_versions_is_published ON mff_manual_versions (is_published);

CREATE TABLE IF NOT EXISTS mff_index_documents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(600) NOT NULL DEFAULT '',
    content_type VARCHAR(120) NOT NULL DEFAULT 'application/pdf',
    manual_id INTEGER REFERENCES mff_manuals(id),
    uploaded_by_user_id INTEGER REFERENCES users(id),
    uploaded_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_mff_index_documents_title ON mff_index_documents (title);
CREATE INDEX IF NOT EXISTS ix_mff_index_documents_manual_id ON mff_index_documents (manual_id);
CREATE INDEX IF NOT EXISTS ix_mff_index_documents_is_active ON mff_index_documents (is_active);

CREATE TABLE IF NOT EXISTS mff_manual_acknowledgements (
    id SERIAL PRIMARY KEY,
    manual_version_id INTEGER NOT NULL REFERENCES mff_manual_versions(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    attested_name VARCHAR(255) NOT NULL,
    attested_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(64),
    user_agent VARCHAR(500),
    CONSTRAINT uq_mff_ack_manual_user UNIQUE (manual_version_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_mff_manual_acknowledgements_manual_version_id ON mff_manual_acknowledgements (manual_version_id);
CREATE INDEX IF NOT EXISTS ix_mff_manual_acknowledgements_user_id ON mff_manual_acknowledgements (user_id);

INSERT INTO permissions (module, action, code, label, sort_order)
SELECT 'Manuals','view','manuals:view','View Manuals',910
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code='manuals:view');
INSERT INTO permissions (module, action, code, label, sort_order)
SELECT 'Manuals','manage','manuals:manage','Manage Manuals',911
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code='manuals:manage');
INSERT INTO permissions (module, action, code, label, sort_order)
SELECT 'Manuals','upload','manuals:upload','Upload Manuals',912
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code='manuals:upload');

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE r.name='Admin' AND p.code IN ('manuals:view','manuals:manage','manuals:upload')
AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id=r.id AND rp.permission_id=p.id);
