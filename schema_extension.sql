-- ============================================================
-- EduNexis — Schema Extension: Batches, Classes, Timetable, Workload
-- Run this AFTER the base schema.sql
-- ============================================================

-- ============================================================
-- 13. BATCHES / SECTIONS (e.g., CSE-A 2024, CSE-B 2024)
-- ============================================================
CREATE TABLE IF NOT EXISTS batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    semester INT NOT NULL DEFAULT 1,
    name VARCHAR(100) NOT NULL,              -- e.g., "Section A", "Batch 1"
    code VARCHAR(50) NOT NULL,               -- e.g., "CSE-A", "ECE-B"
    max_students INT DEFAULT 60,
    academic_year_id UUID REFERENCES academic_years(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, code)
);

CREATE INDEX IF NOT EXISTS idx_batches_tenant ON batches(tenant_id);

-- Link students to batches
CREATE TABLE IF NOT EXISTS batch_students (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    roll_number VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, batch_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_batch_students_tenant ON batch_students(tenant_id);

-- ============================================================
-- 14. CLASSROOMS / ROOMS
-- ============================================================
CREATE TABLE IF NOT EXISTS classrooms (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,              -- e.g., "Room 101", "Lab A"
    code VARCHAR(50) NOT NULL,               -- e.g., "R101", "LABA"
    building VARCHAR(100),
    floor VARCHAR(20),
    capacity INT DEFAULT 60,
    room_type VARCHAR(50) DEFAULT 'lecture',  -- lecture, lab, seminar
    is_available BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, code)
);

CREATE INDEX IF NOT EXISTS idx_classrooms_tenant ON classrooms(tenant_id);

-- ============================================================
-- 15. FACULTY WORKLOAD
-- ============================================================
ALTER TABLE faculty_assignments
    ADD COLUMN IF NOT EXISTS hours_per_week INT DEFAULT 4,
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES batches(id);

-- Aggregate workload view
CREATE TABLE IF NOT EXISTS faculty_workload (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    faculty_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    max_hours_per_week INT DEFAULT 20,
    current_hours_per_week INT DEFAULT 0,
    preferred_slots TEXT,                     -- JSON array of preferred timeslots
    unavailable_slots TEXT,                   -- JSON array of unavailable timeslots
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, faculty_id)
);

CREATE INDEX IF NOT EXISTS idx_faculty_workload_tenant ON faculty_workload(tenant_id);

-- ============================================================
-- 16. TIMETABLE SLOTS
-- ============================================================
CREATE TABLE IF NOT EXISTS timetable_slots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    faculty_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    classroom_id UUID REFERENCES classrooms(id),
    day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 1 AND 6), -- 1=Mon, 6=Sat
    period_number INT NOT NULL,              -- 1-8 (period of the day)
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    slot_type VARCHAR(20) DEFAULT 'lecture',  -- lecture, lab, tutorial
    is_active BOOLEAN DEFAULT true,
    academic_year_id UUID REFERENCES academic_years(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    -- No double-booking: same batch, same day, same period
    UNIQUE(tenant_id, batch_id, day_of_week, period_number),
    -- Same faculty can't be in two places at once
    UNIQUE(tenant_id, faculty_id, day_of_week, period_number),
    -- Same room can't be used twice at same time
    UNIQUE(tenant_id, classroom_id, day_of_week, period_number)
);

CREATE INDEX IF NOT EXISTS idx_timetable_tenant ON timetable_slots(tenant_id);
CREATE INDEX IF NOT EXISTS idx_timetable_batch ON timetable_slots(tenant_id, batch_id);
CREATE INDEX IF NOT EXISTS idx_timetable_faculty ON timetable_slots(tenant_id, faculty_id);

-- ============================================================
-- 17. TIMETABLE TEMPLATES (preset period timings)
-- ============================================================
CREATE TABLE IF NOT EXISTS period_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    period_number INT NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    label VARCHAR(50),                       -- e.g., "Period 1", "Lunch Break"
    is_break BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, period_number)
);

-- Default period timings seed
INSERT INTO period_templates (tenant_id, period_number, start_time, end_time, label, is_break)
SELECT 'a0000000-0000-0000-0000-000000000000'::UUID, p.num, p.st, p.et, p.lbl, p.brk
FROM (VALUES
    (1, '09:00'::TIME, '09:50'::TIME, 'Period 1', false),
    (2, '09:50'::TIME, '10:40'::TIME, 'Period 2', false),
    (3, '10:40'::TIME, '11:00'::TIME, 'Break', true),
    (4, '11:00'::TIME, '11:50'::TIME, 'Period 3', false),
    (5, '11:50'::TIME, '12:40'::TIME, 'Period 4', false),
    (6, '12:40'::TIME, '13:30'::TIME, 'Lunch', true),
    (7, '13:30'::TIME, '14:20'::TIME, 'Period 5', false),
    (8, '14:20'::TIME, '15:10'::TIME, 'Period 6', false)
) AS p(num, st, et, lbl, brk)
WHERE NOT EXISTS (SELECT 1 FROM period_templates LIMIT 1);

-- Apply updated_at triggers to new tables
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT unnest(ARRAY['batches', 'classrooms', 'faculty_workload', 'timetable_slots'])
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
-- 17. DYNAMIC ASSESSMENTS & RESULTS (FAT 1, FAT 2, End Sem)
-- ============================================================
CREATE TABLE IF NOT EXISTS exams (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL, -- e.g., 'FAT 1', 'FAT 2', 'End Semester'
    exam_type VARCHAR(50) NOT NULL DEFAULT 'internal', -- 'internal', 'external'
    max_marks INT DEFAULT 100,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, batch_id, name)
);

CREATE INDEX IF NOT EXISTS idx_exams_tenant ON exams(tenant_id);

CREATE TABLE IF NOT EXISTS exam_marks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    exam_id UUID NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    marks NUMERIC(5,2),
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, exam_id, subject_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_exammarks_tenant ON exam_marks(tenant_id);

-- Add od_type to od_requests (Phase 9)
ALTER TABLE od_requests 
ADD COLUMN IF NOT EXISTS od_type VARCHAR(50) DEFAULT 'normal';

-- Add triggers for exams and exam_marks updated_at
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT unnest(ARRAY['exams', 'exam_marks'])
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
