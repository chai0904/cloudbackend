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
