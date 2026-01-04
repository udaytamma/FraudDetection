-- Fraud Detection Platform - Database Initialization
-- This script runs automatically when PostgreSQL container starts

-- Enable UUID extension for generating unique IDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- EVIDENCE TABLE
-- Immutable transaction evidence for dispute representment
-- ============================================================================
CREATE TABLE IF NOT EXISTS transaction_evidence (
    -- Primary identifier
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Transaction identifiers (for linking)
    transaction_id VARCHAR(64) NOT NULL UNIQUE,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,

    -- Timestamp when evidence was captured
    captured_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Transaction details (immutable snapshot)
    amount_cents BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    merchant_id VARCHAR(64) NOT NULL,
    merchant_name VARCHAR(256),
    merchant_mcc VARCHAR(4),

    -- Entity identifiers (tokenized/hashed, no raw PAN)
    card_token VARCHAR(64) NOT NULL,
    card_bin VARCHAR(8),
    card_last_four VARCHAR(4),
    device_id VARCHAR(64),
    ip_address INET,
    user_id VARCHAR(64),

    -- Risk signals captured at decision time
    risk_score DECIMAL(5,4) NOT NULL,
    criminal_score DECIMAL(5,4),
    friendly_fraud_score DECIMAL(5,4),

    -- Decision made
    decision VARCHAR(20) NOT NULL,
    decision_reasons JSONB NOT NULL DEFAULT '[]',

    -- Features snapshot (for model training and dispute evidence)
    features_snapshot JSONB NOT NULL DEFAULT '{}',

    -- Verification signals (3DS, AVS, CVV)
    avs_result VARCHAR(10),
    cvv_result VARCHAR(10),
    three_ds_result VARCHAR(20),
    three_ds_version VARCHAR(10),

    -- Device fingerprint data
    device_fingerprint JSONB,

    -- Geo data
    geo_country VARCHAR(2),
    geo_region VARCHAR(64),
    geo_city VARCHAR(128),

    -- Policy version for audit (string for backward compatibility)
    policy_version VARCHAR(32),

    -- Policy version ID for proper foreign key linkage (added in v1.1)
    policy_version_id INTEGER,

    -- Indexes for common queries
    CONSTRAINT valid_decision CHECK (decision IN ('ALLOW', 'FRICTION', 'REVIEW', 'BLOCK'))
);

-- Add foreign key after policy_versions table is created
-- This is done via ALTER TABLE to handle table creation order

-- Indexes for evidence lookups
CREATE INDEX IF NOT EXISTS idx_evidence_card_token ON transaction_evidence(card_token);
CREATE INDEX IF NOT EXISTS idx_evidence_user_id ON transaction_evidence(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_merchant_id ON transaction_evidence(merchant_id);
CREATE INDEX IF NOT EXISTS idx_evidence_captured_at ON transaction_evidence(captured_at);
CREATE INDEX IF NOT EXISTS idx_evidence_decision ON transaction_evidence(decision);

-- ============================================================================
-- CHARGEBACKS TABLE
-- Links chargebacks to original transactions for training labels
-- ============================================================================
CREATE TABLE IF NOT EXISTS chargebacks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Link to original transaction
    transaction_id VARCHAR(64) NOT NULL REFERENCES transaction_evidence(transaction_id),

    -- Chargeback details
    chargeback_id VARCHAR(64) NOT NULL UNIQUE,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Amount (may differ from original)
    amount_cents BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',

    -- Reason codes (network-specific)
    reason_code VARCHAR(20) NOT NULL,
    reason_description VARCHAR(256),

    -- Fraud classification (derived from reason code + investigation)
    fraud_type VARCHAR(20),

    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'RECEIVED',

    -- Representment outcome
    represented_at TIMESTAMP WITH TIME ZONE,
    representment_outcome VARCHAR(20),

    CONSTRAINT valid_fraud_type CHECK (
        fraud_type IS NULL OR
        fraud_type IN ('CRIMINAL', 'FRIENDLY', 'MERCHANT_ERROR', 'UNKNOWN')
    ),
    CONSTRAINT valid_status CHECK (
        status IN ('RECEIVED', 'INVESTIGATING', 'REPRESENTED', 'WON', 'LOST', 'EXPIRED')
    )
);

-- Indexes for chargeback queries
CREATE INDEX IF NOT EXISTS idx_chargebacks_transaction_id ON chargebacks(transaction_id);
CREATE INDEX IF NOT EXISTS idx_chargebacks_received_at ON chargebacks(received_at);
CREATE INDEX IF NOT EXISTS idx_chargebacks_fraud_type ON chargebacks(fraud_type);
CREATE INDEX IF NOT EXISTS idx_chargebacks_status ON chargebacks(status);

-- ============================================================================
-- POLICY VERSIONS TABLE
-- Immutable version history for policy settings with semantic versioning
-- Every change creates a new version; rollback creates new version from old content
-- ============================================================================
CREATE TABLE IF NOT EXISTS policy_versions (
    id SERIAL PRIMARY KEY,

    -- Semantic version (e.g., "1.0.0", "1.0.1", "1.1.0")
    version VARCHAR(20) NOT NULL UNIQUE,

    -- Full policy content as JSON (for reconstruction)
    policy_content JSONB NOT NULL,

    -- SHA256 hash of policy content for integrity verification
    policy_hash VARCHAR(64) NOT NULL,

    -- Change metadata
    change_type VARCHAR(50) NOT NULL,  -- 'threshold', 'rule_add', 'rule_update', 'rule_delete', 'list_add', 'list_remove', 'rollback', 'initial'
    change_summary TEXT NOT NULL,      -- Human-readable summary of what changed
    changed_by VARCHAR(100) NOT NULL DEFAULT 'system',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Whether this is the currently active policy
    is_active BOOLEAN NOT NULL DEFAULT FALSE,

    -- Previous version reference (NULL for initial)
    previous_version VARCHAR(20),

    CONSTRAINT valid_change_type CHECK (
        change_type IN ('initial', 'threshold', 'rule_add', 'rule_update', 'rule_delete', 'list_add', 'list_remove', 'rollback')
    )
);

CREATE INDEX IF NOT EXISTS idx_policy_versions_created_at ON policy_versions(created_at);
CREATE INDEX IF NOT EXISTS idx_policy_versions_is_active ON policy_versions(is_active);
CREATE INDEX IF NOT EXISTS idx_policy_versions_version ON policy_versions(version);

-- ============================================================================
-- POLICY AUDIT LOG (legacy - kept for compatibility)
-- Tracks all policy changes for compliance and debugging
-- ============================================================================
CREATE TABLE IF NOT EXISTS policy_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Policy identification
    policy_version VARCHAR(32) NOT NULL,
    policy_hash VARCHAR(64) NOT NULL,

    -- Change metadata
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    changed_by VARCHAR(64) NOT NULL,
    change_type VARCHAR(20) NOT NULL,
    change_description TEXT,

    -- Policy content (YAML as text for auditability)
    policy_content TEXT NOT NULL,

    -- Previous version reference
    previous_version VARCHAR(32),

    CONSTRAINT valid_audit_change_type CHECK (
        change_type IN ('CREATE', 'UPDATE', 'ROLLBACK', 'ACTIVATE', 'DEACTIVATE')
    )
);

CREATE INDEX IF NOT EXISTS idx_policy_audit_changed_at ON policy_audit_log(changed_at);
CREATE INDEX IF NOT EXISTS idx_policy_audit_version ON policy_audit_log(policy_version);

-- ============================================================================
-- DECISION METRICS TABLE
-- Aggregated metrics for economic optimization
-- ============================================================================
CREATE TABLE IF NOT EXISTS decision_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Time bucket (hourly aggregation)
    bucket_start TIMESTAMP WITH TIME ZONE NOT NULL,
    bucket_end TIMESTAMP WITH TIME ZONE NOT NULL,

    -- Counts by decision
    total_transactions BIGINT NOT NULL DEFAULT 0,
    allowed_count BIGINT NOT NULL DEFAULT 0,
    friction_count BIGINT NOT NULL DEFAULT 0,
    review_count BIGINT NOT NULL DEFAULT 0,
    blocked_count BIGINT NOT NULL DEFAULT 0,

    -- Amounts
    total_amount_cents BIGINT NOT NULL DEFAULT 0,
    allowed_amount_cents BIGINT NOT NULL DEFAULT 0,
    blocked_amount_cents BIGINT NOT NULL DEFAULT 0,

    -- Latency percentiles (stored as arrays)
    latency_p50_ms DECIMAL(10,2),
    latency_p95_ms DECIMAL(10,2),
    latency_p99_ms DECIMAL(10,2),

    -- Score distributions
    avg_risk_score DECIMAL(5,4),
    avg_criminal_score DECIMAL(5,4),
    avg_friendly_score DECIMAL(5,4),

    CONSTRAINT unique_bucket UNIQUE (bucket_start)
);

CREATE INDEX IF NOT EXISTS idx_metrics_bucket ON decision_metrics(bucket_start);

-- ============================================================================
-- ADD FOREIGN KEY CONSTRAINTS (after all tables exist)
-- ============================================================================
-- Link transaction_evidence to policy_versions
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_evidence_policy_version'
    ) THEN
        ALTER TABLE transaction_evidence
        ADD CONSTRAINT fk_evidence_policy_version
        FOREIGN KEY (policy_version_id) REFERENCES policy_versions(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_policy_version_id ON transaction_evidence(policy_version_id);

-- ============================================================================
-- GRANT PERMISSIONS
-- ============================================================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO fraud_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO fraud_user;
