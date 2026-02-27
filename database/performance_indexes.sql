-- =============================================================================
-- LeaseTeq Risk Engine — AWS RDS Performance Indexes
-- Schema: lt_risk_engine
-- Database: PostgreSQL 15+ on AWS RDS
-- Generated: February 2026
-- Maintainer: Aralytiks LLC
--
-- PURPOSE:
--   Additional indexes for production performance on AWS RDS.
--   These are NOT created by the Alembic migrations — they should be
--   applied separately after the initial deployment, during a low-traffic
--   maintenance window (CREATE INDEX CONCURRENTLY does not lock the table).
--
-- USAGE:
--   Run after: alembic upgrade head
--   All statements use CONCURRENTLY to avoid table locks in production.
--   Run as the riskengine database user (must own the tables).
--
-- SECTIONS:
--   1. Partial indexes on risk_assessment (reduce index size for common filters)
--   2. Composite indexes for reporting queries
--   3. JSONB optimisation (if columns converted from JSON to JSONB)
--   4. Dealer risk metrics optimisation
--   5. Segment performance optimisation
--   6. Index maintenance commands
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Partial indexes on risk_assessment
--    These only index rows matching the WHERE clause, making them much smaller
--    than full indexes while covering the most common analyst query patterns.
-- ─────────────────────────────────────────────────────────────────────────────

-- Credit analyst workqueue: applications pending manual review
-- SELECT * FROM risk_assessment WHERE decision = 'MANUAL_REVIEW' ORDER BY evaluated_at DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_assessment_manual_review
  ON lt_risk_engine.risk_assessment (evaluated_at DESC)
  WHERE decision = 'MANUAL_REVIEW';

COMMENT ON INDEX lt_risk_engine.ix_assessment_manual_review IS
  'Partial index for analyst workqueue queries. Only indexes MANUAL_REVIEW rows '
  '(typically ~20% of portfolio). Avoids scanning BRIGHT_GREEN/AUTO_APPROVE rows.';


-- Risk monitoring: declined applications
-- SELECT * FROM risk_assessment WHERE tier = 'RED' AND evaluated_at > ...
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_assessment_red_tier
  ON lt_risk_engine.risk_assessment (evaluated_at DESC)
  WHERE tier = 'RED';

COMMENT ON INDEX lt_risk_engine.ix_assessment_red_tier IS
  'Partial index for decline monitoring and analysis. '
  'Typically covers ~10-15% of portfolio.';


-- Auto-approve monitoring: fast access to automated approvals
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_assessment_auto_approve
  ON lt_risk_engine.risk_assessment (evaluated_at DESC)
  WHERE decision = 'AUTO_APPROVE';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Composite indexes for common reporting query patterns
-- ─────────────────────────────────────────────────────────────────────────────

-- Composite: (tier, evaluated_at) — tier distribution reports over time
-- SELECT tier, COUNT(*) FROM risk_assessment
-- WHERE evaluated_at BETWEEN '2026-01-01' AND '2026-02-01' GROUP BY tier
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_assessment_tier_date
  ON lt_risk_engine.risk_assessment (tier, evaluated_at DESC);

COMMENT ON INDEX lt_risk_engine.ix_assessment_tier_date IS
  'Supports tier distribution time-series reports. '
  'Covers GROUP BY tier with time range filters.';


-- Composite: (customer_id, evaluated_at) — customer history lookups
-- SELECT * FROM risk_assessment WHERE customer_id = ? ORDER BY evaluated_at DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_assessment_customer_date
  ON lt_risk_engine.risk_assessment (customer_id, evaluated_at DESC);


-- Composite: (dealer_id, evaluated_at) — dealer portfolio analysis
-- SELECT tier, COUNT(*) FROM risk_assessment WHERE dealer_id = ? GROUP BY tier
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_assessment_dealer_date
  ON lt_risk_engine.risk_assessment (dealer_id, evaluated_at DESC)
  WHERE dealer_id IS NOT NULL;


-- Composite: (model_version, tier) — model version comparison reports
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_assessment_model_tier
  ON lt_risk_engine.risk_assessment (model_version, tier);


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. JSONB optimisation
--    Apply ONLY IF you convert JSON columns to JSONB.
--    Converting: ALTER TABLE lt_risk_engine.risk_assessment
--                ALTER COLUMN factor_scores_json TYPE JSONB USING factor_scores_json::jsonb;
--    NOTE: This requires a full table rewrite — use a maintenance window.
-- ─────────────────────────────────────────────────────────────────────────────

-- GIN index for factor_scores_json — enables JSON path queries
-- e.g., SELECT * FROM risk_assessment WHERE factor_scores_json @> '[{"bin_label": "MISSING"}]'
-- NOTE: Only create this if factor_scores_json has been converted to JSONB
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_factor_scores_gin
--   ON lt_risk_engine.risk_assessment
--   USING GIN (factor_scores_json jsonb_path_ops);

-- GIN index for business_rule_overrides_json — find all declined-by-rule assessments
-- e.g., SELECT * FROM risk_assessment WHERE business_rule_overrides_json @> '[{"rule_code": "BR-04"}]'
-- NOTE: Only create this if business_rule_overrides_json has been converted to JSONB
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_rule_overrides_gin
--   ON lt_risk_engine.risk_assessment
--   USING GIN (business_rule_overrides_json jsonb_path_ops)
--   WHERE business_rule_overrides_json IS NOT NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Dealer risk metrics optimisation
-- ─────────────────────────────────────────────────────────────────────────────

-- Latest snapshot per dealer — used by Flowable lookups
-- SELECT * FROM dealer_risk_metrics WHERE dealer_id = ? ORDER BY snapshot_date DESC LIMIT 1
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_dealer_metrics_latest
  ON lt_risk_engine.dealer_risk_metrics (dealer_id, snapshot_date DESC);

COMMENT ON INDEX lt_risk_engine.ix_dealer_metrics_latest IS
  'Flowable reads the latest dealer metrics via dealer_id. '
  'This composite index ensures O(log n) lookup instead of a sequential scan.';


-- Watchlist trend analysis
-- SELECT * FROM dealer_risk_metrics WHERE is_watchlist = true AND default_rate_trend = 'WORSENING'
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_dealer_watchlist_trend
  ON lt_risk_engine.dealer_risk_metrics (default_rate_trend, snapshot_date DESC)
  WHERE is_watchlist = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Segment performance optimisation
-- ─────────────────────────────────────────────────────────────────────────────

-- WoE drift monitoring — find bins with high drift for recalibration
-- SELECT * FROM population_segment_performance
-- WHERE ABS(woe_drift) > 0.1 ORDER BY ABS(woe_drift) DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_segment_woe_drift
  ON lt_risk_engine.population_segment_performance (ABS(woe_drift) DESC)
  WHERE woe_drift IS NOT NULL;

COMMENT ON INDEX lt_risk_engine.ix_segment_woe_drift IS
  'Supports the Calibration UI recalibration flag dashboard. '
  'Finds bins with WoE drift exceeding 0.1 nats threshold.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Index maintenance reference
-- ─────────────────────────────────────────────────────────────────────────────

-- Check index usage (run periodically to identify unused indexes):
-- SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
-- FROM pg_stat_user_indexes
-- WHERE schemaname = 'lt_risk_engine'
-- ORDER BY idx_scan ASC;

-- Check index sizes:
-- SELECT indexname, pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
-- FROM pg_stat_user_indexes
-- WHERE schemaname = 'lt_risk_engine'
-- ORDER BY pg_relation_size(indexrelid) DESC;

-- Rebuild a bloated index (online, no lock):
-- REINDEX INDEX CONCURRENTLY lt_risk_engine.ix_risk_assessment_request_id;

-- Check for missing statistics (if query plans look wrong):
-- ANALYZE lt_risk_engine.risk_assessment;

-- Set aggressive autovacuum on the high-write risk_assessment table:
-- ALTER TABLE lt_risk_engine.risk_assessment SET (
--   autovacuum_vacuum_scale_factor = 0.01,
--   autovacuum_analyze_scale_factor = 0.005,
--   autovacuum_vacuum_cost_delay = 2
-- );

-- =============================================================================
-- End of performance_indexes.sql
-- =============================================================================
