-- Martins Funeral System - Built-in Insurance Claims module database update
-- Safe to run more than once in DBeaver or Render PostgreSQL.

CREATE TABLE IF NOT EXISTS insurance_policy_monthly_raw (
    id SERIAL PRIMARY KEY,
    franchise_id INTEGER REFERENCES franchises(id),
    franchise_name VARCHAR(255) NOT NULL,
    import_month DATE NOT NULL,
    retail_premium NUMERIC(18,2) DEFAULT 0,
    risk_premium NUMERIC(18,2) DEFAULT 0,
    claims NUMERIC(18,2) DEFAULT 0,
    claim_count NUMERIC(18,2) DEFAULT 0,
    claim_paid_franchise NUMERIC(18,2) DEFAULT 0,
    claim_paid_client NUMERIC(18,2) DEFAULT 0,
    repudiated_pending NUMERIC(18,2) DEFAULT 0,
    grand_total_claims NUMERIC(18,2) DEFAULT 0,
    policy_qty NUMERIC(18,2) DEFAULT 0,
    original_risk_premium NUMERIC(18,2) DEFAULT 0,
    r1_policy_fee NUMERIC(18,2) DEFAULT 0,
    underwriter_2_1_fee NUMERIC(18,2) DEFAULT 0,
    risk_after_r1 NUMERIC(18,2) DEFAULT 0,
    single_monthly_premium_total NUMERIC(18,2) DEFAULT 0,
    current_scenario VARCHAR(120) DEFAULT '100% Claim Ratio',
    source_file VARCHAR(255) DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_ins_policy_franchise_month UNIQUE(franchise_name, import_month)
);
CREATE INDEX IF NOT EXISTS ix_ins_policy_month ON insurance_policy_monthly_raw(import_month);
CREATE INDEX IF NOT EXISTS ix_ins_policy_franchise ON insurance_policy_monthly_raw(franchise_name);

CREATE TABLE IF NOT EXISTS insurance_claims_monthly_raw (
    id SERIAL PRIMARY KEY,
    franchise_id INTEGER REFERENCES franchises(id),
    claim_key VARCHAR(255) DEFAULT '',
    claims_franchise_name VARCHAR(255) NOT NULL,
    claim_month DATE NOT NULL,
    claims_amount NUMERIC(18,2) DEFAULT 0,
    claim_count NUMERIC(18,2) DEFAULT 0,
    claim_paid_franchise NUMERIC(18,2) DEFAULT 0,
    claim_paid_client NUMERIC(18,2) DEFAULT 0,
    repudiated_pending NUMERIC(18,2) DEFAULT 0,
    grand_total_claims NUMERIC(18,2) DEFAULT 0,
    source_file VARCHAR(255) DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_ins_claim_key_franchise_month UNIQUE(claim_key, claims_franchise_name, claim_month)
);
CREATE INDEX IF NOT EXISTS ix_ins_claim_month ON insurance_claims_monthly_raw(claim_month);
CREATE INDEX IF NOT EXISTS ix_ins_claim_key ON insurance_claims_monthly_raw(claim_key);
CREATE INDEX IF NOT EXISTS ix_ins_claim_franchise ON insurance_claims_monthly_raw(claims_franchise_name);

CREATE TABLE IF NOT EXISTS insurance_policydata_detail_raw (
    id SERIAL PRIMARY KEY,
    source_file VARCHAR(255) NOT NULL,
    import_month DATE NOT NULL,
    row_number INTEGER NOT NULL,
    franchise_id INTEGER REFERENCES franchises(id),
    franchise_name VARCHAR(255) NOT NULL,
    relation VARCHAR(80) DEFAULT '',
    is_mem BOOLEAN DEFAULT false NOT NULL,
    retail_premium NUMERIC(18,2) DEFAULT 0,
    original_risk_premium NUMERIC(18,2) DEFAULT 0,
    mpia NUMERIC(18,2) DEFAULT 0,
    single_premium NUMERIC(18,6) DEFAULT 0,
    r1_policy_fee NUMERIC(18,2) DEFAULT 0,
    adv_fund_2_1_fee NUMERIC(18,2) DEFAULT 0,
    risk_after_r1 NUMERIC(18,2) DEFAULT 0,
    new_risk_premium NUMERIC(18,2) DEFAULT 0,
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_ins_policydata_source_month_row UNIQUE(source_file, import_month, row_number)
);
CREATE INDEX IF NOT EXISTS ix_ins_policydata_month ON insurance_policydata_detail_raw(import_month);
CREATE INDEX IF NOT EXISTS ix_ins_policydata_franchise ON insurance_policydata_detail_raw(franchise_name);
CREATE INDEX IF NOT EXISTS ix_ins_policydata_relation ON insurance_policydata_detail_raw(relation);
CREATE INDEX IF NOT EXISTS ix_ins_policydata_is_mem ON insurance_policydata_detail_raw(is_mem);

CREATE TABLE IF NOT EXISTS insurance_import_history (
    id SERIAL PRIMARY KEY,
    import_type VARCHAR(80) NOT NULL,
    source_file VARCHAR(255) DEFAULT '',
    imported_months TEXT DEFAULT '',
    row_count INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'success',
    message TEXT DEFAULT '',
    created_by_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ins_import_type ON insurance_import_history(import_type);
CREATE INDEX IF NOT EXISTS ix_ins_import_status ON insurance_import_history(status);

CREATE TABLE IF NOT EXISTS insurance_franchise_mapping (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(255) NOT NULL UNIQUE,
    mapped_name VARCHAR(255) NOT NULL,
    franchise_id INTEGER REFERENCES franchises(id),
    approved BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ins_map_source ON insurance_franchise_mapping(source_name);
CREATE INDEX IF NOT EXISTS ix_ins_map_mapped ON insurance_franchise_mapping(mapped_name);

CREATE TABLE IF NOT EXISTS insurance_claim_cases (
    id SERIAL PRIMARY KEY,
    claim_ref VARCHAR(120) NOT NULL UNIQUE,
    franchise_id INTEGER REFERENCES franchises(id),
    franchise_name VARCHAR(255) DEFAULT '',
    claimant_name VARCHAR(255) DEFAULT '',
    policy_number VARCHAR(120) DEFAULT '',
    id_number VARCHAR(80) DEFAULT '',
    claim_type VARCHAR(120) DEFAULT 'Funeral Claim',
    claim_date DATE,
    date_of_death DATE,
    claim_amount NUMERIC(18,2) DEFAULT 0,
    status VARCHAR(60) DEFAULT 'Open' NOT NULL,
    priority VARCHAR(40) DEFAULT 'Normal',
    assigned_to_id INTEGER REFERENCES users(id),
    created_by_id INTEGER REFERENCES users(id),
    archived BOOLEAN DEFAULT false NOT NULL,
    notes TEXT DEFAULT '',
    closed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ins_claim_cases_status ON insurance_claim_cases(status);
CREATE INDEX IF NOT EXISTS ix_ins_claim_cases_franchise ON insurance_claim_cases(franchise_name);
CREATE INDEX IF NOT EXISTS ix_ins_claim_cases_created ON insurance_claim_cases(created_at);
CREATE INDEX IF NOT EXISTS ix_ins_claim_cases_archived ON insurance_claim_cases(archived);

CREATE TABLE IF NOT EXISTS insurance_claim_notes (
    id SERIAL PRIMARY KEY,
    claim_id INTEGER NOT NULL REFERENCES insurance_claim_cases(id),
    user_id INTEGER REFERENCES users(id),
    user_email VARCHAR(255) DEFAULT '',
    note TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ins_claim_notes_claim ON insurance_claim_notes(claim_id, created_at);

CREATE TABLE IF NOT EXISTS insurance_claim_attachments (
    id SERIAL PRIMARY KEY,
    claim_id INTEGER NOT NULL REFERENCES insurance_claim_cases(id),
    filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(600) NOT NULL,
    content_type VARCHAR(120) DEFAULT '',
    size_bytes INTEGER DEFAULT 0,
    uploaded_by_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ins_claim_attachments_claim ON insurance_claim_attachments(claim_id, created_at);

CREATE TABLE IF NOT EXISTS insurance_claim_document_types (
    id SERIAL PRIMARY KEY,
    document_type VARCHAR(160) NOT NULL UNIQUE,
    claim_type VARCHAR(120) DEFAULT 'Funeral Claim',
    sort_order INTEGER DEFAULT 0 NOT NULL,
    is_active BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ins_doc_types_active ON insurance_claim_document_types(is_active, sort_order);

CREATE TABLE IF NOT EXISTS insurance_claim_document_rules (
    id SERIAL PRIMARY KEY,
    document_type_id INTEGER NOT NULL REFERENCES insurance_claim_document_types(id),
    rule_key VARCHAR(120) NOT NULL,
    rule_value TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ins_doc_rules_type ON insurance_claim_document_rules(document_type_id, rule_key);

INSERT INTO permissions (module, action, code, label, sort_order)
SELECT 'Insurance Claims', v.action, v.code, v.label, v.sort_order
FROM (VALUES
    ('view', 'insurance_claims:view', 'View Insurance Claims', 310),
    ('add', 'insurance_claims:add', 'Add Insurance Claims', 311),
    ('edit', 'insurance_claims:edit', 'Edit Insurance Claims', 312),
    ('delete', 'insurance_claims:delete', 'Delete Insurance Claims', 313),
    ('export', 'insurance_claims:export', 'Export Insurance Claims', 314),
    ('approve', 'insurance_claims:approve', 'Approve Insurance Claims', 315),
    ('import', 'insurance_claims:import', 'Import Insurance Claims', 316),
    ('manage', 'insurance_claims:manage', 'Manage Insurance Claims', 317)
) AS v(action, code, label, sort_order)
WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = v.code);

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE r.name = 'Admin' AND p.code LIKE 'insurance_claims:%'
AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

INSERT INTO insurance_claim_document_types (document_type, claim_type, sort_order, is_active)
SELECT v.document_type, 'Funeral Claim', v.sort_order, true
FROM (VALUES
    ('Death Certificate', 1), ('BI-1663', 2), ('Policy Schedule', 3), ('ID Copy', 4), ('Bank Confirmation', 5), ('Claim Form', 6)
) AS v(document_type, sort_order)
WHERE NOT EXISTS (SELECT 1 FROM insurance_claim_document_types d WHERE d.document_type = v.document_type);
