-- ============================================================
-- EduNexis Database Schema for Supabase PostgreSQL
-- Multi-Tenant Academic ERP — Enhanced with Trial + User Mgmt
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. TENANTS (Institutions)
-- ============================================================
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    subscription_plan VARCHAR(50) DEFAULT 'trial',
    max_students INT DEFAULT 100,
    is_active BOOLEAN DEFAULT true,
    trial_started_at TIMESTAMPTZ DEFAULT NOW(),
    trial_ends_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '14 days'),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 2. USERS
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    firebase_uid VARCHAR(128) UNIQUE,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('super_admin', 'admin', 'hod', 'faculty', 'student')),
    department_id UUID,
    is_active BOOLEAN DEFAULT true,
    created_by UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_firebase ON users(firebase_uid);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(tenant_id, role);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ============================================================
-- 3. DEPARTMENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS departments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    hod_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, code)
);

CREATE INDEX IF NOT EXISTS idx_departments_tenant ON departments(tenant_id);

-- Add FK for users.department_id (only if not exists)
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT fk_users_department
        FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- 4. ACADEMIC YEARS
-- ============================================================
CREATE TABLE IF NOT EXISTS academic_years (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    year_label VARCHAR(20) NOT NULL,
    is_current BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, year_label)
);

CREATE INDEX IF NOT EXISTS idx_academic_years_tenant ON academic_years(tenant_id);

-- ============================================================
-- 5. PROGRAMS
-- ============================================================
CREATE TABLE IF NOT EXISTS programs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    department_id UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    duration_years INT DEFAULT 4,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, code)
);

CREATE INDEX IF NOT EXISTS idx_programs_tenant ON programs(tenant_id);

-- ============================================================
-- 6. SEMESTERS
-- ============================================================
CREATE TABLE IF NOT EXISTS semesters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    academic_year_id UUID NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    semester_number INT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, academic_year_id, program_id, semester_number)
);

CREATE INDEX IF NOT EXISTS idx_semesters_tenant ON semesters(tenant_id);

-- ============================================================
-- 7. SUBJECTS
-- ============================================================
CREATE TABLE IF NOT EXISTS subjects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    semester_id UUID NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    max_marks INT DEFAULT 100,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, code)
);

CREATE INDEX IF NOT EXISTS idx_subjects_tenant ON subjects(tenant_id);

-- ============================================================
-- 8. FACULTY ASSIGNMENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS faculty_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    faculty_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, faculty_id, subject_id)
);

CREATE INDEX IF NOT EXISTS idx_faculty_assignments_tenant ON faculty_assignments(tenant_id);

-- ============================================================
-- 9. STUDENT ENROLLMENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS student_enrollments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    semester_id UUID NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    roll_number VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, student_id, semester_id)
);

CREATE INDEX IF NOT EXISTS idx_enrollments_tenant ON student_enrollments(tenant_id);

-- ============================================================
-- 10. ATTENDANCE
-- ============================================================
CREATE TABLE IF NOT EXISTS attendance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    faculty_id UUID NOT NULL REFERENCES users(id),
    date DATE NOT NULL,
    session VARCHAR(20) DEFAULT 'morning',
    status VARCHAR(10) NOT NULL CHECK (status IN ('present', 'absent', 'od')),
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_attendance_tenant ON attendance(tenant_id);
CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(tenant_id, student_id);
CREATE INDEX IF NOT EXISTS idx_attendance_subject_date ON attendance(tenant_id, subject_id, date);

-- ============================================================
-- 11. INTERNAL MARKS
-- ============================================================
CREATE TABLE IF NOT EXISTS internal_marks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    marks NUMERIC(5,2),
    max_marks INT DEFAULT 100,
    status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'submitted', 'approved', 'locked')),
    submitted_by UUID REFERENCES users(id),
    approved_by UUID REFERENCES users(id),
    locked_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    locked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, subject_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_marks_tenant ON internal_marks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_marks_status ON internal_marks(tenant_id, status);

-- ============================================================
-- 12. OD REQUESTS
-- ============================================================
CREATE TABLE IF NOT EXISTS od_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    reason TEXT NOT NULL,
    document_url TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'pending_faculty' CHECK (status IN ('pending_faculty', 'pending_hod', 'approved', 'rejected')),
    faculty_action_by UUID REFERENCES users(id),
    hod_action_by UUID REFERENCES users(id),
    faculty_action_at TIMESTAMPTZ,
    hod_action_at TIMESTAMPTZ,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_od_tenant ON od_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_od_status ON od_requests(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_od_student ON od_requests(tenant_id, student_id);

-- ============================================================
-- UPDATED_AT TRIGGER
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to all tables
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_type = 'BASE TABLE'
        AND table_name IN (
            'tenants', 'users', 'departments', 'academic_years',
            'programs', 'semesters', 'subjects', 'faculty_assignments',
            'student_enrollments', 'attendance', 'internal_marks', 'od_requests'
        )
    LOOP
        EXECUTE format('
            DROP TRIGGER IF EXISTS update_%I_updated_at ON %I;
            CREATE TRIGGER update_%I_updated_at
            BEFORE UPDATE ON %I
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        ', t, t, t, t);
    END LOOP;
END;
$$;

-- ============================================================
-- SEED DATA — Super Admin user (no tenant)
-- ============================================================
INSERT INTO users (id, email, name, role, firebase_uid, is_active)
VALUES (
    'a0000000-0000-0000-0000-000000000001',
    'superadmin@edunexis.in',
    'Super Admin',
    'super_admin',
    'sa-firebase-uid',
    true
) ON CONFLICT (firebase_uid) DO NOTHING;


-- ============================================================
-- EduNexis — Schema: Billing, Promo Codes, Subscription
-- Run this AFTER schema.sql and schema_extension.sql
-- ============================================================

-- ============================================================
-- 18. PROMO CODES
-- ============================================================
CREATE TABLE IF NOT EXISTS promo_codes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(50) UNIQUE NOT NULL,
    discount_type VARCHAR(20) NOT NULL CHECK (discount_type IN ('percentage', 'fixed')),
    discount_value NUMERIC(10,2) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    max_uses INT,
    current_uses INT DEFAULT 0,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed: ACM promo code — 100% discount
INSERT INTO promo_codes (code, discount_type, discount_value, is_active)
VALUES ('ACM', 'percentage', 100, true)
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- 19. TENANT BILLING
-- ============================================================
CREATE TABLE IF NOT EXISTS tenant_billing (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    plan VARCHAR(50) NOT NULL,
    base_price NUMERIC(12,2) DEFAULT 0,
    overage_charge NUMERIC(12,2) DEFAULT 0,
    discount_applied NUMERIC(12,2) DEFAULT 0,
    final_amount NUMERIC(12,2) DEFAULT 0,
    promo_code_used VARCHAR(50),
    billing_cycle_start DATE,
    billing_cycle_end DATE,
    payment_status VARCHAR(20) DEFAULT 'pending' CHECK (payment_status IN ('pending', 'paid', 'failed', 'waived')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_billing_tenant ON tenant_billing(tenant_id);

-- ============================================================
-- Ensure tenants table has student_limit and max_students
-- ============================================================
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS max_students INT DEFAULT 100;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS student_limit INT DEFAULT 100;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS subscription_plan VARCHAR(50) DEFAULT 'trial';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMPTZ;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMPTZ;

-- Apply updated_at trigger
DO $$
BEGIN
    EXECUTE '
        DROP TRIGGER IF EXISTS update_tenant_billing_updated_at ON tenant_billing;
    ';
EXCEPTION WHEN undefined_table THEN NULL;
END;
$$;


-- ============================================================
-- EduNexis — Schema: User Onboarding & Auth Extensions
-- Run this AFTER schema.sql
-- ============================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS requires_password_reset BOOLEAN DEFAULT false;
