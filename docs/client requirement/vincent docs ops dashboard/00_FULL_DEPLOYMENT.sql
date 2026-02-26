-- =============================================================================
-- FUNNEL ANALYTICS - FULL DEPLOYMENT SCRIPT
-- =============================================================================
--
-- Prepared by: Vincent Van Seumeren
-- Date: 2026-02-01
--
-- This script creates all funnel analytics objects in the dwh schema.
-- Execute with a user that has CREATE privileges on the dwh schema.
--
-- Estimated execution time: < 1 minute (object creation only)
-- Post-deployment: Run CALL dwh.refresh_all_funnel_views(); to populate data
--
-- =============================================================================

\echo '============================================='
\echo 'FUNNEL ANALYTICS DEPLOYMENT'
\echo 'Started at:' `date`
\echo '============================================='

-- =============================================================================
-- PHASE 1: DATA FOUNDATION
-- =============================================================================

\echo ''
\echo '>>> PHASE 1: Data Foundation'
\echo ''

-- -----------------------------------------------------------------------------
-- 1.1: Funnel Stage Dimension Table
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.dim_funnel_stage...'

CREATE TABLE IF NOT EXISTS dwh.dim_funnel_stage (
    stage_key SERIAL PRIMARY KEY,
    stage_id VARCHAR(50) NOT NULL UNIQUE,
    stage_name VARCHAR(100) NOT NULL,
    stage_order INT NOT NULL,
    stage_category VARCHAR(20) NOT NULL,
    applies_to_b2c BOOLEAN DEFAULT TRUE,
    applies_to_b2b BOOLEAN DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_stage_category CHECK (stage_category IN ('PRE_FUNNEL', 'OPERATIONAL', 'OUTCOME'))
);

CREATE INDEX IF NOT EXISTS idx_dim_funnel_stage_category ON dwh.dim_funnel_stage(stage_category);
CREATE INDEX IF NOT EXISTS idx_dim_funnel_stage_order ON dwh.dim_funnel_stage(stage_order);

COMMENT ON TABLE dwh.dim_funnel_stage IS 'Funnel stage dimension aligned with underwriting kanban workflow';

-- Populate stage data
TRUNCATE TABLE dwh.dim_funnel_stage RESTART IDENTITY CASCADE;

INSERT INTO dwh.dim_funnel_stage (stage_id, stage_name, stage_order, stage_category, applies_to_b2c, applies_to_b2b, description) VALUES
('DATA_COLLECTION', 'Data Collection', 0, 'PRE_FUNNEL', TRUE, TRUE, 'Dealer/customer submission through data collection'),
('AUTOMATED_CHECKS', 'Automated Checks', 1, 'OPERATIONAL', TRUE, TRUE, 'System-driven verification: Credit Scoring, AML, KDF'),
('KYC_SIGNING', 'KYC + Signing', 2, 'OPERATIONAL', TRUE, TRUE, 'Identity verification and contract signing'),
('UNDERWRITING_REVIEW', 'Underwriting Review', 3, 'OPERATIONAL', TRUE, TRUE, 'Manual review by underwriters'),
('ACTIVATION_FUNDING', 'Activation & Funding', 4, 'OPERATIONAL', TRUE, TRUE, 'Final activation and fund disbursement'),
('FUNDED', 'Funded', 10, 'OUTCOME', TRUE, TRUE, 'Application successfully funded'),
('AUTO_REJECTED', 'Auto-rejected', 11, 'OUTCOME', TRUE, TRUE, 'System automatically rejected'),
('MANUAL_REJECTED', 'Manual-rejected', 12, 'OUTCOME', TRUE, TRUE, 'Underwriter manually rejected'),
('CUSTOMER_DROPOFF', 'Customer Drop-off', 13, 'OUTCOME', TRUE, TRUE, 'Customer abandoned application');

\echo 'Created dwh.dim_funnel_stage with 9 stages'

-- -----------------------------------------------------------------------------
-- 1.2: Step-to-Stage Mapping View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_step_stage_mapping...'

CREATE OR REPLACE VIEW dwh.v_step_stage_mapping AS
WITH step_mappings AS (
    -- Stage 1: Automated Checks
    SELECT 'AUTOMATED_CHECKS' as stage_id, 'Age check' as step_pattern, TRUE as b2c, TRUE as b2b
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'Credit Scoring', TRUE, FALSE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'Credit Scoring Crif', FALSE, TRUE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'Credit Scoring Intrum', TRUE, FALSE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'KDF Private', TRUE, FALSE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'KDF Business', FALSE, TRUE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'AML Personal', TRUE, FALSE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'AML business', FALSE, TRUE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'CRIF (request list of controllers)', FALSE, TRUE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'ZEK Request Info B2C', TRUE, FALSE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'ZEK Register Credit Claim', TRUE, TRUE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'Customer check', TRUE, TRUE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'Company check', FALSE, TRUE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'Controller check', FALSE, TRUE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'System Task (define locales)', TRUE, TRUE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'ZFS Proposal Private', TRUE, FALSE
    UNION ALL SELECT 'AUTOMATED_CHECKS', 'ZFS Proposal business', FALSE, TRUE
    -- Stage 2: KYC + Signing
    UNION ALL SELECT 'KYC_SIGNING', 'KYC initiation', TRUE, FALSE
    UNION ALL SELECT 'KYC_SIGNING', 'KYC initiation Lease', TRUE, FALSE
    UNION ALL SELECT 'KYC_SIGNING', 'KYC initiation MP', TRUE, FALSE
    UNION ALL SELECT 'KYC_SIGNING', 'KYC initiation B2B Lease', FALSE, TRUE
    UNION ALL SELECT 'KYC_SIGNING', 'KYC initiation B2B MP', FALSE, TRUE
    UNION ALL SELECT 'KYC_SIGNING', 'KYC initiation Ent Lease', TRUE, FALSE
    UNION ALL SELECT 'KYC_SIGNING', 'KYC initiation Ent MP', TRUE, FALSE
    UNION ALL SELECT 'KYC_SIGNING', 'KYC Bypass', TRUE, TRUE
    UNION ALL SELECT 'KYC_SIGNING', 'KYC bypass', TRUE, TRUE
    UNION ALL SELECT 'KYC_SIGNING', 'Send email with link to KYC', TRUE, FALSE
    UNION ALL SELECT 'KYC_SIGNING', 'Send email with link to KYC Lease', TRUE, FALSE
    UNION ALL SELECT 'KYC_SIGNING', 'Send email with link to KYC Lease(MP)', TRUE, FALSE
    UNION ALL SELECT 'KYC_SIGNING', 'Send signee 1  email with link to KYC', FALSE, TRUE
    UNION ALL SELECT 'KYC_SIGNING', 'Send signee 2 email with link to KYC', FALSE, TRUE
    UNION ALL SELECT 'KYC_SIGNING', 'Send Ent  email with link to KYC', TRUE, FALSE
    UNION ALL SELECT 'KYC_SIGNING', 'QES', TRUE, TRUE
    UNION ALL SELECT 'KYC_SIGNING', 'Send signing contract-reminder e-mail (Lessee)', TRUE, FALSE
    UNION ALL SELECT 'KYC_SIGNING', 'Send signing contract-reminder e-mail (Signee 1)', FALSE, TRUE
    UNION ALL SELECT 'KYC_SIGNING', 'Send signing contract-reminder e-mail (Signee 2)', FALSE, TRUE
    UNION ALL SELECT 'KYC_SIGNING', 'Get signed contract', TRUE, TRUE
    -- Stage 3: Underwriting Review
    UNION ALL SELECT 'UNDERWRITING_REVIEW', 'Document review', TRUE, TRUE
    UNION ALL SELECT 'UNDERWRITING_REVIEW', 'CRM (Document review)', TRUE, TRUE
    UNION ALL SELECT 'UNDERWRITING_REVIEW', 'Pre-UNW check documents', TRUE, TRUE
    UNION ALL SELECT 'UNDERWRITING_REVIEW', 'CRM', TRUE, TRUE
    UNION ALL SELECT 'UNDERWRITING_REVIEW', 'Bawag Request contract review', TRUE, TRUE
    UNION ALL SELECT 'UNDERWRITING_REVIEW', 'Bawag Request review result', TRUE, TRUE
    UNION ALL SELECT 'UNDERWRITING_REVIEW', 'Rejected by BAWAG', TRUE, TRUE
    UNION ALL SELECT 'UNDERWRITING_REVIEW', 'Bawag confirmed financing', TRUE, TRUE
    UNION ALL SELECT 'UNDERWRITING_REVIEW', 'Higher down payment required', TRUE, TRUE
    UNION ALL SELECT 'UNDERWRITING_REVIEW', 'Custom RV check', TRUE, TRUE
    UNION ALL SELECT 'UNDERWRITING_REVIEW', 'Regenerate contract', TRUE, TRUE
    -- Stage 4: Activation & Funding
    UNION ALL SELECT 'ACTIVATION_FUNDING', 'Contract Activation', TRUE, TRUE
    UNION ALL SELECT 'ACTIVATION_FUNDING', 'Funds confirmation', TRUE, TRUE
    UNION ALL SELECT 'ACTIVATION_FUNDING', 'Create ECode178', TRUE, TRUE
    UNION ALL SELECT 'ACTIVATION_FUNDING', 'Register Contract in ZEK', TRUE, TRUE
    UNION ALL SELECT 'ACTIVATION_FUNDING', 'Get contract dates', TRUE, TRUE
    UNION ALL SELECT 'ACTIVATION_FUNDING', 'Odoo First Invoice', TRUE, TRUE
    UNION ALL SELECT 'ACTIVATION_FUNDING', 'Odoo Request Invoice for down payment', TRUE, TRUE
    UNION ALL SELECT 'ACTIVATION_FUNDING', 'Bawag  Create contract', TRUE, TRUE
    UNION ALL SELECT 'ACTIVATION_FUNDING', 'Bawag  Update contract (results of KYC/QES)', TRUE, TRUE
    UNION ALL SELECT 'ACTIVATION_FUNDING', 'Funding package sent to Bawag', TRUE, TRUE
    UNION ALL SELECT 'ACTIVATION_FUNDING', 'Create handover protocol', TRUE, TRUE
    UNION ALL SELECT 'ACTIVATION_FUNDING', 'Create Dealer buyback agreement', TRUE, TRUE
    -- Pre-Funnel: Data Collection
    UNION ALL SELECT 'DATA_COLLECTION', 'Welcome page', TRUE, FALSE
    UNION ALL SELECT 'DATA_COLLECTION', 'Welcome page (BAWAG)', TRUE, TRUE
    UNION ALL SELECT 'DATA_COLLECTION', 'Welcome Page', TRUE, TRUE
    UNION ALL SELECT 'DATA_COLLECTION', 'Calculation page', TRUE, TRUE
    UNION ALL SELECT 'DATA_COLLECTION', 'Calculation page B2C (lease/loan)', TRUE, FALSE
    UNION ALL SELECT 'DATA_COLLECTION', 'Calculation page B2C (mobility_plan)', TRUE, FALSE
    UNION ALL SELECT 'DATA_COLLECTION', 'Calculation page B2B (lease/loan)', FALSE, TRUE
    UNION ALL SELECT 'DATA_COLLECTION', 'Calculation page B2B (mobility_plan)', FALSE, TRUE
    UNION ALL SELECT 'DATA_COLLECTION', 'Personal data', TRUE, FALSE
    UNION ALL SELECT 'DATA_COLLECTION', 'Personal income', TRUE, FALSE
    UNION ALL SELECT 'DATA_COLLECTION', 'Personal expenses', TRUE, FALSE
    UNION ALL SELECT 'DATA_COLLECTION', 'About the company', FALSE, TRUE
    UNION ALL SELECT 'DATA_COLLECTION', 'Company contact details', FALSE, TRUE
    UNION ALL SELECT 'DATA_COLLECTION', 'Business figures', FALSE, TRUE
    UNION ALL SELECT 'DATA_COLLECTION', 'Account creation', TRUE, TRUE
    UNION ALL SELECT 'DATA_COLLECTION', 'Entrepreneur About the company', TRUE, FALSE
    UNION ALL SELECT 'DATA_COLLECTION', 'Entrepreneur Personal Income', TRUE, FALSE
    UNION ALL SELECT 'DATA_COLLECTION', 'Entrepreneur Personal Expenses', TRUE, FALSE
)
SELECT
    sm.step_pattern as step_name,
    sm.stage_id,
    ds.stage_name,
    ds.stage_order,
    ds.stage_category,
    sm.b2c as applies_to_b2c,
    sm.b2b as applies_to_b2b
FROM step_mappings sm
JOIN dwh.dim_funnel_stage ds ON sm.stage_id = ds.stage_id;

COMMENT ON VIEW dwh.v_step_stage_mapping IS 'Maps flowapp step names to funnel stages with B2C/B2B applicability';

-- -----------------------------------------------------------------------------
-- 1.3: Status-to-Outcome Mapping View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_status_outcome_mapping...'

CREATE OR REPLACE VIEW dwh.v_status_outcome_mapping AS
SELECT
    status_code,
    outcome_stage_id,
    ds.stage_name as outcome_name,
    outcome_category,
    is_terminal,
    is_funnel_relevant,
    status_description
FROM (
    VALUES
        ('IN_PROGRESS', NULL, 'active', FALSE, TRUE, 'Application currently being processed'),
        ('', NULL, 'pre_submission', FALSE, TRUE, 'Status not yet assigned'),
        ('FUNDS_CONFIRMED', 'FUNDED', 'success', TRUE, TRUE, 'Application successfully funded'),
        ('COMPLETED', NULL, 'completed', TRUE, TRUE, 'All steps completed'),
        ('DECLINED', 'AUTO_REJECTED', 'rejection', TRUE, TRUE, 'System auto-rejected'),
        ('REJECTED', 'MANUAL_REJECTED', 'rejection', TRUE, TRUE, 'Underwriter manually rejected'),
        ('ARCHIVED', 'CUSTOMER_DROPOFF', 'abandonment', TRUE, TRUE, 'Customer abandoned application'),
        ('FAILED', NULL, 'technical', TRUE, TRUE, 'Technical/system failure'),
        ('UNKNOWN', NULL, 'unknown', FALSE, TRUE, 'Status not determined'),
        ('SETTLEMENT_SAASDO', NULL, 'post_funnel', TRUE, FALSE, 'Contract in settlement'),
        ('OWNERSHIP_CHANGE_SAASDO', NULL, 'post_funnel', TRUE, FALSE, 'Ownership transfer'),
        ('EARLY_TERMINATION_SAASDO', NULL, 'post_funnel', TRUE, FALSE, 'Contract terminated early'),
        ('AUTO_TERMINATION_SAASDO', NULL, 'post_funnel', TRUE, FALSE, 'Automatic termination'),
        ('TOTAL_LOSS_SAASDO', NULL, 'post_funnel', TRUE, FALSE, 'Vehicle total loss'),
        ('END_OF_CONTRACT_SAASDO', NULL, 'post_funnel', TRUE, FALSE, 'Contract ended normally'),
        ('BUYOUT', NULL, 'post_funnel', TRUE, FALSE, 'Customer buyout')
) AS status_map(status_code, outcome_stage_id, outcome_category, is_terminal, is_funnel_relevant, status_description)
LEFT JOIN dwh.dim_funnel_stage ds ON status_map.outcome_stage_id = ds.stage_id;

COMMENT ON VIEW dwh.v_status_outcome_mapping IS 'Maps contract statuses to outcome stages and categories';

-- -----------------------------------------------------------------------------
-- 1.4: Helper Function
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.get_stage_for_step()...'

CREATE OR REPLACE FUNCTION dwh.get_stage_for_step(p_step_name VARCHAR)
RETURNS VARCHAR AS $$
DECLARE
    v_stage_id VARCHAR;
BEGIN
    SELECT stage_id INTO v_stage_id
    FROM dwh.v_step_stage_mapping
    WHERE UPPER(TRIM(step_name)) = UPPER(TRIM(p_step_name))
    LIMIT 1;
    RETURN COALESCE(v_stage_id, 'UNKNOWN');
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION dwh.get_stage_for_step IS 'Returns stage_id for a given flowapp step name';

-- -----------------------------------------------------------------------------
-- 1.5: Application Events View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_application_events...'

CREATE OR REPLACE VIEW dwh.v_application_events AS
WITH
status_events AS (
    SELECT
        h.contract_id AS application_id,
        h.created_at AS event_timestamp,
        'STATUS_CHANGE' AS event_type,
        h.status AS event_name,
        som.outcome_stage_id AS stage_id,
        som.outcome_category,
        som.is_terminal,
        som.is_funnel_relevant,
        NULL::VARCHAR AS flowapp_step_type,
        h.id AS source_id,
        'status_history' AS source_table
    FROM ods.contract_status_history_sst h
    LEFT JOIN dwh.v_status_outcome_mapping som ON h.status = som.status_code
    WHERE h.is_deleted_flg = 0
),
step_events AS (
    SELECT
        s.contract_id AS application_id,
        s.created_at AS event_timestamp,
        'STEP_COMPLETED' AS event_type,
        s.step AS event_name,
        ssm.stage_id,
        ssm.stage_category AS outcome_category,
        FALSE AS is_terminal,
        CASE WHEN ssm.stage_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_funnel_relevant,
        s.flowapp_step_type,
        s.id AS source_id,
        'flowapp_steps' AS source_table
    FROM ods.contract_flowapp_steps_sst s
    LEFT JOIN dwh.v_step_stage_mapping ssm ON UPPER(TRIM(s.step)) = UPPER(TRIM(ssm.step_name))
    WHERE s.is_deleted_flg = 0
      AND s.flowapp_step_type = 'MAIN'
),
all_events AS (
    SELECT * FROM status_events
    UNION ALL
    SELECT * FROM step_events
)
SELECT
    e.application_id,
    e.event_timestamp,
    e.event_type,
    e.event_name,
    e.stage_id,
    ds.stage_name,
    ds.stage_order,
    ds.stage_category,
    e.outcome_category,
    e.is_terminal,
    e.is_funnel_relevant,
    e.flowapp_step_type,
    CASE c.request_type
        WHEN 'PRIVATE' THEN 'B2C'
        WHEN 'BUSINESS' THEN 'B2B'
        ELSE 'UNKNOWN'
    END AS party_type,
    c.oem_partner_id AS dealer_id,
    c.contract_origin,
    c.product_type,
    c.country_code,
    e.source_id,
    e.source_table
FROM all_events e
JOIN ods.contract c ON e.application_id = c.representation_id
LEFT JOIN dwh.dim_funnel_stage ds ON e.stage_id = ds.stage_id;

COMMENT ON VIEW dwh.v_application_events IS 'Unified event log combining status changes and step completions for funnel analytics';

-- -----------------------------------------------------------------------------
-- 1.6: Stage Entry Timestamps View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_application_stage_entries...'

CREATE OR REPLACE VIEW dwh.v_application_stage_entries AS
SELECT
    application_id,
    stage_id,
    stage_name,
    stage_order,
    party_type,
    dealer_id,
    MIN(event_timestamp) AS first_entry_at,
    MAX(event_timestamp) AS last_event_at,
    COUNT(*) AS event_count,
    COUNT(CASE WHEN event_type = 'STATUS_CHANGE' THEN 1 END) AS status_event_count,
    COUNT(CASE WHEN event_type = 'STEP_COMPLETED' THEN 1 END) AS step_event_count
FROM dwh.v_application_events
WHERE stage_id IS NOT NULL
  AND is_funnel_relevant = TRUE
GROUP BY application_id, stage_id, stage_name, stage_order, party_type, dealer_id;

COMMENT ON VIEW dwh.v_application_stage_entries IS 'Aggregated stage entry/exit timestamps per application';

-- -----------------------------------------------------------------------------
-- 1.7: Application Outcomes View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_application_outcomes...'

CREATE OR REPLACE VIEW dwh.v_application_outcomes AS
WITH terminal_events AS (
    SELECT
        application_id,
        event_timestamp,
        event_name AS outcome_status,
        stage_id AS outcome_stage_id,
        stage_name AS outcome_stage_name,
        outcome_category,
        party_type,
        dealer_id,
        ROW_NUMBER() OVER (PARTITION BY application_id ORDER BY event_timestamp DESC) AS rn
    FROM dwh.v_application_events
    WHERE is_terminal = TRUE
      AND event_type = 'STATUS_CHANGE'
)
SELECT
    application_id,
    event_timestamp AS outcome_timestamp,
    outcome_status,
    outcome_stage_id,
    outcome_stage_name,
    outcome_category,
    party_type,
    dealer_id
FROM terminal_events
WHERE rn = 1;

COMMENT ON VIEW dwh.v_application_outcomes IS 'Terminal outcome per application';

-- -----------------------------------------------------------------------------
-- 1.8: Funnel Progress Summary View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_application_funnel_progress...'

CREATE OR REPLACE VIEW dwh.v_application_funnel_progress AS
SELECT
    se.application_id,
    se.party_type,
    se.dealer_id,
    MAX(CASE WHEN se.stage_id = 'DATA_COLLECTION' THEN 1 ELSE 0 END) AS reached_data_collection,
    MAX(CASE WHEN se.stage_id = 'AUTOMATED_CHECKS' THEN 1 ELSE 0 END) AS reached_automated_checks,
    MAX(CASE WHEN se.stage_id = 'KYC_SIGNING' THEN 1 ELSE 0 END) AS reached_kyc_signing,
    MAX(CASE WHEN se.stage_id = 'UNDERWRITING_REVIEW' THEN 1 ELSE 0 END) AS reached_underwriting_review,
    MAX(CASE WHEN se.stage_id = 'ACTIVATION_FUNDING' THEN 1 ELSE 0 END) AS reached_activation_funding,
    MAX(se.stage_order) FILTER (WHERE se.stage_order BETWEEN 0 AND 4) AS max_operational_stage_order,
    MIN(se.first_entry_at) AS first_event_at,
    MAX(se.last_event_at) AS last_event_at,
    COUNT(DISTINCT se.stage_id) AS stages_touched,
    SUM(se.event_count) AS total_events
FROM dwh.v_application_stage_entries se
GROUP BY se.application_id, se.party_type, se.dealer_id;

COMMENT ON VIEW dwh.v_application_funnel_progress IS 'Summary of funnel stages reached per application';

-- -----------------------------------------------------------------------------
-- 1.9: Fact Table (Materialized View)
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.mv_fact_application_funnel...'

CREATE MATERIALIZED VIEW IF NOT EXISTS dwh.mv_fact_application_funnel AS
WITH
application_base AS (
    SELECT
        c.representation_id AS application_id,
        c.submission_date AS submission_dt,
        CASE c.request_type WHEN 'PRIVATE' THEN 'B2C' WHEN 'BUSINESS' THEN 'B2B' ELSE 'UNKNOWN' END AS party_type,
        c.oem_partner_id AS dealer_id,
        COALESCE(c.oem_partner_name, 'Unknown Dealer') AS dealer_name,
        c.country_code,
        c.product_type,
        c.contract_origin,
        c.financing_amount,
        c.purchase_price AS vehicle_price,
        c.down_payment,
        c.monthly_payment,
        DATE_TRUNC('week', c.submission_date)::DATE AS submission_week,
        DATE_TRUNC('month', c.submission_date)::DATE AS submission_month,
        EXTRACT(YEAR FROM c.submission_date)::INT AS submission_year
    FROM ods.contract c
    WHERE c.is_deleted_flg = 0
      AND c.submission_date IS NOT NULL
),
stage_milestones AS (
    SELECT
        application_id,
        MAX(CASE WHEN stage_id = 'AUTOMATED_CHECKS' THEN first_entry_at END) AS stage_1_automated_checks_dt,
        MAX(CASE WHEN stage_id = 'KYC_SIGNING' THEN first_entry_at END) AS stage_2_kyc_signing_dt,
        MAX(CASE WHEN stage_id = 'UNDERWRITING_REVIEW' THEN first_entry_at END) AS stage_3_underwriting_dt,
        MAX(CASE WHEN stage_id = 'ACTIVATION_FUNDING' THEN first_entry_at END) AS stage_4_activation_dt,
        MAX(CASE WHEN stage_id = 'DATA_COLLECTION' THEN first_entry_at END) AS data_collection_dt
    FROM dwh.v_application_stage_entries
    GROUP BY application_id
),
outcome_dates AS (
    SELECT
        application_id,
        MAX(CASE WHEN outcome_status = 'FUNDS_CONFIRMED' THEN outcome_timestamp END) AS funded_dt,
        MAX(CASE WHEN outcome_status = 'DECLINED' THEN outcome_timestamp END) AS auto_rejected_dt,
        MAX(CASE WHEN outcome_status = 'REJECTED' THEN outcome_timestamp END) AS manual_rejected_dt,
        MAX(CASE WHEN outcome_status = 'ARCHIVED' THEN outcome_timestamp END) AS customer_dropoff_dt
    FROM dwh.v_application_outcomes
    GROUP BY application_id
)
SELECT
    ab.application_id,
    ab.submission_dt,
    sm.data_collection_dt,
    sm.stage_1_automated_checks_dt,
    sm.stage_2_kyc_signing_dt,
    sm.stage_3_underwriting_dt,
    sm.stage_4_activation_dt,
    od.funded_dt,
    od.auto_rejected_dt,
    od.manual_rejected_dt,
    od.customer_dropoff_dt,
    CASE
        WHEN od.funded_dt IS NOT NULL THEN 'FUNDED'
        WHEN od.auto_rejected_dt IS NOT NULL THEN 'AUTO_REJECTED'
        WHEN od.manual_rejected_dt IS NOT NULL THEN 'MANUAL_REJECTED'
        WHEN od.customer_dropoff_dt IS NOT NULL THEN 'CUSTOMER_DROPOFF'
        ELSE NULL
    END AS current_outcome,
    CASE
        WHEN od.funded_dt IS NOT NULL THEN 'FUNDED'
        WHEN od.auto_rejected_dt IS NOT NULL THEN 'AUTO_REJECTED'
        WHEN od.manual_rejected_dt IS NOT NULL THEN 'MANUAL_REJECTED'
        WHEN od.customer_dropoff_dt IS NOT NULL THEN 'CUSTOMER_DROPOFF'
        WHEN sm.stage_4_activation_dt IS NOT NULL THEN 'ACTIVATION_FUNDING'
        WHEN sm.stage_3_underwriting_dt IS NOT NULL THEN 'UNDERWRITING_REVIEW'
        WHEN sm.stage_2_kyc_signing_dt IS NOT NULL THEN 'KYC_SIGNING'
        WHEN sm.stage_1_automated_checks_dt IS NOT NULL THEN 'AUTOMATED_CHECKS'
        WHEN sm.data_collection_dt IS NOT NULL THEN 'DATA_COLLECTION'
        ELSE 'DATA_COLLECTION'
    END AS current_stage_id,
    CASE
        WHEN od.funded_dt IS NOT NULL OR od.auto_rejected_dt IS NOT NULL
             OR od.manual_rejected_dt IS NOT NULL OR od.customer_dropoff_dt IS NOT NULL
        THEN TRUE ELSE FALSE
    END AS is_terminal,
    CASE
        WHEN od.funded_dt IS NULL AND od.auto_rejected_dt IS NULL
             AND od.manual_rejected_dt IS NULL AND od.customer_dropoff_dt IS NULL
        THEN TRUE ELSE FALSE
    END AS is_active,
    CASE
        WHEN sm.stage_1_automated_checks_dt IS NOT NULL AND ab.submission_dt IS NOT NULL
        THEN ROUND(EXTRACT(EPOCH FROM sm.stage_1_automated_checks_dt - ab.submission_dt) / 86400.0, 2)
    END AS days_submission_to_stage_1,
    CASE
        WHEN sm.stage_2_kyc_signing_dt IS NOT NULL AND sm.stage_1_automated_checks_dt IS NOT NULL
        THEN ROUND(EXTRACT(EPOCH FROM sm.stage_2_kyc_signing_dt - sm.stage_1_automated_checks_dt) / 86400.0, 2)
    END AS days_stage_1_to_stage_2,
    CASE
        WHEN sm.stage_3_underwriting_dt IS NOT NULL AND sm.stage_2_kyc_signing_dt IS NOT NULL
        THEN ROUND(EXTRACT(EPOCH FROM sm.stage_3_underwriting_dt - sm.stage_2_kyc_signing_dt) / 86400.0, 2)
    END AS days_stage_2_to_stage_3,
    CASE
        WHEN sm.stage_4_activation_dt IS NOT NULL AND sm.stage_3_underwriting_dt IS NOT NULL
        THEN ROUND(EXTRACT(EPOCH FROM sm.stage_4_activation_dt - sm.stage_3_underwriting_dt) / 86400.0, 2)
    END AS days_stage_3_to_stage_4,
    CASE
        WHEN od.funded_dt IS NOT NULL AND sm.stage_4_activation_dt IS NOT NULL
        THEN ROUND(EXTRACT(EPOCH FROM od.funded_dt - sm.stage_4_activation_dt) / 86400.0, 2)
    END AS days_stage_4_to_funded,
    CASE
        WHEN ab.submission_dt IS NOT NULL
        THEN ROUND(EXTRACT(EPOCH FROM (
            COALESCE(od.funded_dt, od.auto_rejected_dt, od.manual_rejected_dt, od.customer_dropoff_dt, CURRENT_TIMESTAMP) - ab.submission_dt
        )) / 86400.0, 2)
    END AS days_total_in_funnel,
    ab.party_type,
    ab.dealer_id,
    ab.dealer_name,
    ab.country_code,
    ab.product_type,
    ab.contract_origin,
    ab.submission_week,
    ab.submission_month,
    ab.submission_year,
    ab.financing_amount,
    ab.vehicle_price,
    ab.down_payment,
    ab.monthly_payment,
    CURRENT_TIMESTAMP AS last_refresh_at
FROM application_base ab
LEFT JOIN stage_milestones sm ON ab.application_id = sm.application_id
LEFT JOIN outcome_dates od ON ab.application_id = od.application_id;

-- Indexes for fact table
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_fact_funnel_app_id ON dwh.mv_fact_application_funnel(application_id);
CREATE INDEX IF NOT EXISTS idx_mv_fact_funnel_submission_dt ON dwh.mv_fact_application_funnel(submission_dt);
CREATE INDEX IF NOT EXISTS idx_mv_fact_funnel_submission_week ON dwh.mv_fact_application_funnel(submission_week);
CREATE INDEX IF NOT EXISTS idx_mv_fact_funnel_party_type ON dwh.mv_fact_application_funnel(party_type);
CREATE INDEX IF NOT EXISTS idx_mv_fact_funnel_dealer_id ON dwh.mv_fact_application_funnel(dealer_id);
CREATE INDEX IF NOT EXISTS idx_mv_fact_funnel_current_stage ON dwh.mv_fact_application_funnel(current_stage_id);
CREATE INDEX IF NOT EXISTS idx_mv_fact_funnel_is_terminal ON dwh.mv_fact_application_funnel(is_terminal);

COMMENT ON MATERIALIZED VIEW dwh.mv_fact_application_funnel IS 'Accumulating snapshot fact table for application funnel analytics';

-- -----------------------------------------------------------------------------
-- 1.10: Fact Table View Wrapper for PowerBI
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_fact_application_funnel...'

CREATE OR REPLACE VIEW dwh.v_fact_application_funnel AS
SELECT
    application_id, submission_dt, data_collection_dt,
    stage_1_automated_checks_dt, stage_2_kyc_signing_dt, stage_3_underwriting_dt, stage_4_activation_dt,
    funded_dt, auto_rejected_dt, manual_rejected_dt, customer_dropoff_dt,
    current_outcome, current_stage_id, is_terminal, is_active,
    days_submission_to_stage_1, days_stage_1_to_stage_2, days_stage_2_to_stage_3,
    days_stage_3_to_stage_4, days_stage_4_to_funded, days_total_in_funnel,
    party_type, dealer_id, dealer_name, country_code, product_type, contract_origin,
    submission_week, submission_month, submission_year,
    financing_amount, vehicle_price, down_payment, monthly_payment, last_refresh_at,
    CASE current_stage_id
        WHEN 'DATA_COLLECTION' THEN 0 WHEN 'AUTOMATED_CHECKS' THEN 1 WHEN 'KYC_SIGNING' THEN 2
        WHEN 'UNDERWRITING_REVIEW' THEN 3 WHEN 'ACTIVATION_FUNDING' THEN 4 WHEN 'FUNDED' THEN 10
        WHEN 'AUTO_REJECTED' THEN 11 WHEN 'MANUAL_REJECTED' THEN 12 WHEN 'CUSTOMER_DROPOFF' THEN 13
        ELSE 99
    END AS current_stage_order,
    CASE current_stage_id
        WHEN 'DATA_COLLECTION' THEN 'Data Collection' WHEN 'AUTOMATED_CHECKS' THEN 'Automated Checks'
        WHEN 'KYC_SIGNING' THEN 'KYC + Signing' WHEN 'UNDERWRITING_REVIEW' THEN 'Underwriting Review'
        WHEN 'ACTIVATION_FUNDING' THEN 'Activation & Funding' WHEN 'FUNDED' THEN 'Funded'
        WHEN 'AUTO_REJECTED' THEN 'Auto-rejected' WHEN 'MANUAL_REJECTED' THEN 'Manual-rejected'
        WHEN 'CUSTOMER_DROPOFF' THEN 'Customer Drop-off' ELSE 'Unknown'
    END AS current_stage_name,
    CASE current_outcome
        WHEN 'FUNDED' THEN 'Funded' WHEN 'AUTO_REJECTED' THEN 'Auto-rejected'
        WHEN 'MANUAL_REJECTED' THEN 'Manual-rejected' WHEN 'CUSTOMER_DROPOFF' THEN 'Customer Drop-off'
        ELSE 'In Progress'
    END AS outcome_display,
    CASE
        WHEN current_outcome IS NOT NULL THEN 'OUTCOME'
        WHEN current_stage_id = 'DATA_COLLECTION' THEN 'PRE_FUNNEL'
        ELSE 'OPERATIONAL'
    END AS stage_category
FROM dwh.mv_fact_application_funnel;

COMMENT ON VIEW dwh.v_fact_application_funnel IS 'View wrapper for fact table with human-readable names for PowerBI';

-- -----------------------------------------------------------------------------
-- 1.11: Phase 1 Refresh Procedures
-- -----------------------------------------------------------------------------

\echo 'Creating Phase 1 refresh procedures...'

CREATE OR REPLACE PROCEDURE dwh.refresh_application_funnel()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_fact_application_funnel;
    RAISE NOTICE 'Application funnel snapshot refreshed at %', CURRENT_TIMESTAMP;
END;
$$;

CREATE OR REPLACE PROCEDURE dwh.refresh_application_funnel_full()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW dwh.mv_fact_application_funnel;
    RAISE NOTICE 'Application funnel snapshot fully refreshed at %', CURRENT_TIMESTAMP;
END;
$$;

\echo 'Phase 1 complete'

-- =============================================================================
-- PHASE 2: CORE METRICS
-- =============================================================================

\echo ''
\echo '>>> PHASE 2: Core Metrics'
\echo ''

-- -----------------------------------------------------------------------------
-- 2.1: Daily Metrics Materialized View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.mv_agg_daily_metrics...'

CREATE MATERIALIZED VIEW IF NOT EXISTS dwh.mv_agg_daily_metrics AS
SELECT
    submission_dt::DATE AS metric_date,
    party_type,
    COUNT(*) AS submitted_count,
    COUNT(CASE WHEN is_active = TRUE THEN 1 END) AS active_count,
    COUNT(funded_dt) AS funded_count,
    COUNT(auto_rejected_dt) + COUNT(manual_rejected_dt) AS rejected_count,
    COUNT(customer_dropoff_dt) AS dropoff_count,
    COUNT(CASE WHEN is_active = TRUE AND current_stage_id = 'AUTOMATED_CHECKS' THEN 1 END) AS count_at_stage_1,
    COUNT(CASE WHEN is_active = TRUE AND current_stage_id = 'KYC_SIGNING' THEN 1 END) AS count_at_stage_2,
    COUNT(CASE WHEN is_active = TRUE AND current_stage_id = 'UNDERWRITING_REVIEW' THEN 1 END) AS count_at_stage_3,
    COUNT(CASE WHEN is_active = TRUE AND current_stage_id = 'ACTIVATION_FUNDING' THEN 1 END) AS count_at_stage_4,
    ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(stage_1_automated_checks_dt), 0), 1) AS stage_1_to_funded,
    ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(stage_2_kyc_signing_dt), 0), 1) AS stage_2_to_funded,
    ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(stage_3_underwriting_dt), 0), 1) AS stage_3_to_funded,
    ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(stage_4_activation_dt), 0), 1) AS stage_4_to_funded,
    ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(*), 0), 1) AS overall_conversion_rate,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_submission_to_stage_1), 1) AS median_days_submission_to_stage_1,
    ROUND(AVG(days_submission_to_stage_1), 1) AS avg_days_submission_to_stage_1,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_stage_1_to_stage_2), 1) AS median_days_stage_1_to_2,
    ROUND(AVG(days_stage_1_to_stage_2), 1) AS avg_days_stage_1_to_2,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_stage_2_to_stage_3), 1) AS median_days_stage_2_to_3,
    ROUND(AVG(days_stage_2_to_stage_3), 1) AS avg_days_stage_2_to_3,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_stage_3_to_stage_4), 1) AS median_days_stage_3_to_4,
    ROUND(AVG(days_stage_3_to_stage_4), 1) AS avg_days_stage_3_to_4,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_total_in_funnel), 1) AS median_days_total,
    ROUND(AVG(days_total_in_funnel), 1) AS avg_days_total
FROM dwh.mv_fact_application_funnel
WHERE submission_dt >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY submission_dt::DATE, party_type;

CREATE UNIQUE INDEX IF NOT EXISTS idx_agg_daily_metrics_pk ON dwh.mv_agg_daily_metrics(metric_date, party_type);

COMMENT ON MATERIALIZED VIEW dwh.mv_agg_daily_metrics IS 'Daily aggregated metrics for funnel analytics dashboard';

-- -----------------------------------------------------------------------------
-- 2.2: PowerBI Daily Metrics View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_powerbi_daily_metrics...'

CREATE OR REPLACE VIEW dwh.v_powerbi_daily_metrics AS
SELECT
    metric_date AS "Date",
    CASE party_type WHEN 'B2C' THEN 'Private' WHEN 'B2B' THEN 'Business' ELSE party_type END AS "Customer Type",
    submitted_count AS "Submitted", active_count AS "Active", funded_count AS "Funded",
    rejected_count AS "Rejected", dropoff_count AS "Dropoff",
    count_at_stage_1 AS "At Automated Checks", count_at_stage_2 AS "At KYC + Signing",
    count_at_stage_3 AS "At Underwriting", count_at_stage_4 AS "At Activation",
    overall_conversion_rate AS "Conversion Rate %",
    100.0 - overall_conversion_rate AS "Loss Rate %",
    stage_1_to_funded AS "Stage 1 to Funded %", stage_2_to_funded AS "Stage 2 to Funded %",
    stage_3_to_funded AS "Stage 3 to Funded %", stage_4_to_funded AS "Stage 4 to Funded %",
    median_days_submission_to_stage_1 AS "Median Days to Stage 1",
    median_days_stage_1_to_2 AS "Median Days Stage 1 to 2",
    median_days_stage_2_to_3 AS "Median Days Stage 2 to 3",
    median_days_stage_3_to_4 AS "Median Days Stage 3 to 4",
    median_days_total AS "Median Days to Fund",
    avg_days_submission_to_stage_1 AS "Avg Days to Stage 1",
    avg_days_stage_1_to_2 AS "Avg Days Stage 1 to 2",
    avg_days_stage_2_to_3 AS "Avg Days Stage 2 to 3",
    avg_days_stage_3_to_4 AS "Avg Days Stage 3 to 4",
    avg_days_total AS "Avg Days to Fund"
FROM dwh.mv_agg_daily_metrics
WHERE metric_date >= CURRENT_DATE - INTERVAL '12 months'
ORDER BY metric_date DESC, "Customer Type";

COMMENT ON VIEW dwh.v_powerbi_daily_metrics IS 'PowerBI-optimized view of daily metrics';

-- -----------------------------------------------------------------------------
-- 2.3: Weekly Cohorts Materialized View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.mv_agg_weekly_cohorts...'

CREATE MATERIALIZED VIEW IF NOT EXISTS dwh.mv_agg_weekly_cohorts AS
SELECT
    submission_week,
    party_type,
    COUNT(*) AS cohort_size,
    SUM(financing_amount) AS cohort_financing_amount,
    COUNT(CASE WHEN funded_dt IS NOT NULL AND days_total_in_funnel <= 7 THEN 1 END) AS funded_7d,
    COUNT(CASE WHEN funded_dt IS NOT NULL AND days_total_in_funnel <= 14 THEN 1 END) AS funded_14d,
    COUNT(CASE WHEN funded_dt IS NOT NULL AND days_total_in_funnel <= 30 THEN 1 END) AS funded_30d,
    COUNT(funded_dt) AS funded_total,
    ROUND(100.0 * COUNT(CASE WHEN funded_dt IS NOT NULL AND days_total_in_funnel <= 7 THEN 1 END) / NULLIF(COUNT(*), 0), 1) AS conversion_7d,
    ROUND(100.0 * COUNT(CASE WHEN funded_dt IS NOT NULL AND days_total_in_funnel <= 14 THEN 1 END) / NULLIF(COUNT(*), 0), 1) AS conversion_14d,
    ROUND(100.0 * COUNT(CASE WHEN funded_dt IS NOT NULL AND days_total_in_funnel <= 30 THEN 1 END) / NULLIF(COUNT(*), 0), 1) AS conversion_30d,
    ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(*), 0), 1) AS final_conversion_rate,
    COUNT(stage_4_activation_dt) AS approved_count,
    COUNT(CASE WHEN stage_4_activation_dt IS NOT NULL AND funded_dt IS NOT NULL THEN 1 END) AS approved_then_funded,
    ROUND(100.0 * COUNT(CASE WHEN stage_4_activation_dt IS NOT NULL AND funded_dt IS NOT NULL THEN 1 END) / NULLIF(COUNT(stage_4_activation_dt), 0), 1) AS post_approval_conversion_rate,
    CURRENT_TIMESTAMP AS last_refresh_at
FROM dwh.mv_fact_application_funnel
WHERE submission_week >= DATE_TRUNC('week', CURRENT_DATE - INTERVAL '12 months')
GROUP BY submission_week, party_type;

CREATE UNIQUE INDEX IF NOT EXISTS idx_agg_cohorts_pk ON dwh.mv_agg_weekly_cohorts(submission_week, party_type);
CREATE INDEX IF NOT EXISTS idx_agg_cohorts_week ON dwh.mv_agg_weekly_cohorts(submission_week DESC);

COMMENT ON MATERIALIZED VIEW dwh.mv_agg_weekly_cohorts IS 'Weekly cohort conversion rates at multiple time horizons';

-- -----------------------------------------------------------------------------
-- 2.4: Stage Duration Thresholds Materialized View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.mv_stage_duration_thresholds...'

CREATE MATERIALIZED VIEW IF NOT EXISTS dwh.mv_stage_duration_thresholds AS
SELECT
    current_stage_id AS stage_id,
    party_type,
    ROUND((PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY days_total_in_funnel))::numeric, 1) AS p75_duration,
    ROUND((PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY days_total_in_funnel))::numeric, 1) AS p90_duration,
    ROUND(AVG(days_total_in_funnel)::numeric, 1) AS avg_duration,
    ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_total_in_funnel))::numeric, 1) AS median_duration,
    COUNT(*) AS sample_size,
    CURRENT_TIMESTAMP AS last_refresh_at
FROM dwh.mv_fact_application_funnel
WHERE is_terminal = TRUE
  AND submission_dt >= CURRENT_DATE - INTERVAL '6 months'
  AND current_stage_id IN ('FUNDED', 'AUTO_REJECTED', 'MANUAL_REJECTED', 'CUSTOMER_DROPOFF')
GROUP BY current_stage_id, party_type
HAVING COUNT(*) >= 30;

CREATE UNIQUE INDEX IF NOT EXISTS idx_stage_thresholds_pk ON dwh.mv_stage_duration_thresholds(stage_id, party_type);

COMMENT ON MATERIALIZED VIEW dwh.mv_stage_duration_thresholds IS 'Percentile-based duration thresholds for stuck application detection';

-- -----------------------------------------------------------------------------
-- 2.5: Stuck Applications View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_stuck_applications...'

CREATE OR REPLACE VIEW dwh.v_stuck_applications AS
SELECT
    f.application_id, f.submission_dt, f.dealer_id, f.dealer_name,
    f.current_stage_id, f.current_stage_name, f.party_type,
    f.days_total_in_funnel AS current_duration,
    t.p75_duration AS threshold_duration,
    f.days_total_in_funnel - t.p75_duration AS days_over_threshold,
    CASE
        WHEN f.days_total_in_funnel > t.p90_duration THEN 'Critical'
        WHEN f.days_total_in_funnel > t.p75_duration THEN 'Warning'
        ELSE 'Normal'
    END AS urgency_level,
    f.financing_amount, f.country_code, f.product_type
FROM dwh.v_fact_application_funnel f
JOIN dwh.mv_stage_duration_thresholds t ON f.current_stage_id = t.stage_id AND f.party_type = t.party_type
WHERE f.is_active = TRUE
  AND f.days_total_in_funnel > t.p75_duration
ORDER BY days_over_threshold DESC;

COMMENT ON VIEW dwh.v_stuck_applications IS 'Active applications exceeding P75 duration threshold';

-- -----------------------------------------------------------------------------
-- 2.6: Phase 2 Refresh Procedures
-- -----------------------------------------------------------------------------

\echo 'Creating Phase 2 refresh procedures...'

CREATE OR REPLACE PROCEDURE dwh.refresh_cohorts_and_thresholds()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_agg_weekly_cohorts;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_stage_duration_thresholds;
    RAISE NOTICE 'Cohort and threshold MVs refreshed at %', CURRENT_TIMESTAMP;
END;
$$;

CREATE OR REPLACE PROCEDURE dwh.refresh_cohorts_and_thresholds_initial()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW dwh.mv_agg_weekly_cohorts;
    REFRESH MATERIALIZED VIEW dwh.mv_stage_duration_thresholds;
    RAISE NOTICE 'Initial cohort and threshold MVs refresh completed at %', CURRENT_TIMESTAMP;
END;
$$;

-- -----------------------------------------------------------------------------
-- 2.7: Executive Dashboard View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_powerbi_funnel_executive...'

CREATE OR REPLACE VIEW dwh.v_powerbi_funnel_executive AS
-- Last 7 Days - All Customers
SELECT '7d' AS metric_period, 'All' AS customer_segment, COUNT(*) AS applications_submitted, COUNT(funded_dt) AS applications_funded,
    ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(*), 0), 1) AS overall_conversion_rate_pct,
    ROUND(100.0 * COUNT(auto_rejected_dt) / NULLIF(COUNT(*), 0), 1) AS auto_rejection_rate_pct,
    ROUND(100.0 * COUNT(manual_rejected_dt) / NULLIF(COUNT(*), 0), 1) AS manual_rejection_rate_pct,
    ROUND(100.0 * COUNT(customer_dropoff_dt) / NULLIF(COUNT(*), 0), 1) AS customer_dropoff_rate_pct,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_total_in_funnel), 1) AS median_days_to_fund,
    ROUND(AVG(days_total_in_funnel), 1) AS avg_days_to_fund,
    SUM(CASE WHEN funded_dt IS NOT NULL THEN financing_amount ELSE 0 END) AS total_financing_funded
FROM dwh.v_fact_application_funnel WHERE submission_dt >= CURRENT_DATE - INTERVAL '7 days'
UNION ALL
-- Last 7 Days - By Segment
SELECT '7d', CASE WHEN party_type = 'B2C' THEN 'Private (B2C)' WHEN party_type = 'B2B' THEN 'Business (B2B)' ELSE party_type END, COUNT(*), COUNT(funded_dt),
    ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(*), 0), 1), ROUND(100.0 * COUNT(auto_rejected_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(manual_rejected_dt) / NULLIF(COUNT(*), 0), 1), ROUND(100.0 * COUNT(customer_dropoff_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_total_in_funnel), 1), ROUND(AVG(days_total_in_funnel), 1),
    SUM(CASE WHEN funded_dt IS NOT NULL THEN financing_amount ELSE 0 END)
FROM dwh.v_fact_application_funnel WHERE submission_dt >= CURRENT_DATE - INTERVAL '7 days' GROUP BY party_type
UNION ALL
-- Last 30 Days - All Customers
SELECT '30d', 'All', COUNT(*), COUNT(funded_dt), ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(auto_rejected_dt) / NULLIF(COUNT(*), 0), 1), ROUND(100.0 * COUNT(manual_rejected_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(customer_dropoff_dt) / NULLIF(COUNT(*), 0), 1), ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_total_in_funnel), 1),
    ROUND(AVG(days_total_in_funnel), 1), SUM(CASE WHEN funded_dt IS NOT NULL THEN financing_amount ELSE 0 END)
FROM dwh.v_fact_application_funnel WHERE submission_dt >= CURRENT_DATE - INTERVAL '30 days'
UNION ALL
-- Last 30 Days - By Segment
SELECT '30d', CASE WHEN party_type = 'B2C' THEN 'Private (B2C)' WHEN party_type = 'B2B' THEN 'Business (B2B)' ELSE party_type END, COUNT(*), COUNT(funded_dt),
    ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(*), 0), 1), ROUND(100.0 * COUNT(auto_rejected_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(manual_rejected_dt) / NULLIF(COUNT(*), 0), 1), ROUND(100.0 * COUNT(customer_dropoff_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_total_in_funnel), 1), ROUND(AVG(days_total_in_funnel), 1),
    SUM(CASE WHEN funded_dt IS NOT NULL THEN financing_amount ELSE 0 END)
FROM dwh.v_fact_application_funnel WHERE submission_dt >= CURRENT_DATE - INTERVAL '30 days' GROUP BY party_type
UNION ALL
-- Last 90 Days - All Customers
SELECT '90d', 'All', COUNT(*), COUNT(funded_dt), ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(auto_rejected_dt) / NULLIF(COUNT(*), 0), 1), ROUND(100.0 * COUNT(manual_rejected_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(customer_dropoff_dt) / NULLIF(COUNT(*), 0), 1), ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_total_in_funnel), 1),
    ROUND(AVG(days_total_in_funnel), 1), SUM(CASE WHEN funded_dt IS NOT NULL THEN financing_amount ELSE 0 END)
FROM dwh.v_fact_application_funnel WHERE submission_dt >= CURRENT_DATE - INTERVAL '90 days'
UNION ALL
-- Last 90 Days - By Segment
SELECT '90d', CASE WHEN party_type = 'B2C' THEN 'Private (B2C)' WHEN party_type = 'B2B' THEN 'Business (B2B)' ELSE party_type END, COUNT(*), COUNT(funded_dt),
    ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(*), 0), 1), ROUND(100.0 * COUNT(auto_rejected_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(manual_rejected_dt) / NULLIF(COUNT(*), 0), 1), ROUND(100.0 * COUNT(customer_dropoff_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_total_in_funnel), 1), ROUND(AVG(days_total_in_funnel), 1),
    SUM(CASE WHEN funded_dt IS NOT NULL THEN financing_amount ELSE 0 END)
FROM dwh.v_fact_application_funnel WHERE submission_dt >= CURRENT_DATE - INTERVAL '90 days' GROUP BY party_type
UNION ALL
-- Year to Date - All Customers
SELECT 'YTD', 'All', COUNT(*), COUNT(funded_dt), ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(auto_rejected_dt) / NULLIF(COUNT(*), 0), 1), ROUND(100.0 * COUNT(manual_rejected_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(customer_dropoff_dt) / NULLIF(COUNT(*), 0), 1), ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_total_in_funnel), 1),
    ROUND(AVG(days_total_in_funnel), 1), SUM(CASE WHEN funded_dt IS NOT NULL THEN financing_amount ELSE 0 END)
FROM dwh.v_fact_application_funnel WHERE submission_dt >= DATE_TRUNC('year', CURRENT_DATE)
UNION ALL
-- Year to Date - By Segment
SELECT 'YTD', CASE WHEN party_type = 'B2C' THEN 'Private (B2C)' WHEN party_type = 'B2B' THEN 'Business (B2B)' ELSE party_type END, COUNT(*), COUNT(funded_dt),
    ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(*), 0), 1), ROUND(100.0 * COUNT(auto_rejected_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(100.0 * COUNT(manual_rejected_dt) / NULLIF(COUNT(*), 0), 1), ROUND(100.0 * COUNT(customer_dropoff_dt) / NULLIF(COUNT(*), 0), 1),
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_total_in_funnel), 1), ROUND(AVG(days_total_in_funnel), 1),
    SUM(CASE WHEN funded_dt IS NOT NULL THEN financing_amount ELSE 0 END)
FROM dwh.v_fact_application_funnel WHERE submission_dt >= DATE_TRUNC('year', CURRENT_DATE) GROUP BY party_type;

COMMENT ON VIEW dwh.v_powerbi_funnel_executive IS 'Executive dashboard view: Funnel KPIs at multiple time horizons';

-- -----------------------------------------------------------------------------
-- 2.8: Operations Dashboard View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_powerbi_funnel_operations...'

CREATE OR REPLACE VIEW dwh.v_powerbi_funnel_operations AS
-- Current Volume by Stage
SELECT 'Current Volume' AS report_type, current_stage_name AS stage_name, party_type AS customer_type, COUNT(*) AS application_count,
    SUM(financing_amount) AS financing_at_risk, ROUND(AVG(days_total_in_funnel), 1) AS avg_days_in_stage,
    NULL::TEXT AS exit_type, NULL::INTEGER AS exit_count, NULL::NUMERIC AS exit_rate_pct,
    NULL::INTEGER AS stuck_count, NULL::INTEGER AS critical_count, NULL::INTEGER AS warning_count,
    NULL::TEXT AS dealer_name, NULL::NUMERIC AS days_over_threshold
FROM dwh.v_fact_application_funnel WHERE is_active = TRUE GROUP BY current_stage_name, party_type
UNION ALL
-- Exit Branches
SELECT 'Exit Branches', COALESCE(
    CASE current_stage_id WHEN 'AUTO_REJECTED' THEN 'Auto-Rejected' WHEN 'MANUAL_REJECTED' THEN 'Manual-Rejected'
        WHEN 'CUSTOMER_DROPOFF' THEN 'Customer Drop-off' WHEN 'FUNDED' THEN 'Funded' ELSE current_stage_name END, 'Unknown'),
    party_type, COUNT(*), SUM(financing_amount), ROUND(AVG(days_total_in_funnel), 1),
    CASE WHEN current_stage_id = 'AUTO_REJECTED' THEN 'Auto-rejected' WHEN current_stage_id = 'MANUAL_REJECTED' THEN 'Manual-rejected'
        WHEN current_stage_id = 'CUSTOMER_DROPOFF' THEN 'Customer Drop-off' WHEN current_stage_id = 'FUNDED' THEN 'Funded' ELSE 'Active' END,
    COUNT(*), ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY party_type), 1),
    NULL, NULL, NULL, NULL, NULL
FROM dwh.v_fact_application_funnel WHERE is_terminal = TRUE GROUP BY current_stage_id, current_stage_name, party_type
UNION ALL
-- Stuck Applications Summary
SELECT 'Stuck Applications', current_stage_name, party_type, COUNT(*), SUM(financing_amount), ROUND(AVG(current_duration), 1),
    NULL, NULL, NULL, COUNT(*), COUNT(CASE WHEN urgency_level = 'Critical' THEN 1 END), COUNT(CASE WHEN urgency_level = 'Warning' THEN 1 END),
    NULL, ROUND(AVG(days_over_threshold), 1)
FROM dwh.v_stuck_applications GROUP BY current_stage_name, party_type
UNION ALL
-- Stuck Applications Detail (Top 100)
SELECT 'Stuck Applications Detail', current_stage_name, party_type, 1, financing_amount, current_duration,
    urgency_level, NULL, NULL, NULL, NULL, NULL, dealer_name, days_over_threshold
FROM dwh.v_stuck_applications ORDER BY days_over_threshold DESC LIMIT 100;

COMMENT ON VIEW dwh.v_powerbi_funnel_operations IS 'Operations dashboard view: Current volume, exit branches, stuck apps';

\echo 'Phase 2 complete'

-- =============================================================================
-- PHASE 3: LOSS ANALYSIS
-- =============================================================================

\echo ''
\echo '>>> PHASE 3: Loss Analysis'
\echo ''

-- -----------------------------------------------------------------------------
-- 3.1: Rejection Phrase Dimension Table
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.dim_rejection_phrase...'

CREATE TABLE IF NOT EXISTS dwh.dim_rejection_phrase (
    phrase_id SERIAL PRIMARY KEY,
    phrase_pattern VARCHAR(200) NOT NULL,
    phrase_category VARCHAR(50) NOT NULL,
    phrase_subcategory VARCHAR(50),
    display_label VARCHAR(100),
    sort_order INT DEFAULT 100,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_phrase_pattern_format CHECK (phrase_pattern LIKE '%\%%')
);

CREATE INDEX IF NOT EXISTS idx_dim_rejection_phrase_active ON dwh.dim_rejection_phrase(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_dim_rejection_phrase_category ON dwh.dim_rejection_phrase(phrase_category);

COMMENT ON TABLE dwh.dim_rejection_phrase IS 'Rejection reason phrase patterns for extracting categories from free-text notes';

-- Populate phrase patterns
TRUNCATE TABLE dwh.dim_rejection_phrase RESTART IDENTITY CASCADE;

INSERT INTO dwh.dim_rejection_phrase (phrase_pattern, phrase_category, phrase_subcategory, display_label, sort_order) VALUES
('%crif red%', 'Credit Score Issues', 'CRIF Red', 'CRIF Red Score', 1),
('%crif yellow%', 'Credit Score Issues', 'CRIF Yellow', 'CRIF Yellow Score', 2),
('%crif gelb%', 'Credit Score Issues', 'CRIF Yellow', 'CRIF Gelb (Yellow)', 3),
('%intrum -%', 'Credit Score Issues', 'Intrum Negative', 'Intrum Negative Score', 4),
('%intrum negative%', 'Credit Score Issues', 'Intrum Negative', 'Intrum Negative', 5),
('%negative dscr%', 'Insufficient Income', 'Negative DSCR', 'Negative DSCR', 10),
('%dscr ungenügend%', 'Insufficient Income', 'Negative DSCR', 'DSCR ungenügend', 11),
('%dscr insufficient%', 'Insufficient Income', 'Negative DSCR', 'DSCR Insufficient', 12),
('%open verlustschein%', 'Debt Enforcement', 'Verlustschein', 'Open Verlustschein', 20),
('%verlustschein offen%', 'Debt Enforcement', 'Verlustschein', 'Verlustschein offen', 21),
('%debt enforcement%', 'Debt Enforcement', 'Debt Collection', 'Debt Enforcement', 22),
('%debt collection%', 'Debt Enforcement', 'Debt Collection', 'Debt Collection Issues', 23),
('%betreibung%', 'Debt Enforcement', 'Debt Collection', 'Betreibung', 24),
('%l permit%', 'Permit Issues', 'Residence Permit', 'L Permit (temporary)', 30),
('%residence permit%', 'Permit Issues', 'Residence Permit', 'Residence Permit Issues', 31),
('%aufenthaltsbewilligung%', 'Permit Issues', 'Residence Permit', 'Aufenthaltsbewilligung', 32),
('%fake payslip%', 'Document Issues', 'Fraudulent Documents', 'Fake Payslips', 40),
('%fake document%', 'Document Issues', 'Fraudulent Documents', 'Fake Documents', 41),
('%gefälscht%', 'Document Issues', 'Fraudulent Documents', 'Gefälscht (forged)', 42),
('%falsified%', 'Document Issues', 'Fraudulent Documents', 'Falsified Documents', 43),
('%rental company%', 'Industry Restrictions', 'Car Rental', 'Car Rental Company', 50),
('%renting company%', 'Industry Restrictions', 'Car Rental', 'Renting Company', 51),
('%autovermietung%', 'Industry Restrictions', 'Car Rental', 'Autovermietung', 52),
('%negative equity%', 'Financial Issues', 'Negative Equity', 'Company Negative Equity', 60),
('%überschuldung%', 'Financial Issues', 'Over-Indebtedness', 'Überschuldung', 61),
('%insolvency%', 'Financial Issues', 'Insolvency', 'Insolvency Risk', 62),
('%bawag reject%', 'Partner Rejection', 'BAWAG', 'Rejected by BAWAG', 70),
('%bawag declined%', 'Partner Rejection', 'BAWAG', 'Declined by BAWAG', 71),
('%bawag ablehnung%', 'Partner Rejection', 'BAWAG', 'BAWAG Ablehnung', 72),
('%age check%', 'Eligibility Issues', 'Age', 'Age Requirement Not Met', 80),
('%too young%', 'Eligibility Issues', 'Age', 'Applicant Too Young', 81),
('%zu jung%', 'Eligibility Issues', 'Age', 'Zu jung (too young)', 82);

\echo 'Created dwh.dim_rejection_phrase with 32 patterns'

-- -----------------------------------------------------------------------------
-- 3.2: Rejection Reasons Extraction View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_rejection_reasons...'

CREATE OR REPLACE VIEW dwh.v_rejection_reasons AS
WITH latest_rejection_note AS (
    SELECT n.contract_id AS application_id, n.content, n.created_at AS note_date, c.status, c.state
    FROM ods.contract_notes_sst n
    JOIN ods.contract c ON n.contract_id = c.representation_id
    WHERE n.is_deleted_flg = 0 AND c.status IN ('REJECTED', 'DECLINED')
      AND n.created_at = (SELECT MAX(n2.created_at) FROM ods.contract_notes_sst n2 WHERE n2.contract_id = n.contract_id AND n2.is_deleted_flg = 0)
),
rejection_notes AS (
    SELECT * FROM latest_rejection_note
    WHERE LOWER(content) LIKE '%reject%' OR LOWER(content) LIKE '%declined%' OR LOWER(content) LIKE '%ablehnung%' OR LOWER(content) LIKE '%crif%' OR LOWER(content) LIKE '%dscr%'
),
phrase_matches AS (
    SELECT rn.application_id, rn.note_date, rn.content, rn.status, p.phrase_category, p.phrase_subcategory, p.display_label, p.sort_order
    FROM rejection_notes rn
    CROSS JOIN dwh.dim_rejection_phrase p
    WHERE p.is_active = TRUE AND LOWER(rn.content) LIKE LOWER(p.phrase_pattern)
)
SELECT application_id, MAX(note_date) AS latest_rejection_note_date,
    MAX(CASE WHEN status = 'DECLINED' THEN 'Auto-Rejected' WHEN status = 'REJECTED' THEN 'Manual-Rejected' ELSE 'Other' END) AS rejection_type,
    STRING_AGG(DISTINCT phrase_category, '; ' ORDER BY phrase_category) AS rejection_categories,
    STRING_AGG(DISTINCT display_label, '; ' ORDER BY display_label) AS rejection_reasons,
    COUNT(DISTINCT phrase_category) AS reason_count,
    STRING_AGG(DISTINCT SUBSTRING(content, 1, 200), ' || ') AS note_excerpts
FROM phrase_matches GROUP BY application_id;

COMMENT ON VIEW dwh.v_rejection_reasons IS 'Extracted rejection reason phrases per application';

-- -----------------------------------------------------------------------------
-- 3.3: Rejection Summary View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_rejection_summary...'

CREATE OR REPLACE VIEW dwh.v_rejection_summary AS
WITH all_rejections AS (
    SELECT f.application_id, f.submission_dt, f.party_type, f.current_stage_id, f.current_stage_name,
        CASE WHEN f.auto_rejected_dt IS NOT NULL THEN 'Auto-Rejected' WHEN f.manual_rejected_dt IS NOT NULL THEN 'Manual-Rejected' ELSE 'Other' END AS rejection_type
    FROM dwh.mv_fact_application_funnel f WHERE f.current_stage_id IN ('AUTO_REJECTED', 'MANUAL_REJECTED')
),
rejections_with_reasons AS (
    SELECT ar.*, rr.rejection_categories, rr.rejection_reasons, rr.reason_count,
        CASE WHEN rr.application_id IS NULL THEN 'Unknown' ELSE rr.rejection_categories END AS category_with_unknown
    FROM all_rejections ar LEFT JOIN dwh.v_rejection_reasons rr ON ar.application_id = rr.application_id
)
SELECT rejection_type, party_type, COUNT(*) AS total_rejections, COUNT(rejection_categories) AS rejections_with_reasons,
    COUNT(*) - COUNT(rejection_categories) AS rejections_unknown, ROUND(100.0 * COUNT(rejection_categories) / NULLIF(COUNT(*), 0), 2) AS coverage_pct,
    MODE() WITHIN GROUP (ORDER BY category_with_unknown) AS most_common_category
FROM rejections_with_reasons WHERE submission_dt >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY rejection_type, party_type ORDER BY rejection_type, party_type;

COMMENT ON VIEW dwh.v_rejection_summary IS 'Summary of rejection coverage and most common categories';

-- -----------------------------------------------------------------------------
-- 3.4: Drop-off Reasons View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_dropoff_reasons...'

CREATE OR REPLACE VIEW dwh.v_dropoff_reasons AS
SELECT f.application_id, f.submission_dt, f.party_type, f.dealer_id, f.dealer_name,
    CASE
        WHEN LOWER(n.content) LIKE '%customer%cancel%' OR LOWER(n.content) LIKE '%kunde%storniert%' THEN 'Customer-Cancelled'
        WHEN LOWER(n.content) LIKE '%customer%cancell%' OR LOWER(n.content) LIKE '%kunde%abgesagt%' THEN 'Customer-Cancelled'
        WHEN LOWER(n.content) LIKE '%expired%' OR LOWER(n.content) LIKE '%abgelaufen%' THEN 'Expired'
        WHEN LOWER(n.content) LIKE '%withdrawn%' OR LOWER(n.content) LIKE '%zurückgezogen%' THEN 'Withdrawn'
        WHEN LOWER(n.content) LIKE '%withdraw%' OR LOWER(n.content) LIKE '%zuruckgezogen%' THEN 'Withdrawn'
        ELSE 'Customer-Abandoned'
    END AS dropoff_category,
    LEFT(n.content, 500) AS dropoff_note_excerpt, n.created_at AS latest_note_date, f.days_total_in_funnel
FROM dwh.mv_fact_application_funnel f
LEFT JOIN ods.contract_notes_sst n ON f.application_id = n.contract_id AND n.is_deleted_flg = 0
    AND n.created_at = (SELECT MAX(n2.created_at) FROM ods.contract_notes_sst n2 WHERE n2.contract_id = f.application_id AND n2.is_deleted_flg = 0)
WHERE f.current_stage_id = 'CUSTOMER_DROPOFF';

COMMENT ON VIEW dwh.v_dropoff_reasons IS 'Drop-off categorization with raw note excerpts';

-- -----------------------------------------------------------------------------
-- 3.5: Post-Approval Drop-offs View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_post_approval_dropoffs...'

CREATE OR REPLACE VIEW dwh.v_post_approval_dropoffs AS
SELECT f.application_id, f.submission_dt, f.stage_4_activation_dt AS approval_dt,
    CURRENT_DATE - f.stage_4_activation_dt AS days_since_approval,
    f.party_type, f.dealer_id, f.dealer_name, f.financing_amount,
    n.content AS dropoff_note, n.created_at AS note_date
FROM dwh.mv_fact_application_funnel f
LEFT JOIN ods.contract_notes_sst n ON f.application_id = n.contract_id AND n.is_deleted_flg = 0
    AND n.created_at = (SELECT MAX(n2.created_at) FROM ods.contract_notes_sst n2 WHERE n2.contract_id = f.application_id AND n2.is_deleted_flg = 0)
WHERE f.stage_4_activation_dt IS NOT NULL AND f.funded_dt IS NULL
  AND f.current_stage_id IN ('CUSTOMER_DROPOFF', 'MANUAL_REJECTED')
ORDER BY days_since_approval DESC;

COMMENT ON VIEW dwh.v_post_approval_dropoffs IS 'Post-approval drop-offs: applications approved but not funded';

-- -----------------------------------------------------------------------------
-- 3.6: Stuck Responsibility View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_stuck_responsibility...'

CREATE OR REPLACE VIEW dwh.v_stuck_responsibility AS
SELECT s.application_id, s.submission_dt, s.dealer_id, s.dealer_name, s.current_stage_id, s.current_stage_name,
    s.party_type, s.current_duration, s.threshold_duration, s.days_over_threshold, s.urgency_level, s.financing_amount,
    CASE
        WHEN s.current_stage_id = 'KYC_SIGNING' THEN 'Customer-Pending'
        WHEN s.current_stage_id = 'UNDERWRITING_REVIEW' THEN 'Underwriter-Pending'
        WHEN s.current_stage_id = 'ACTIVATION_FUNDING' THEN 'Mixed'
        WHEN s.current_stage_id = 'AUTOMATED_CHECKS' THEN 'System'
        ELSE 'Unknown'
    END AS responsible_party,
    CASE
        WHEN s.current_stage_id = 'KYC_SIGNING' THEN 'Customer needs to complete KYC verification or sign contract'
        WHEN s.current_stage_id = 'UNDERWRITING_REVIEW' THEN 'Underwriter needs to review documents and make decision'
        WHEN s.current_stage_id = 'ACTIVATION_FUNDING' THEN 'Multiple dependencies: asset delivery, dealer, customer, funding'
        WHEN s.current_stage_id = 'AUTOMATED_CHECKS' THEN 'Waiting for automated credit checks to complete'
        ELSE 'Unable to determine from current stage'
    END AS responsibility_reason
FROM dwh.v_stuck_applications s;

COMMENT ON VIEW dwh.v_stuck_responsibility IS 'Stuck applications with responsible party attribution';

-- -----------------------------------------------------------------------------
-- 3.7: Stuck Responsibility Summary View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_stuck_responsibility_summary...'

CREATE OR REPLACE VIEW dwh.v_stuck_responsibility_summary AS
SELECT responsible_party, urgency_level, party_type, COUNT(*) AS stuck_count, SUM(financing_amount) AS financing_at_risk,
    AVG(days_over_threshold) AS avg_days_over_threshold, MAX(days_over_threshold) AS max_days_over_threshold
FROM dwh.v_stuck_responsibility
GROUP BY responsible_party, urgency_level, party_type
ORDER BY CASE urgency_level WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 END, financing_at_risk DESC;

COMMENT ON VIEW dwh.v_stuck_responsibility_summary IS 'Dashboard-ready summary of stuck applications by responsible party';

-- -----------------------------------------------------------------------------
-- 3.8: Loss Metrics Materialized View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.mv_agg_loss_metrics...'

CREATE MATERIALIZED VIEW IF NOT EXISTS dwh.mv_agg_loss_metrics AS
-- Rejections
SELECT DATE_TRUNC('week', f.submission_dt)::DATE AS submission_week, f.party_type,
    CASE WHEN f.current_stage_id = 'AUTO_REJECTED' THEN 'Auto-Rejected' WHEN f.current_stage_id = 'MANUAL_REJECTED' THEN 'Manual-Rejected' END AS loss_type,
    COALESCE(r.rejection_categories, 'Unknown') AS loss_category, COUNT(*) AS loss_count,
    COUNT(CASE WHEN r.rejection_categories IS NOT NULL AND r.rejection_categories != 'Unknown' THEN 1 END) AS with_reason_count,
    SUM(f.financing_amount) AS financing_lost
FROM dwh.mv_fact_application_funnel f
LEFT JOIN dwh.v_rejection_reasons r ON f.application_id = r.application_id
WHERE f.current_stage_id IN ('AUTO_REJECTED', 'MANUAL_REJECTED') AND f.submission_dt >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY DATE_TRUNC('week', f.submission_dt)::DATE, f.party_type, f.current_stage_id, r.rejection_categories
UNION ALL
-- Drop-offs
SELECT DATE_TRUNC('week', f.submission_dt)::DATE, f.party_type, 'Customer-Dropoff', d.dropoff_category, COUNT(*),
    COUNT(CASE WHEN d.dropoff_category IS NOT NULL AND d.dropoff_category != 'Unknown' THEN 1 END), SUM(f.financing_amount)
FROM dwh.mv_fact_application_funnel f
LEFT JOIN dwh.v_dropoff_reasons d ON f.application_id = d.application_id
WHERE f.current_stage_id = 'CUSTOMER_DROPOFF' AND f.submission_dt >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY DATE_TRUNC('week', f.submission_dt)::DATE, f.party_type, d.dropoff_category;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_agg_loss_metrics_grain ON dwh.mv_agg_loss_metrics(submission_week, party_type, loss_type, loss_category);
CREATE INDEX IF NOT EXISTS idx_mv_agg_loss_metrics_week ON dwh.mv_agg_loss_metrics(submission_week);

COMMENT ON MATERIALIZED VIEW dwh.mv_agg_loss_metrics IS 'Pre-aggregated loss counts by type and category';

-- -----------------------------------------------------------------------------
-- 3.9: Loss Analysis Dashboard View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_powerbi_loss_analysis...'

CREATE OR REPLACE VIEW dwh.v_powerbi_loss_analysis AS
-- Rejection Summary 30d
SELECT '30d' AS time_horizon, 'All' AS customer_segment, 'Rejection Summary' AS report_type, loss_type AS metric_label, SUM(loss_count) AS metric_value,
    ROUND(100.0 * SUM(loss_count) / SUM(SUM(loss_count)) OVER (), 1) AS metric_rate, SUM(financing_lost) AS financing_impact
FROM dwh.mv_agg_loss_metrics WHERE submission_week >= CURRENT_DATE - INTERVAL '30 days' AND loss_type IN ('Auto-Rejected', 'Manual-Rejected') GROUP BY loss_type
UNION ALL
SELECT '30d', CASE WHEN party_type = 'B2C' THEN 'Private (B2C)' WHEN party_type = 'B2B' THEN 'Business (B2B)' ELSE party_type END, 'Rejection Summary', loss_type, SUM(loss_count),
    ROUND(100.0 * SUM(loss_count) / NULLIF(SUM(SUM(loss_count)) OVER (PARTITION BY party_type), 0), 1), SUM(financing_lost)
FROM dwh.mv_agg_loss_metrics WHERE submission_week >= CURRENT_DATE - INTERVAL '30 days' AND loss_type IN ('Auto-Rejected', 'Manual-Rejected') GROUP BY party_type, loss_type
UNION ALL
-- Rejection Reasons 30d
SELECT '30d', 'All', 'Rejection Reasons', loss_category, SUM(loss_count), ROUND(100.0 * SUM(loss_count) / SUM(SUM(loss_count)) OVER (), 1), SUM(financing_lost)
FROM dwh.mv_agg_loss_metrics WHERE submission_week >= CURRENT_DATE - INTERVAL '30 days' AND loss_type IN ('Auto-Rejected', 'Manual-Rejected') GROUP BY loss_category
UNION ALL
SELECT '30d', CASE WHEN party_type = 'B2C' THEN 'Private (B2C)' ELSE 'Business (B2B)' END, 'Rejection Reasons', loss_category, SUM(loss_count),
    ROUND(100.0 * SUM(loss_count) / NULLIF(SUM(SUM(loss_count)) OVER (PARTITION BY party_type), 0), 1), SUM(financing_lost)
FROM dwh.mv_agg_loss_metrics WHERE submission_week >= CURRENT_DATE - INTERVAL '30 days' AND loss_type IN ('Auto-Rejected', 'Manual-Rejected') GROUP BY party_type, loss_category
UNION ALL
-- Drop-off Summary 30d
SELECT '30d', 'All', 'Drop-off Summary', loss_category, SUM(loss_count), ROUND(100.0 * SUM(loss_count) / SUM(SUM(loss_count)) OVER (), 1), SUM(financing_lost)
FROM dwh.mv_agg_loss_metrics WHERE submission_week >= CURRENT_DATE - INTERVAL '30 days' AND loss_type = 'Customer-Dropoff' GROUP BY loss_category
UNION ALL
SELECT '30d', CASE WHEN party_type = 'B2C' THEN 'Private (B2C)' ELSE 'Business (B2B)' END, 'Drop-off Summary', loss_category, SUM(loss_count),
    ROUND(100.0 * SUM(loss_count) / NULLIF(SUM(SUM(loss_count)) OVER (PARTITION BY party_type), 0), 1), SUM(financing_lost)
FROM dwh.mv_agg_loss_metrics WHERE submission_week >= CURRENT_DATE - INTERVAL '30 days' AND loss_type = 'Customer-Dropoff' GROUP BY party_type, loss_category
UNION ALL
-- Responsibility (Current)
SELECT 'Current', 'All', 'Responsibility', responsible_party || ' - ' || urgency_level, stuck_count,
    ROUND(100.0 * stuck_count / SUM(stuck_count) OVER (), 1), financing_at_risk
FROM dwh.v_stuck_responsibility_summary
UNION ALL
SELECT 'Current', CASE WHEN party_type = 'B2C' THEN 'Private (B2C)' ELSE 'Business (B2B)' END, 'Responsibility', responsible_party || ' - ' || urgency_level, stuck_count,
    ROUND(100.0 * stuck_count / NULLIF(SUM(stuck_count) OVER (PARTITION BY party_type), 0), 1), financing_at_risk
FROM dwh.v_stuck_responsibility_summary;

COMMENT ON VIEW dwh.v_powerbi_loss_analysis IS 'Unified loss analysis dashboard view';

-- -----------------------------------------------------------------------------
-- 3.10: Loss Metrics Refresh Procedure
-- -----------------------------------------------------------------------------

\echo 'Creating Phase 3 refresh procedure...'

CREATE OR REPLACE PROCEDURE dwh.refresh_loss_metrics()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_agg_loss_metrics;
    RAISE NOTICE 'Loss metrics refreshed at %', CURRENT_TIMESTAMP;
END;
$$;

\echo 'Phase 3 complete'

-- =============================================================================
-- PHASE 4: DEALER PERFORMANCE
-- =============================================================================

\echo ''
\echo '>>> PHASE 4: Dealer Performance'
\echo ''

-- -----------------------------------------------------------------------------
-- 4.1: Dealer Metrics Materialized View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.mv_agg_dealer_metrics...'

CREATE MATERIALIZED VIEW IF NOT EXISTS dwh.mv_agg_dealer_metrics AS
SELECT dealer_id, dealer_name, DATE_TRUNC('week', submission_dt)::DATE AS submission_week, party_type,
    COUNT(*) AS application_count, COUNT(funded_dt) AS funded_count,
    SUM(financing_amount) AS total_financing, SUM(CASE WHEN funded_dt IS NOT NULL THEN financing_amount END) AS funded_financing,
    ROUND(100.0 * COUNT(funded_dt) / NULLIF(COUNT(*), 0), 1) AS conversion_rate
FROM dwh.mv_fact_application_funnel
WHERE submission_dt >= CURRENT_DATE - INTERVAL '12 months' AND dealer_id IS NOT NULL
GROUP BY dealer_id, dealer_name, DATE_TRUNC('week', submission_dt)::DATE, party_type;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_agg_dealer_metrics_grain ON dwh.mv_agg_dealer_metrics(dealer_id, submission_week, party_type);
CREATE INDEX IF NOT EXISTS idx_mv_agg_dealer_metrics_week ON dwh.mv_agg_dealer_metrics(submission_week);

COMMENT ON MATERIALIZED VIEW dwh.mv_agg_dealer_metrics IS 'Pre-aggregated dealer performance metrics by week and segment';

-- -----------------------------------------------------------------------------
-- 4.2: Dealer Performance Dashboard View
-- -----------------------------------------------------------------------------

\echo 'Creating dwh.v_powerbi_dealer_performance...'

CREATE OR REPLACE VIEW dwh.v_powerbi_dealer_performance AS
-- Top 10 by Volume - 30d All
WITH ranked AS (
    SELECT '30d' AS time_horizon, 'All' AS party_type_filter, dealer_name, SUM(application_count) AS application_count, SUM(funded_count) AS funded_count,
        SUM(funded_financing) AS funded_financing, ROUND(100.0 * SUM(funded_count) / NULLIF(SUM(application_count), 0), 1) AS conversion_rate,
        RANK() OVER (ORDER BY SUM(funded_financing) DESC) AS rank_position
    FROM dwh.mv_agg_dealer_metrics WHERE submission_week >= CURRENT_DATE - INTERVAL '30 days' GROUP BY dealer_name
)
SELECT 'Top 10 by Volume' AS report_type, time_horizon, party_type_filter, rank_position, dealer_name, application_count, funded_count, funded_financing, conversion_rate
FROM ranked WHERE rank_position <= 10
UNION ALL
-- Top 10 by Volume - 30d B2C
WITH ranked AS (
    SELECT '30d', 'B2C', dealer_name, SUM(application_count), SUM(funded_count), SUM(funded_financing), ROUND(100.0 * SUM(funded_count) / NULLIF(SUM(application_count), 0), 1),
        RANK() OVER (ORDER BY SUM(funded_financing) DESC)
    FROM dwh.mv_agg_dealer_metrics WHERE submission_week >= CURRENT_DATE - INTERVAL '30 days' AND party_type = 'B2C' GROUP BY dealer_name
)
SELECT 'Top 10 by Volume', time_horizon, party_type_filter, rank_position, dealer_name, application_count, funded_count, funded_financing, conversion_rate
FROM ranked WHERE rank_position <= 10
UNION ALL
-- Top 10 by Volume - 30d B2B
WITH ranked AS (
    SELECT '30d', 'B2B', dealer_name, SUM(application_count), SUM(funded_count), SUM(funded_financing), ROUND(100.0 * SUM(funded_count) / NULLIF(SUM(application_count), 0), 1),
        RANK() OVER (ORDER BY SUM(funded_financing) DESC)
    FROM dwh.mv_agg_dealer_metrics WHERE submission_week >= CURRENT_DATE - INTERVAL '30 days' AND party_type = 'B2B' GROUP BY dealer_name
)
SELECT 'Top 10 by Volume', time_horizon, party_type_filter, rank_position, dealer_name, application_count, funded_count, funded_financing, conversion_rate
FROM ranked WHERE rank_position <= 10
UNION ALL
-- Top 10 by Volume - 90d All
WITH ranked AS (
    SELECT '90d', 'All', dealer_name, SUM(application_count), SUM(funded_count), SUM(funded_financing), ROUND(100.0 * SUM(funded_count) / NULLIF(SUM(application_count), 0), 1),
        RANK() OVER (ORDER BY SUM(funded_financing) DESC)
    FROM dwh.mv_agg_dealer_metrics WHERE submission_week >= CURRENT_DATE - INTERVAL '90 days' GROUP BY dealer_name
)
SELECT 'Top 10 by Volume', time_horizon, party_type_filter, rank_position, dealer_name, application_count, funded_count, funded_financing, conversion_rate
FROM ranked WHERE rank_position <= 10
UNION ALL
-- Top 10 by Volume - YTD All
WITH ranked AS (
    SELECT 'YTD', 'All', dealer_name, SUM(application_count), SUM(funded_count), SUM(funded_financing), ROUND(100.0 * SUM(funded_count) / NULLIF(SUM(application_count), 0), 1),
        RANK() OVER (ORDER BY SUM(funded_financing) DESC)
    FROM dwh.mv_agg_dealer_metrics WHERE submission_week >= DATE_TRUNC('year', CURRENT_DATE)::DATE GROUP BY dealer_name
)
SELECT 'Top 10 by Volume', time_horizon, party_type_filter, rank_position, dealer_name, application_count, funded_count, funded_financing, conversion_rate
FROM ranked WHERE rank_position <= 10
UNION ALL
-- Top 10 by Conversion - 30d All (min 5 apps)
WITH ranked AS (
    SELECT '30d', 'All', dealer_name, SUM(application_count), SUM(funded_count), SUM(funded_financing), ROUND(100.0 * SUM(funded_count) / NULLIF(SUM(application_count), 0), 1),
        RANK() OVER (ORDER BY ROUND(100.0 * SUM(funded_count) / NULLIF(SUM(application_count), 0), 1) DESC)
    FROM dwh.mv_agg_dealer_metrics WHERE submission_week >= CURRENT_DATE - INTERVAL '30 days' GROUP BY dealer_name HAVING SUM(application_count) >= 5
)
SELECT 'Top 10 by Conversion', time_horizon, party_type_filter, rank_position, dealer_name, application_count, funded_count, funded_financing, conversion_rate
FROM ranked WHERE rank_position <= 10
UNION ALL
-- Top 10 by Conversion - 90d All (min 5 apps)
WITH ranked AS (
    SELECT '90d', 'All', dealer_name, SUM(application_count), SUM(funded_count), SUM(funded_financing), ROUND(100.0 * SUM(funded_count) / NULLIF(SUM(application_count), 0), 1),
        RANK() OVER (ORDER BY ROUND(100.0 * SUM(funded_count) / NULLIF(SUM(application_count), 0), 1) DESC)
    FROM dwh.mv_agg_dealer_metrics WHERE submission_week >= CURRENT_DATE - INTERVAL '90 days' GROUP BY dealer_name HAVING SUM(application_count) >= 5
)
SELECT 'Top 10 by Conversion', time_horizon, party_type_filter, rank_position, dealer_name, application_count, funded_count, funded_financing, conversion_rate
FROM ranked WHERE rank_position <= 10;

COMMENT ON VIEW dwh.v_powerbi_dealer_performance IS 'Top 10 dealer rankings dashboard view';

-- -----------------------------------------------------------------------------
-- 4.3: Dealer Metrics Refresh Procedure
-- -----------------------------------------------------------------------------

\echo 'Creating Phase 4 refresh procedure...'

CREATE OR REPLACE PROCEDURE dwh.refresh_dealer_metrics()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_agg_dealer_metrics;
    RAISE NOTICE 'Dealer metrics refreshed at %', NOW();
END;
$$;

\echo 'Phase 4 complete'

-- =============================================================================
-- MASTER REFRESH PROCEDURES
-- =============================================================================

\echo ''
\echo '>>> Creating Master Refresh Procedures'
\echo ''

-- Refresh all metric aggregations (call 3x daily)
CREATE OR REPLACE PROCEDURE dwh.refresh_metric_aggregations()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_agg_daily_metrics;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_agg_weekly_cohorts;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_stage_duration_thresholds;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_agg_loss_metrics;
    REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_agg_dealer_metrics;
    RAISE NOTICE 'All metric aggregations refreshed at %', CURRENT_TIMESTAMP;
END;
$$;

COMMENT ON PROCEDURE dwh.refresh_metric_aggregations IS 'Refreshes all aggregation MVs. Call 3x daily (7am, 1pm, 6pm).';

-- Full refresh (initial deployment)
CREATE OR REPLACE PROCEDURE dwh.refresh_all_funnel_views()
LANGUAGE plpgsql AS $$
BEGIN
    RAISE NOTICE 'Refreshing base fact table...';
    CALL dwh.refresh_application_funnel_full();
    RAISE NOTICE 'Refreshing metric aggregations...';
    CALL dwh.refresh_metric_aggregations();
    RAISE NOTICE 'Full funnel view refresh completed at %', CURRENT_TIMESTAMP;
END;
$$;

COMMENT ON PROCEDURE dwh.refresh_all_funnel_views IS 'Full refresh of base fact table + all aggregations. Use for initial deployment.';

-- =============================================================================
-- DEPLOYMENT COMPLETE
-- =============================================================================

\echo ''
\echo '============================================='
\echo 'DEPLOYMENT COMPLETE'
\echo ''
\echo 'Next steps:'
\echo '1. Run: CALL dwh.refresh_all_funnel_views();'
\echo '   (This populates all materialized views with data)'
\echo ''
\echo '2. Schedule 3x daily refresh:'
\echo '   CALL dwh.refresh_metric_aggregations();'
\echo ''
\echo '3. Connect PowerBI to:'
\echo '   - dwh.v_powerbi_funnel_executive'
\echo '   - dwh.v_powerbi_funnel_operations'
\echo '   - dwh.v_powerbi_loss_analysis'
\echo '   - dwh.v_powerbi_dealer_performance'
\echo '============================================='
