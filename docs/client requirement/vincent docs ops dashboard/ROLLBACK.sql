-- =============================================================================
-- FUNNEL ANALYTICS - ROLLBACK SCRIPT
-- =============================================================================
--
-- Use this script to completely remove all funnel analytics objects.
-- All objects are isolated - no impact on existing ODS tables.
--
-- =============================================================================

\echo 'Rolling back Funnel Analytics objects...'

-- Drop in reverse dependency order

-- Phase 4: Dealer Performance
DROP VIEW IF EXISTS dwh.v_powerbi_dealer_performance CASCADE;
DROP MATERIALIZED VIEW IF EXISTS dwh.mv_agg_dealer_metrics CASCADE;
DROP PROCEDURE IF EXISTS dwh.refresh_dealer_metrics();

-- Phase 3: Loss Analysis
DROP VIEW IF EXISTS dwh.v_powerbi_loss_analysis CASCADE;
DROP MATERIALIZED VIEW IF EXISTS dwh.mv_agg_loss_metrics CASCADE;
DROP VIEW IF EXISTS dwh.v_stuck_responsibility_summary CASCADE;
DROP VIEW IF EXISTS dwh.v_stuck_responsibility CASCADE;
DROP VIEW IF EXISTS dwh.v_post_approval_dropoffs CASCADE;
DROP VIEW IF EXISTS dwh.v_dropoff_reasons CASCADE;
DROP VIEW IF EXISTS dwh.v_rejection_summary CASCADE;
DROP VIEW IF EXISTS dwh.v_rejection_reasons CASCADE;
DROP TABLE IF EXISTS dwh.dim_rejection_phrase CASCADE;
DROP PROCEDURE IF EXISTS dwh.refresh_loss_metrics();

-- Phase 2: Core Metrics
DROP VIEW IF EXISTS dwh.v_powerbi_funnel_operations CASCADE;
DROP VIEW IF EXISTS dwh.v_powerbi_funnel_executive CASCADE;
DROP VIEW IF EXISTS dwh.v_powerbi_daily_metrics CASCADE;
DROP VIEW IF EXISTS dwh.v_stuck_applications CASCADE;
DROP MATERIALIZED VIEW IF EXISTS dwh.mv_stage_duration_thresholds CASCADE;
DROP MATERIALIZED VIEW IF EXISTS dwh.mv_agg_weekly_cohorts CASCADE;
DROP MATERIALIZED VIEW IF EXISTS dwh.mv_agg_daily_metrics CASCADE;
DROP PROCEDURE IF EXISTS dwh.refresh_cohorts_and_thresholds_initial();
DROP PROCEDURE IF EXISTS dwh.refresh_cohorts_and_thresholds();

-- Phase 1: Data Foundation
DROP VIEW IF EXISTS dwh.v_fact_application_funnel CASCADE;
DROP MATERIALIZED VIEW IF EXISTS dwh.mv_fact_application_funnel CASCADE;
DROP VIEW IF EXISTS dwh.v_application_funnel_progress CASCADE;
DROP VIEW IF EXISTS dwh.v_application_outcomes CASCADE;
DROP VIEW IF EXISTS dwh.v_application_stage_entries CASCADE;
DROP VIEW IF EXISTS dwh.v_application_events CASCADE;
DROP VIEW IF EXISTS dwh.v_status_outcome_mapping CASCADE;
DROP VIEW IF EXISTS dwh.v_step_stage_mapping CASCADE;
DROP TABLE IF EXISTS dwh.dim_funnel_stage CASCADE;
DROP FUNCTION IF EXISTS dwh.get_stage_for_step(VARCHAR);

-- Master procedures
DROP PROCEDURE IF EXISTS dwh.refresh_all_funnel_views();
DROP PROCEDURE IF EXISTS dwh.refresh_metric_aggregations();
DROP PROCEDURE IF EXISTS dwh.refresh_application_funnel_full();
DROP PROCEDURE IF EXISTS dwh.refresh_application_funnel();

\echo 'Rollback complete. All funnel analytics objects have been removed.'
