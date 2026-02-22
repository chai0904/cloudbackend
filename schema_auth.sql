-- ============================================================
-- EduNexis — Schema: User Onboarding & Auth Extensions
-- Run this AFTER schema.sql
-- ============================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS requires_password_reset BOOLEAN DEFAULT false;
