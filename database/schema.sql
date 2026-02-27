-- =============================================================================
-- LeaseTeq Risk Engine — Complete Database Schema DDL
-- Schema: lt_risk_engine
-- Database: PostgreSQL 15+
-- Generated: February 2026
-- Maintainer: Aralytiks LLC
--
-- USAGE:
--   Run this file once against a fresh database to create the full schema.
--   For incremental updates, use Alembic migrations instead:
--     alembic upgrade head
--
--   This file is kept in sync with the Alembic migration chain
--   (001 through 005) and can be used as a reference or for
--   spinning up a clean test / dev database quickly.
--
-- ORDER:
--   1. Schema
--   2. Primary audit table (risk_assessment)
--   3. Calibration tables (model_version → factor_config → factor_bins
--      → tier_thresholds → business_rules → calibration_audit_log)
--   4. WoE scorecard params
--   5. Monitoring tables (scoring_defaults_applied, population_segment_performance,
--      model_monitoring_snapshot, dealer_risk_metrics)
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 0. Schema
-- ─────────────────────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS lt_risk_engine;

COMMENT ON SCHEMA lt_risk_engine IS
  'LeaseTeq Risk Engine — all scoring, calibration, and monitoring tables';


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. risk_assessment — Primary audit table (one row per scoring request)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE lt_risk_engine.risk_assessment (

  -- Identity
  assessment_id           VARCHAR(36)     PRIMARY KEY,
  request_id              VARCHAR(100)    NOT NULL UNIQUE,   -- Flowable idempotency key
  contract_id             VARCHAR(100)    NOT NULL,
  customer_id             VARCHAR(100)    NOT NULL,

  -- Scoring configuration
  model_version           VARCHAR(10)     NOT NULL,          -- e.g. '1.2'

  -- Primary scoring outputs
  total_score             FLOAT           NOT NULL,          -- composite score, range ~-75 to +53
  tier                    VARCHAR(20)     NOT NULL,          -- BRIGHT_GREEN | GREEN | YELLOW | RED
  decision                VARCHAR(30)     NOT NULL,          -- AUTO_APPROVE | APPROVE_STANDARD | MANUAL_REVIEW | DECLINE
  probability_of_default  FLOAT,                             -- calibrated 12-month PD estimate (0-1)

  -- Factor breakdown (JSON for schema flexibility)
  factor_scores_json      JSON            NOT NULL,          -- array of {factor_name, raw_value, bin_label, weight, raw_score}
  dscr_json               JSON            NOT NULL,          -- {dscr_value, monthly_disposable_income, calculation_method, is_valid}
  business_rule_overrides_json JSON,                         -- array of {rule_code, rule_description, triggered_value}

  -- Legacy WoE scorecard (B2C only)
  legacy_score            INTEGER,                           -- WoE points total, range ~333-502; NULL for B2B
  legacy_band             VARCHAR(1),                        -- A/B/C/D/E; NULL for B2B

  -- Full payload storage (for audit replay)
  request_payload         JSON            NOT NULL,          -- complete Flowable POST request
  response_payload        JSON            NOT NULL,          -- complete response returned to Flowable

  -- Performance metadata
  processing_time_ms      INTEGER         NOT NULL,          -- end-to-end scoring time in milliseconds
  evaluated_at            TIMESTAMPTZ     NOT NULL,          -- UTC scoring timestamp

  -- Row metadata
  created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

  -- Added in migration 004: default value tracking
  defaults_applied_count  INTEGER         DEFAULT 0,         -- count of fields substituted with defaults
  defaults_applied_json   JSON,                              -- array of {field_name, original_value, default_value}
  dealer_id               VARCHAR(100),                      -- extracted for easier query (denormalised from request_payload)
  source_system           VARCHAR(50)     DEFAULT 'SST'      -- originating system identifier

);

COMMENT ON TABLE lt_risk_engine.risk_assessment IS
  'Immutable audit log of every risk scoring request. One row per POST /v1/risk/evaluate call.';

-- Core access pattern indexes
CREATE UNIQUE INDEX ix_risk_assessment_request_id
  ON lt_risk_engine.risk_assessment (request_id);
  -- Used by idempotency check on every POST /evaluate — must be O(log n)

CREATE INDEX ix_risk_assessment_contract_id
  ON lt_risk_engine.risk_assessment (contract_id);
  -- Dispute resolution: all assessments for a contract

CREATE INDEX ix_risk_assessment_customer_id
  ON lt_risk_engine.risk_assessment (customer_id);
  -- Portfolio queries: all assessments for a customer

CREATE INDEX ix_risk_assessment_tier
  ON lt_risk_engine.risk_assessment (tier);
  -- Dashboard: filter by tier (e.g. all RED decisions today)

CREATE INDEX ix_risk_assessment_evaluated_at
  ON lt_risk_engine.risk_assessment (evaluated_at DESC);
  -- Time-range reporting; also base for future range partitioning


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. model_version — Snapshot of a complete scoring model configuration
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE lt_risk_engine.model_version (

  version_id      VARCHAR(20)     PRIMARY KEY,            -- e.g. '1.2.0', '1.2.1'
  description     TEXT,                                   -- human-readable change notes
  status          VARCHAR(20)     NOT NULL DEFAULT 'DRAFT', -- DRAFT | PUBLISHED | ARCHIVED
  published_at    TIMESTAMPTZ,                            -- when this version went live
  published_by    VARCHAR(100),                           -- Keycloak sub (user) who published
  created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
  created_by      VARCHAR(100)    NOT NULL                -- Keycloak sub who created this version

);

COMMENT ON TABLE lt_risk_engine.model_version IS
  'Each row is a point-in-time snapshot of the scoring model configuration. '
  'Only one version has status=PUBLISHED at any time.';

COMMENT ON COLUMN lt_risk_engine.model_version.status IS
  'DRAFT: being worked on in the Calibration UI. '
  'PUBLISHED: currently active for scoring. '
  'ARCHIVED: superseded by a newer version.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. scoring_factor_config — Factor weights and metadata per model version
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE lt_risk_engine.scoring_factor_config (

  id              SERIAL          PRIMARY KEY,
  version_id      VARCHAR(20)     NOT NULL REFERENCES lt_risk_engine.model_version(version_id),
  factor_name     VARCHAR(50)     NOT NULL,   -- LTV | Term | Age | CRIF | Intrum | DSCR | Permit |
                                              -- VehiclePriceTier | ZEK | DealerRisk (B2C)
                                              -- CompanyAge | DebtRatio | CompanyType | IndustryRisk (B2B)
  weight          FLOAT           NOT NULL,   -- 0.0-1.0; all factors per version must sum to 1.0
  enabled         BOOLEAN         NOT NULL DEFAULT TRUE,
  description     TEXT,
  score_range_min FLOAT,                      -- documentation: minimum possible raw score
  score_range_max FLOAT,                      -- documentation: maximum possible raw score
  display_order   INTEGER         NOT NULL DEFAULT 0

);

COMMENT ON TABLE lt_risk_engine.scoring_factor_config IS
  'Factor metadata per model version. One row per factor per version.';

COMMENT ON COLUMN lt_risk_engine.scoring_factor_config.weight IS
  'Relative importance in the scoring model. Stored for reporting; '
  'raw scores are summed directly (not multiplied by weight) in v1.2.';

CREATE UNIQUE INDEX ix_factor_config_version_factor
  ON lt_risk_engine.scoring_factor_config (version_id, factor_name);
  -- One configuration row per factor per version


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. scoring_factor_bins — Bin definitions (calibratable raw scores)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE lt_risk_engine.scoring_factor_bins (

  id                  SERIAL          PRIMARY KEY,
  version_id          VARCHAR(20)     NOT NULL REFERENCES lt_risk_engine.model_version(version_id),
  factor_name         VARCHAR(50)     NOT NULL,
  bin_order           INTEGER         NOT NULL,   -- evaluation order within the factor (1=first)
  bin_label           VARCHAR(100)    NOT NULL,   -- human-readable, shown in API response and UI
  lower_bound         FLOAT,                      -- NULL = open-ended lower (e.g., -infinity)
  upper_bound         FLOAT,                      -- NULL = open-ended upper (e.g., +infinity)
  lower_inclusive     BOOLEAN         NOT NULL DEFAULT TRUE,  -- >= (true) or > (false)
  upper_inclusive     BOOLEAN         NOT NULL DEFAULT TRUE,  -- <= (true) or < (false)
  match_value         VARCHAR(100),               -- for categorical bins: exact string to match (e.g., 'C', 'AG')
  is_missing_bin      BOOLEAN         NOT NULL DEFAULT FALSE, -- TRUE = handles NULL/missing input
  raw_score           FLOAT           NOT NULL,   -- THE CALIBRATABLE VALUE; range typically -10 to +8
  risk_interpretation VARCHAR(200)                -- human-readable risk description for this bin

);

COMMENT ON TABLE lt_risk_engine.scoring_factor_bins IS
  'Bin definitions for each scoring factor. The raw_score column is the primary '
  'calibration target — risk managers adjust these values in the Calibration UI.';

COMMENT ON COLUMN lt_risk_engine.scoring_factor_bins.raw_score IS
  'Score assigned when an input falls into this bin. '
  'Positive = lower risk, Negative = higher risk. '
  'Typical range: -10 (worst) to +8 (best).';

COMMENT ON COLUMN lt_risk_engine.scoring_factor_bins.is_missing_bin IS
  'When TRUE, this bin is selected when the input field is NULL. '
  'Every factor should have exactly one missing bin to ensure robust '
  'handling of incomplete data from Flowable.';

CREATE UNIQUE INDEX ix_factor_bins_version_factor
  ON lt_risk_engine.scoring_factor_bins (version_id, factor_name, bin_order);
  -- Ensures bins are uniquely ordered within each factor per version


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. scoring_tier_thresholds — Score-to-tier mapping
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE lt_risk_engine.scoring_tier_thresholds (

  id              SERIAL          PRIMARY KEY,
  version_id      VARCHAR(20)     NOT NULL REFERENCES lt_risk_engine.model_version(version_id),
  tier_name       VARCHAR(30)     NOT NULL,   -- BRIGHT_GREEN | GREEN | YELLOW | RED
  tier_order      INTEGER         NOT NULL,   -- 1=BRIGHT_GREEN (checked first), 4=RED (catch-all)
  min_score       FLOAT,                      -- minimum composite score for this tier; NULL for RED (no minimum)
  decision        VARCHAR(30)     NOT NULL,   -- AUTO_APPROVE | APPROVE_STANDARD | MANUAL_REVIEW | DECLINE
  estimated_pd    FLOAT,                      -- calibrated annualised PD for this tier
  color_hex       VARCHAR(7),                 -- hex colour for UI: e.g. '#27AE60'
  description     TEXT

);

COMMENT ON TABLE lt_risk_engine.scoring_tier_thresholds IS
  'Score thresholds that map composite scores to risk tiers and credit decisions. '
  'v1.2 thresholds: BRIGHT_GREEN>=25, GREEN>=10, YELLOW>=0, RED<0.';

CREATE UNIQUE INDEX ix_tier_version_tier
  ON lt_risk_engine.scoring_tier_thresholds (version_id, tier_name);
  -- One threshold per tier per version


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. business_rules — Hard kill override conditions
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE lt_risk_engine.business_rules (

  id                  SERIAL          PRIMARY KEY,
  version_id          VARCHAR(20)     NOT NULL REFERENCES lt_risk_engine.model_version(version_id),
  rule_code           VARCHAR(10)     NOT NULL,  -- BR-01 ... BR-08, BR-B01 ... BR-B04
  rule_name           VARCHAR(100)    NOT NULL,
  description         TEXT,
  condition_field     VARCHAR(100)    NOT NULL,  -- field being evaluated (e.g., 'age', 'ltv', 'zefix_status')
  condition_operator  VARCHAR(10)     NOT NULL,  -- <, >, <=, >=, ==, !=, IN
  condition_value     VARCHAR(100)    NOT NULL,  -- threshold or value (e.g., '18', '120', 'DISSOLVED')
  forced_tier         VARCHAR(30)     NOT NULL DEFAULT 'RED',
  forced_decision     VARCHAR(30)     NOT NULL DEFAULT 'DECLINE',
  enabled             BOOLEAN         NOT NULL DEFAULT TRUE,
  severity            VARCHAR(20)     NOT NULL DEFAULT 'HARD'  -- HARD = always overrides, SOFT = advisory

);

COMMENT ON TABLE lt_risk_engine.business_rules IS
  'Hard-kill conditions. Any triggered rule forces tier=RED and decision=DECLINE '
  'regardless of composite score. Rules can be disabled without deletion.';

CREATE UNIQUE INDEX ix_rules_version_code
  ON lt_risk_engine.business_rules (version_id, rule_code);
  -- One rule per code per version


-- ─────────────────────────────────────────────────────────────────────────────
-- 7. calibration_audit_log — Governance trail for all model changes
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE lt_risk_engine.calibration_audit_log (

  id              SERIAL          PRIMARY KEY,
  version_id      VARCHAR(20)     NOT NULL,
  action          VARCHAR(50)     NOT NULL,   -- CREATED | UPDATED | PUBLISHED | ARCHIVED
  table_name      VARCHAR(100)    NOT NULL,   -- which calibration table was modified
  record_id       VARCHAR(100),               -- PK of the modified record
  field_name      VARCHAR(100),               -- which column was changed
  old_value       TEXT,                       -- value before change; NULL for CREATED
  new_value       TEXT,                       -- value after change
  changed_by      VARCHAR(100)    NOT NULL,   -- Keycloak sub (user ID)
  changed_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
  change_reason   TEXT                        -- optional free-text justification

);

COMMENT ON TABLE lt_risk_engine.calibration_audit_log IS
  'Immutable governance audit trail. Every change to any calibration table '
  'is recorded here. Required for model risk management and regulatory audit.';

CREATE INDEX ix_audit_version
  ON lt_risk_engine.calibration_audit_log (version_id);

CREATE INDEX ix_audit_changed_at
  ON lt_risk_engine.calibration_audit_log (changed_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- 8. woe_scorecard_params — Logistic regression parameters
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE lt_risk_engine.woe_scorecard_params (

  id                  SERIAL          PRIMARY KEY,
  version_id          VARCHAR(20)     NOT NULL REFERENCES lt_risk_engine.model_version(version_id),
  param_type          VARCHAR(20)     NOT NULL,   -- INTERCEPT | COEFFICIENT | BIN_POINTS
  factor_name         VARCHAR(50),                -- NULL for INTERCEPT
  bin_label           VARCHAR(100),               -- NULL for INTERCEPT and COEFFICIENT
  coefficient         FLOAT,                      -- logistic regression coefficient
  woe_value           FLOAT,                      -- Weight of Evidence value for this bin
  points              FLOAT           NOT NULL,   -- scaled scorecard points
  bin_default_rate    FLOAT,                      -- observed default rate in this bin (development sample)
  bin_count           INTEGER,                    -- sample count in this bin
  bin_default_count   INTEGER,                    -- default count in this bin
  created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()

);

COMMENT ON TABLE lt_risk_engine.woe_scorecard_params IS
  'Logistic regression parameters for the legacy WoE scorecard (A-E bands). '
  'Includes intercept (389), per-factor coefficients, and per-bin point allocations. '
  'Used for BAWAG reporting and backward compatibility.';

CREATE INDEX ix_woe_params_version
  ON lt_risk_engine.woe_scorecard_params (version_id, param_type, factor_name);


-- ─────────────────────────────────────────────────────────────────────────────
-- 9. scoring_defaults_applied — Audit trail for NULL input substitution
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE lt_risk_engine.scoring_defaults_applied (

  id              SERIAL          PRIMARY KEY,
  assessment_id   VARCHAR(36)     NOT NULL REFERENCES lt_risk_engine.risk_assessment(assessment_id),
  field_name      VARCHAR(100)    NOT NULL,   -- e.g., 'crif_score', 'monthly_rent', 'date_of_birth'
  original_value  TEXT,                       -- what was received (NULL or empty string)
  default_value   TEXT            NOT NULL,   -- what was substituted
  default_source  VARCHAR(50)     NOT NULL,   -- SYSTEM | CONFIG | POPULATION_MEAN
  factor_affected VARCHAR(50),                -- which scoring factor was impacted
  impact_on_score FLOAT,                      -- score delta vs. if actual value existed
  created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()

);

COMMENT ON TABLE lt_risk_engine.scoring_defaults_applied IS
  'Records every instance where a NULL or missing input field was substituted '
  'with a default value during scoring. Enables analysis of data quality impact '
  'on scores and identification of upstream data collection gaps.';

CREATE INDEX ix_defaults_assessment_id
  ON lt_risk_engine.scoring_defaults_applied (assessment_id);

CREATE INDEX ix_defaults_field_name
  ON lt_risk_engine.scoring_defaults_applied (field_name);
  -- Find the most commonly missing fields across the portfolio


-- ─────────────────────────────────────────────────────────────────────────────
-- 10. dealer_risk_metrics — Nightly dealer default rate snapshots
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE lt_risk_engine.dealer_risk_metrics (

  id                      SERIAL          PRIMARY KEY,
  dealer_id               VARCHAR(100)    NOT NULL,
  dealer_name             VARCHAR(200),
  snapshot_date           DATE            NOT NULL,

  -- Current portfolio metrics
  active_contracts        INTEGER         NOT NULL,   -- open contracts originated by this dealer
  total_originated        INTEGER         NOT NULL,   -- total contracts ever
  default_count           INTEGER         NOT NULL,   -- contracts at 90+ DPD or written off
  current_default_rate    FLOAT           NOT NULL,   -- default_count / total_originated; passed to scoring engine
  previous_default_rate   FLOAT,                      -- from prior snapshot; for trend computation
  default_rate_trend      VARCHAR(20),                -- IMPROVING | STABLE | WORSENING | NEW

  -- Volume and age
  active_months           INTEGER         NOT NULL,   -- months since first contract; <6m = NEW_DEALER in scoring
  volume_tier             VARCHAR(20),                -- BRONZE | SILVER | GOLD | PLATINUM
  avg_contract_size       FLOAT,                      -- average financed amount CHF

  -- Risk flags
  is_watchlist            BOOLEAN         NOT NULL DEFAULT FALSE,  -- TRUE if default_rate > 20%
  watchlist_reason        TEXT,                       -- human-readable explanation

  data_source             VARCHAR(100)    NOT NULL DEFAULT 'DATAHUB',
  created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()

);

COMMENT ON TABLE lt_risk_engine.dealer_risk_metrics IS
  'Nightly snapshot of dealer portfolio statistics, refreshed from the DataHub '
  '(dwh.dim_contract). Flowable reads the latest snapshot per dealer and passes '
  'dealer_default_rate in the scoring request payload.';

COMMENT ON COLUMN lt_risk_engine.dealer_risk_metrics.current_default_rate IS
  'Dealer historical default rate (0-1). Rates above 0.20 (20%) '
  'set is_watchlist=TRUE and trigger business rule BR-07 hard decline.';

CREATE UNIQUE INDEX ix_dealer_metrics_dealer
  ON lt_risk_engine.dealer_risk_metrics (dealer_id, snapshot_date);
  -- Supports ON CONFLICT DO UPDATE upsert in batch job

CREATE INDEX ix_dealer_metrics_watchlist
  ON lt_risk_engine.dealer_risk_metrics (is_watchlist)
  WHERE is_watchlist = TRUE;
  -- Partial index: only watchlisted dealers (typically a small subset)


-- ─────────────────────────────────────────────────────────────────────────────
-- 11. population_segment_performance — Historical default rates per factor bin
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE lt_risk_engine.population_segment_performance (

  id                          SERIAL          PRIMARY KEY,
  snapshot_date               DATE            NOT NULL,   -- when this snapshot was taken
  segment_type                VARCHAR(50)     NOT NULL,   -- FACTOR_BIN | TIER | OVERALL
  segment_key                 VARCHAR(100)    NOT NULL,   -- e.g., 'LTV:<75%', 'TIER:GREEN', 'OVERALL'
  factor_name                 VARCHAR(50),                -- NULL for TIER and OVERALL segments
  bin_label                   VARCHAR(100),               -- NULL for TIER and OVERALL segments

  -- Portfolio statistics from DataHub
  contract_count              INTEGER         NOT NULL,
  default_count               INTEGER         NOT NULL,
  observed_default_rate       FLOAT           NOT NULL,   -- actual DR: default_count / contract_count
  predicted_default_rate      FLOAT,                      -- average PD the model predicted
  avg_score                   FLOAT,                      -- average composite score in this segment
  avg_legacy_score            FLOAT,                      -- average legacy WoE score

  -- WoE recalibration metrics
  observed_woe                FLOAT,                      -- ln(% non-defaults / % defaults) for this bin
  original_woe                FLOAT,                      -- WoE from development sample
  woe_drift                   FLOAT,                      -- observed - original; >0.1 nats = recalibration flag

  -- Metadata
  data_source                 VARCHAR(100)    NOT NULL,   -- DATAHUB_ODS | MANUAL
  observation_window_months   INTEGER         NOT NULL DEFAULT 12,
  created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
  created_by                  VARCHAR(100)    NOT NULL DEFAULT 'system'

);

COMMENT ON TABLE lt_risk_engine.population_segment_performance IS
  'Quarterly snapshots of observed default rates per factor bin and tier. '
  'WoE drift > 0.1 nats flags a bin for recalibration in the Calibration UI. '
  'Populated by the quarterly_segment_refresh batch job.';

COMMENT ON COLUMN lt_risk_engine.population_segment_performance.woe_drift IS
  'Difference between current observed WoE and the original development sample WoE. '
  'Positive drift = bin is performing better than expected. '
  'Negative drift = bin is performing worse. '
  'Absolute drift > 0.1 nats triggers a recalibration review flag.';

CREATE INDEX ix_segment_perf_snapshot
  ON lt_risk_engine.population_segment_performance (snapshot_date, segment_type);

CREATE INDEX ix_segment_perf_factor
  ON lt_risk_engine.population_segment_performance (factor_name, bin_label);


-- ─────────────────────────────────────────────────────────────────────────────
-- 12. model_monitoring_snapshot — Periodic model health metrics
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE lt_risk_engine.model_monitoring_snapshot (

  id                          SERIAL          PRIMARY KEY,
  snapshot_date               DATE            NOT NULL,
  model_version               VARCHAR(20)     NOT NULL,
  scorecard_type              VARCHAR(20)     NOT NULL,   -- V1_2_COMPOSITE | LEGACY_WOE

  -- Discrimination metrics
  gini_coefficient            FLOAT,      -- 2*AUC-1; range 0-1, higher=better; v1.2 target >0.40
  ks_statistic                FLOAT,      -- Kolmogorov-Smirnov; max separation between default/non-default CDFs
  auc_roc                     FLOAT,      -- area under ROC curve; 0.5=random, 1.0=perfect

  -- Calibration metrics
  overall_predicted_pd        FLOAT,      -- portfolio-average model PD
  overall_observed_dr         FLOAT,      -- actual portfolio default rate
  calibration_ratio           FLOAT,      -- predicted / observed; ideal = 1.0

  -- Stability metrics
  psi_score                   FLOAT,      -- Population Stability Index; 0-0.1=stable, 0.1-0.25=shift, >0.25=alarm
  psi_status                  VARCHAR(20),-- STABLE | SHIFT | ALARM

  -- Portfolio composition
  total_contracts             INTEGER     NOT NULL,
  total_defaults              INTEGER     NOT NULL,
  observation_window_months   INTEGER     NOT NULL,
  tier_distribution_json      JSON,       -- {"BRIGHT_GREEN": 0.42, "GREEN": 0.30, "YELLOW": 0.20, "RED": 0.08}

  notes                       TEXT,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by                  VARCHAR(100) NOT NULL DEFAULT 'system'

);

COMMENT ON TABLE lt_risk_engine.model_monitoring_snapshot IS
  'Periodic model health report. Populated by the quarterly_segment_refresh job. '
  'Tracks discrimination power (Gini, KS), calibration, and population stability over time. '
  'PSI_STATUS=ALARM or Gini dropping below 0.35 should trigger an immediate recalibration review.';

CREATE UNIQUE INDEX ix_monitoring_snapshot_date
  ON lt_risk_engine.model_monitoring_snapshot (snapshot_date, model_version);


-- ─────────────────────────────────────────────────────────────────────────────
-- End of schema.sql
-- To verify: SELECT table_name FROM information_schema.tables
--            WHERE table_schema = 'lt_risk_engine' ORDER BY table_name;
-- Expected: 12 tables
-- ─────────────────────────────────────────────────────────────────────────────
