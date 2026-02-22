-- ======================================================================================
-- EduNexis — DANGER: CLEAR ALL DATA
-- 
-- Executing this query will permanently WIPE ALL DATA from all tables in the database, 
-- but will leave the tables, schemas, and columns perfectly intact.
-- 
-- Use this to "factory reset" your Supabase database.
-- ======================================================================================

TRUNCATE TABLE 
    tenants, 
    users, 
    departments, 
    academic_years, 
    programs, 
    semesters, 
    subjects, 
    faculty_assignments, 
    student_enrollments, 
    attendance, 
    internal_marks, 
    od_requests, 
    promo_codes, 
    tenant_billing 
RESTART IDENTITY CASCADE;

-- Note: 
-- "CASCADE" ensures that all foreign key constraints are bypassed and child tables are cleared automatically.
-- "RESTART IDENTITY" resets all auto-incrementing IDs (like serial columns) back to 1.
