#FASTAPI

pip install -r requirements.txt

python -m uvicorn main:app --reload


#FLASK

pip install -r requirements.txt

py app.py


postgresql://postgres:MHWdrHhWHMDOVaCqZJjoLBxeHMgQRIZW@postgres.railway.internal:5432/railway
postgresql://postgres:MHWdrHhWHMDOVaCqZJjoLBxeHMgQRIZW@crossover.proxy.rlwy.net:36511/railway

#STRUKTUR 

    FASTAPI/
    ├─ app
    │   ├─ main.py
    │   ├─ connection
    │       ├─ database.py
    │       ├─ schemas.py
    │       └─ base.py
    │   ├─ models 
    |       ├─ models.py
    │   └─ routers
    │       ├─ directories.py
    │       ├─ documents.py
    │       └─ metadata.py
    └─ requirements.txt

    FLASKAPP/
    ├─ app.py
    ├─ requirements.txt
    ├─ templates
    │   └─ backend
    |       └─ components
    |           └─ all the components here
    |       └─ pages
    |           └─ dashboard.html
    |           └─ organization.html
    |           └─ department.html 
    |       └─ base.html
    └─ static
        └─ js
            └─ index.js

            

USER MANAGEMENT MODULE
├── Super Admin Panel
│   ├── Manage semua companies
│   ├── Create company admin
│   └── System-wide user stats
│   └── All departments
│   └── All organizations
├── Company Or Organization Admin Panel  
│   ├── Manage users di company sendiri
│   ├── Create/edit departments
│   ├── Assign department heads
│   └── Company user analytics
├── Department Management
│   └── Department heads manage member


 FASTAPI/
    ├─ app
    │   ├─ main.py
    │   ├─ connection
    │       ├─ database.py
    │       ├─ schemas.py
    │       └─ base.py
    │   ├─ models 
    |       ├─ models.py
    │   └─ routers
    │       ├─ directories.py
    │       ├─ documents.py
    │       └─ departments.py
    │       └─ metadata.py
    │       └─ organizations.py
    │       └─ auth.py
    │   └─ utils.py
    │       └─ security.py
    │       └─ authorization.py
    └─ requirements.txt

    FLASKAPP/
    ├─ app.py
    ├─ requirements.txt
    ├─ templates
    │   └─ backend
    |       └─ components
    |           └─ all the components here
    |       └─ pages
    |           └─ dashboard.html
    |           └─ organization.html
    |           └─ department.html 
    |       └─ base.html
    │   └─ frontend
    |       └─ activity-logs.html
    |       └─ share-preview.html
    │   └─ index.html
    │   └─ login.html
    └─ static
        └─ js
            └─ index.js
            └─ auth.js



postgres://avnadmin:AVNS_noBu8_GLpF_BhYClUzw@pg-32c1c2a5-grahanwaston-f621.c.aivencloud.com:25460/defaultdb?sslmode=require


Superadmin

- Bisa melihat semua data dari root tanpa batasan organisasi atau dept
- Panel admin lengkap

Email : superadmin@mail.co.id
Password : 12345678

Admin Organisasi / Company

- Hanya dapat melihat data sesuai organisasinya namun dapat melihat semua data department yg ada di organisasinya
- Hanya dapat mengatur sesuai organisasinya saja

Email : admin_org@mail.com
Password : 12345678

Head Dept 

- Hanya dapat melihat data yg ada di departmentnya yg 1 organisasi
- Hanya dapat mengatur member yg ada di dept nya 

Email : head_dept@mail.com
Password : 12345678

User

- Hanya dapat melihat data yg ada di departmentnya yg 1 organisasi
- Hanya dapat mengupload file sesuai dengan dept nya saja 

Email : user@mail.com
Password : 12345678



~~~~~~~~~~~~~~~~~~~
CHANGES LOG 120625
```````````````````

Changes on database 

-- ========================================
-- MIGRATION: Document Categories & Enhanced Document Attributes
-- Database: PostgreSQL
-- Date: 2024
-- ========================================

BEGIN;

-- 1. CREATE document_categories table
CREATE TABLE IF NOT EXISTS document_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(100) NOT NULL,
    description TEXT,
    organization_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    
    CONSTRAINT fk_doc_category_org 
        FOREIGN KEY (organization_id) 
        REFERENCES organizations(id) 
        ON DELETE CASCADE,
    
    CONSTRAINT fk_doc_category_creator 
        FOREIGN KEY (created_by) 
        REFERENCES users(id) 
        ON DELETE SET NULL,
    
    CONSTRAINT uq_doc_category_org_code 
        UNIQUE (organization_id, code)
);

-- Indexes for document_categories
CREATE INDEX idx_doc_categories_org_id ON document_categories(organization_id);
CREATE INDEX idx_doc_categories_code ON document_categories(code);
CREATE INDEX idx_doc_categories_created_at ON document_categories(created_at);

-- 2. ADD new columns to documents table
ALTER TABLE documents 
    ADD COLUMN IF NOT EXISTS file_type VARCHAR(50) DEFAULT 'Document',
    ADD COLUMN IF NOT EXISTS document_category_id INTEGER,
    ADD COLUMN IF NOT EXISTS file_category VARCHAR(50),
    ADD COLUMN IF NOT EXISTS file_owner VARCHAR(255),
    ADD COLUMN IF NOT EXISTS expire_date TIMESTAMP;

-- Add foreign key for document_category_id
ALTER TABLE documents
    ADD CONSTRAINT fk_documents_category
    FOREIGN KEY (document_category_id)
    REFERENCES document_categories(id)
    ON DELETE SET NULL;

-- Indexes for new document columns
CREATE INDEX IF NOT EXISTS idx_documents_file_type ON documents(file_type);
CREATE INDEX IF NOT EXISTS idx_documents_category_id ON documents(document_category_id);
CREATE INDEX IF NOT EXISTS idx_documents_file_category ON documents(file_category);
CREATE INDEX IF NOT EXISTS idx_documents_expire_date ON documents(expire_date);

-- 3. UPDATE existing documents to populate file_owner
UPDATE documents d
SET file_owner = u.name
FROM users u
WHERE d.created_by = u.id 
  AND d.file_owner IS NULL;

-- 4. CREATE VIEW for expired documents
CREATE OR REPLACE VIEW v_expired_documents AS
SELECT 
    d.id,
    d.name,
    d.title_document,
    d.file_type,
    d.file_owner,
    d.expire_date,
    d.created_at,
    d.status,
    o.name as organization_name,
    dept.name as department_name,
    u.name as creator_name,
    dc.name as category_name,
    CASE 
        WHEN d.expire_date < CURRENT_TIMESTAMP THEN 'Expired'
        WHEN d.expire_date < CURRENT_TIMESTAMP + INTERVAL '7 days' THEN 'Expiring Soon'
        ELSE 'Valid'
    END as expire_status
FROM documents d
LEFT JOIN organizations o ON d.organization_id = o.id
LEFT JOIN departments dept ON d.department_id = dept.id
LEFT JOIN users u ON d.created_by = u.id
LEFT JOIN document_categories dc ON d.document_category_id = dc.id
WHERE d.expire_date IS NOT NULL;

-- 5. CREATE FUNCTION to auto-archive expired documents
CREATE OR REPLACE FUNCTION fn_auto_archive_expired_documents()
RETURNS TABLE(affected_count INTEGER) AS $$
BEGIN
    UPDATE documents
    SET 
        status = 'archived',
        archived_at = CURRENT_TIMESTAMP
    WHERE 
        expire_date IS NOT NULL 
        AND expire_date < CURRENT_TIMESTAMP
        AND status = 'active';
    
    GET DIAGNOSTICS affected_count = ROW_COUNT;
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- 6. INSERT default document categories for all organizations
DO $$
DECLARE
    org_record RECORD;
    default_categories TEXT[][] := ARRAY[
        ['Letter', 'LETTER', 'Official correspondence and letters'],
        ['Contract', 'CONTRACT', 'Legal contracts and agreements'],
        ['Drawing', 'DRAWING', 'Technical drawings and blueprints'],
        ['User Manual', 'MANUAL', 'User guides and manuals'],
        ['Report', 'REPORT', 'Business reports and analysis'],
        ['Invoice', 'INVOICE', 'Financial invoices and receipts'],
        ['Proposal', 'PROPOSAL', 'Business proposals'],
        ['Policy', 'POLICY', 'Company policies and procedures'],
        ['Certificate', 'CERTIFICATE', 'Certificates and credentials'],
        ['Form', 'FORM', 'Official forms and templates']
    ];
    category TEXT[];
BEGIN
    FOR org_record IN SELECT id FROM organizations LOOP
        FOREACH category SLICE 1 IN ARRAY default_categories LOOP
            INSERT INTO document_categories (name, code, organization_id, description)
            VALUES (category[1], category[2], org_record.id, category[3])
            ON CONFLICT (organization_id, code) DO NOTHING;
        END LOOP;
    END LOOP;
END $$;

-- 7. CREATE TRIGGER to set file_owner automatically
CREATE OR REPLACE FUNCTION fn_set_file_owner()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.file_owner IS NULL AND NEW.created_by IS NOT NULL THEN
        SELECT name INTO NEW.file_owner
        FROM users
        WHERE id = NEW.created_by;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_set_file_owner
    BEFORE INSERT ON documents
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_file_owner();

-- 8. GRANT permissions (adjust user name as needed)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON document_categories TO your_app_user;
-- GRANT USAGE, SELECT ON SEQUENCE document_categories_id_seq TO your_app_user;
-- GRANT SELECT ON v_expired_documents TO your_app_user;

COMMIT;

-- ========================================
-- VERIFICATION QUERIES
-- ========================================

-- Check new columns
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'documents'
  AND column_name IN ('file_type', 'document_category_id', 'file_category', 'file_owner', 'expire_date')
ORDER BY ordinal_position;

-- Check document_categories
SELECT 
    dc.id,
    dc.name,
    dc.code,
    o.name as organization,
    COUNT(d.id) as document_count
FROM document_categories dc
LEFT JOIN organizations o ON dc.organization_id = o.id
LEFT JOIN documents d ON d.document_category_id = dc.id
GROUP BY dc.id, dc.name, dc.code, o.name
ORDER BY o.name, dc.name;

-- Check expired documents view
SELECT * FROM v_expired_documents LIMIT 10;

-- Statistics
SELECT 
    'Total Categories' as metric,
    COUNT(*)::TEXT as value
FROM document_categories
UNION ALL
SELECT 
    'Documents with Category',
    COUNT(*)::TEXT
FROM documents
WHERE document_category_id IS NOT NULL
UNION ALL
SELECT 
    'Documents with Expire Date',
    COUNT(*)::TEXT
FROM documents
WHERE expire_date IS NOT NULL
UNION ALL
SELECT 
    'Expired Documents',
    COUNT(*)::TEXT
FROM documents
WHERE expire_date < CURRENT_TIMESTAMP AND status = 'active';

-- Create organization_licenses table
CREATE TABLE IF NOT EXISTS organization_licenses (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL UNIQUE REFERENCES organizations(id) ON DELETE CASCADE,
    subscription_status VARCHAR(20) DEFAULT 'trial',
    start_date TIMESTAMP DEFAULT NOW(),
    end_date TIMESTAMP NOT NULL,
    trial_days INTEGER DEFAULT 30,
    max_users INTEGER DEFAULT 10,
    max_storage_gb INTEGER DEFAULT 5,
    last_checked TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_org_license_org_id ON organization_licenses(organization_id);
CREATE INDEX idx_org_license_end_date ON organization_licenses(end_date);
CREATE INDEX idx_org_license_status ON organization_licenses(subscription_status);

-- Function untuk auto-create license saat organization baru
CREATE OR REPLACE FUNCTION create_default_license()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO organization_licenses (
        organization_id,
        subscription_status,
        start_date,
        end_date,
        trial_days
    ) VALUES (
        NEW.id,
        'trial',
        NOW(),
        NOW() + INTERVAL '30 days',
        30
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_create_org_license
AFTER INSERT ON organizations
FOR EACH ROW
EXECUTE FUNCTION create_default_license();

-- Function untuk check expired licenses (jalankan via cron)
CREATE OR REPLACE FUNCTION check_expired_licenses()
RETURNS void AS $$
BEGIN
    UPDATE organization_licenses
    SET subscription_status = 'expired',
        updated_at = NOW()
    WHERE end_date < NOW() 
    AND subscription_status IN ('active', 'trial');
    
    UPDATE organization_licenses
    SET last_checked = NOW()
    WHERE id > 0;
END;
$$ LANGUAGE plpgsql;

-- View untuk monitoring
CREATE OR REPLACE VIEW v_organization_license_status AS
SELECT 
    o.id as org_id,
    o.name as org_name,
    o.code as org_code,
    o.status as org_status,
    l.subscription_status,
    l.start_date,
    l.end_date,
    EXTRACT(DAY FROM (l.end_date - NOW())) as days_remaining,
    CASE 
        WHEN l.end_date < NOW() THEN false
        ELSE true
    END as is_active,
    l.max_users,
    l.max_storage_gb,
    (SELECT COUNT(*) FROM users WHERE organization_id = o.id) as current_users,
    l.last_checked
FROM organizations o
LEFT JOIN organization_licenses l ON o.id = l.organization_id;

-- Function untuk create missing licenses untuk existing organizations
CREATE OR REPLACE FUNCTION create_missing_licenses()
RETURNS TABLE(org_id INT, org_name VARCHAR, license_created BOOLEAN) AS $$
DECLARE
    org_record RECORD;
    license_exists BOOLEAN;
BEGIN
    -- Loop through all organizations
    FOR org_record IN 
        SELECT id, name FROM organizations
    LOOP
        -- Check if license exists
        SELECT EXISTS(
            SELECT 1 FROM organization_licenses 
            WHERE organization_id = org_record.id
        ) INTO license_exists;
        
        -- If not exists, create it
        IF NOT license_exists THEN
            INSERT INTO organization_licenses (
                organization_id,
                subscription_status,
                start_date,
                end_date,
                trial_days,
                max_users,
                max_storage_gb
            ) VALUES (
                org_record.id,
                'trial',
                NOW(),
                NOW() + INTERVAL '30 days',
                30,
                10,
                5
            );
            
            org_id := org_record.id;
            org_name := org_record.name;
            license_created := TRUE;
            RETURN NEXT;
        END IF;
    END LOOP;
    
    RETURN;
END;
$$ LANGUAGE plpgsql;

-- Jalankan function ini untuk create missing licenses
SELECT * FROM create_missing_licenses();

-- Atau bisa pakai query langsung:
INSERT INTO organization_licenses (
    organization_id,
    subscription_status,
    start_date,
    end_date,
    trial_days,
    max_users,
    max_storage_gb
)
SELECT 
    o.id,
    'trial',
    NOW(),
    NOW() + INTERVAL '30 days',
    30,
    10,
    5
FROM organizations o
LEFT JOIN organization_licenses l ON o.id = l.organization_id
WHERE l.id IS NULL;