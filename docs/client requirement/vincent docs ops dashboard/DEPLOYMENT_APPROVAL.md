# Deployment Approval Request: Funnel Analytics Objects

**Prepared for:** DWH Owner
**Prepared by:** Vincent Van Seumeren
**Date:** 2026-02-01

## Summary

Request to create 25 new database objects in the `dwh` schema to enable funnel analytics dashboards in PowerBI. These objects are **additive only** - no existing tables or views are modified.

## Impact Assessment

| Category | Impact |
|----------|--------|
| Existing tables modified | **0** |
| Existing views modified | **0** |
| New tables created | 2 |
| New views created | 12 |
| New materialized views created | 6 |
| New procedures created | 5 |
| New functions created | 1 |
| New indexes created | ~20 |

## Objects to be Created

### 1. Tables (2)

| Table | Purpose | Estimated Rows |
|-------|---------|----------------|
| `dwh.dim_funnel_stage` | Funnel stage definitions (9 stages) | 9 |
| `dwh.dim_rejection_phrase` | Rejection reason phrase patterns for text extraction | ~32 |

**Storage estimate:** < 1 KB (tiny dimension tables)

### 2. Regular Views (12)

| View | Purpose | Source Tables |
|------|---------|---------------|
| `dwh.v_step_stage_mapping` | Maps flowapp steps to funnel stages | dim_funnel_stage |
| `dwh.v_status_outcome_mapping` | Maps contract statuses to outcomes | dim_funnel_stage |
| `dwh.v_application_events` | Unified event log (status + steps) | ods.contract, ods.contract_status_history_sst, ods.contract_flowapp_steps_sst |
| `dwh.v_application_stage_entries` | Stage entry timestamps per app | v_application_events |
| `dwh.v_application_outcomes` | Terminal outcomes per application | v_application_events |
| `dwh.v_application_funnel_progress` | Funnel progress summary per app | v_application_stage_entries |
| `dwh.v_fact_application_funnel` | PowerBI wrapper for fact MV | mv_fact_application_funnel |
| `dwh.v_powerbi_daily_metrics` | Daily metrics for PowerBI | mv_agg_daily_metrics |
| `dwh.v_stuck_applications` | Applications exceeding duration thresholds | v_fact_application_funnel, mv_stage_duration_thresholds |
| `dwh.v_rejection_reasons` | Extracted rejection reasons per app | ods.contract_notes_sst, dim_rejection_phrase |
| `dwh.v_rejection_summary` | Coverage stats for rejection extraction | mv_fact_application_funnel, v_rejection_reasons |
| `dwh.v_dropoff_reasons` | Drop-off categorization per app | mv_fact_application_funnel, ods.contract_notes_sst |
| `dwh.v_post_approval_dropoffs` | Approved-but-not-funded applications | mv_fact_application_funnel, ods.contract_notes_sst |
| `dwh.v_stuck_responsibility` | Stuck apps with responsibility attribution | v_stuck_applications |
| `dwh.v_stuck_responsibility_summary` | Aggregated responsibility counts | v_stuck_responsibility |
| `dwh.v_powerbi_funnel_executive` | Executive dashboard view | v_fact_application_funnel |
| `dwh.v_powerbi_funnel_operations` | Operations dashboard view | v_fact_application_funnel, v_stuck_applications |
| `dwh.v_powerbi_loss_analysis` | Loss analysis dashboard view | mv_agg_loss_metrics, v_stuck_responsibility_summary |
| `dwh.v_powerbi_dealer_performance` | Dealer Top 10 rankings dashboard | mv_agg_dealer_metrics |

### 3. Materialized Views (6)

| MV | Purpose | Grain | Est. Rows | Est. Size |
|----|---------|-------|-----------|-----------|
| `dwh.mv_fact_application_funnel` | One row per application with milestone dates | application_id | ~15,000 | ~5 MB |
| `dwh.mv_agg_daily_metrics` | Daily conversion metrics | (date, party_type) | ~730 | < 1 MB |
| `dwh.mv_agg_weekly_cohorts` | Weekly cohort conversion | (week, party_type) | ~104 | < 1 MB |
| `dwh.mv_stage_duration_thresholds` | P75/P90 duration thresholds | (stage, party_type) | ~16 | < 1 KB |
| `dwh.mv_agg_loss_metrics` | Aggregated loss counts | (week, party_type, type, category) | ~2,000 | < 1 MB |
| `dwh.mv_agg_dealer_metrics` | Dealer performance metrics | (dealer, week, party_type) | ~5,000 | ~2 MB |

**Total storage estimate:** ~10 MB

### 4. Procedures (5)

| Procedure | Purpose |
|-----------|---------|
| `dwh.refresh_application_funnel()` | Refresh base fact MV (concurrent) |
| `dwh.refresh_application_funnel_full()` | Full refresh (initial load) |
| `dwh.refresh_metric_aggregations()` | Refresh all aggregation MVs |
| `dwh.refresh_all_funnel_views()` | Full refresh of all MVs |
| `dwh.refresh_cohorts_and_thresholds()` | Refresh cohort MVs |
| `dwh.refresh_cohorts_and_thresholds_initial()` | Initial cohort MV load |
| `dwh.refresh_loss_metrics()` | Refresh loss metrics MV |
| `dwh.refresh_dealer_metrics()` | Refresh dealer metrics MV |

### 5. Functions (1)

| Function | Purpose |
|----------|---------|
| `dwh.get_stage_for_step(VARCHAR)` | Helper function for step-to-stage lookup |

## Dependencies on Existing Objects

The views read from these existing ODS tables (read-only):

| ODS Table | Usage |
|-----------|-------|
| `ods.contract` | Application master data |
| `ods.contract_status_history_sst` | Status change events |
| `ods.contract_flowapp_steps_sst` | Step completion events |
| `ods.contract_notes_sst` | Notes for rejection/drop-off text extraction |

**No writes to ODS tables. No schema changes to ODS.**

## Refresh Requirements

| Schedule | Procedure | Duration Est. |
|----------|-----------|---------------|
| 3x daily (7am, 1pm, 6pm) | `refresh_metric_aggregations()` | 30-60 sec |
| As needed | `refresh_application_funnel()` | 2-5 min |
| Initial only | `refresh_all_funnel_views()` | 5-10 min |

## Rollback Plan

All objects are new and isolated. To remove completely:

```sql
-- Drop in reverse dependency order
DROP VIEW IF EXISTS dwh.v_powerbi_dealer_performance CASCADE;
DROP VIEW IF EXISTS dwh.v_powerbi_loss_analysis CASCADE;
DROP VIEW IF EXISTS dwh.v_powerbi_funnel_operations CASCADE;
DROP VIEW IF EXISTS dwh.v_powerbi_funnel_executive CASCADE;
DROP VIEW IF EXISTS dwh.v_stuck_responsibility_summary CASCADE;
DROP VIEW IF EXISTS dwh.v_stuck_responsibility CASCADE;
DROP VIEW IF EXISTS dwh.v_post_approval_dropoffs CASCADE;
DROP VIEW IF EXISTS dwh.v_dropoff_reasons CASCADE;
DROP VIEW IF EXISTS dwh.v_rejection_summary CASCADE;
DROP VIEW IF EXISTS dwh.v_rejection_reasons CASCADE;
DROP VIEW IF EXISTS dwh.v_stuck_applications CASCADE;
DROP VIEW IF EXISTS dwh.v_powerbi_daily_metrics CASCADE;
DROP VIEW IF EXISTS dwh.v_fact_application_funnel CASCADE;
DROP VIEW IF EXISTS dwh.v_application_funnel_progress CASCADE;
DROP VIEW IF EXISTS dwh.v_application_outcomes CASCADE;
DROP VIEW IF EXISTS dwh.v_application_stage_entries CASCADE;
DROP VIEW IF EXISTS dwh.v_application_events CASCADE;
DROP VIEW IF EXISTS dwh.v_status_outcome_mapping CASCADE;
DROP VIEW IF EXISTS dwh.v_step_stage_mapping CASCADE;

DROP MATERIALIZED VIEW IF EXISTS dwh.mv_agg_dealer_metrics CASCADE;
DROP MATERIALIZED VIEW IF EXISTS dwh.mv_agg_loss_metrics CASCADE;
DROP MATERIALIZED VIEW IF EXISTS dwh.mv_stage_duration_thresholds CASCADE;
DROP MATERIALIZED VIEW IF EXISTS dwh.mv_agg_weekly_cohorts CASCADE;
DROP MATERIALIZED VIEW IF EXISTS dwh.mv_agg_daily_metrics CASCADE;
DROP MATERIALIZED VIEW IF EXISTS dwh.mv_fact_application_funnel CASCADE;

DROP TABLE IF EXISTS dwh.dim_rejection_phrase CASCADE;
DROP TABLE IF EXISTS dwh.dim_funnel_stage CASCADE;

DROP PROCEDURE IF EXISTS dwh.refresh_dealer_metrics();
DROP PROCEDURE IF EXISTS dwh.refresh_loss_metrics();
DROP PROCEDURE IF EXISTS dwh.refresh_cohorts_and_thresholds_initial();
DROP PROCEDURE IF EXISTS dwh.refresh_cohorts_and_thresholds();
DROP PROCEDURE IF EXISTS dwh.refresh_all_funnel_views();
DROP PROCEDURE IF EXISTS dwh.refresh_metric_aggregations();
DROP PROCEDURE IF EXISTS dwh.refresh_application_funnel_full();
DROP PROCEDURE IF EXISTS dwh.refresh_application_funnel();

DROP FUNCTION IF EXISTS dwh.get_stage_for_step(VARCHAR);
```

## PowerBI Views for Dashboard Consumption

Once deployed, PowerBI should connect to these 4 views:

| View | Dashboard | Usage |
|------|-----------|-------|
| `dwh.v_powerbi_funnel_executive` | Executive Dashboard | Conversion rates, time horizons, segments |
| `dwh.v_powerbi_funnel_operations` | Operations Dashboard | Current volume, exit branches, stuck apps |
| `dwh.v_powerbi_loss_analysis` | Loss Analysis Dashboard | Rejection reasons, drop-off categories |
| `dwh.v_powerbi_dealer_performance` | Dealer Dashboard | Top 10 dealer rankings |

## Deployment Order

1. **Phase 1:** `dim_funnel_stage.sql` → `v_application_events.sql` → `fact_application_funnel.sql`
2. **Phase 2:** `agg_daily_metrics.sql` + `agg_cohorts_stuck.sql` + `refresh_and_dashboards.sql`
3. **Phase 3:** `dim_rejection_phrase.sql` → `v_dropoff_responsibility.sql` → `agg_loss_dashboards.sql`
4. **Phase 4:** `dealer_performance.sql`
5. **Initial refresh:** `CALL dwh.refresh_all_funnel_views();`
6. **Schedule refresh:** `CALL dwh.refresh_metric_aggregations();` 3x daily

## SQL Files Location

All SQL files are in `.planning/phases/*/sql/`:
- `.planning/phases/01-data-foundation/sql/` (3 files)
- `.planning/phases/02-core-metrics/sql/` (3 files)
- `.planning/phases/03-loss-analysis/sql/` (3 files)
- `.planning/phases/04-operational-views/sql/` (1 file)

## Questions for DWH Owner

1. Should objects be created in `dwh` schema or a separate schema (e.g., `funnel_analytics`)?
2. Are there naming conventions for materialized views or procedures?
3. Who should schedule the 3x daily refresh procedure?
4. Any concerns with the estimated 10 MB storage footprint?

---

**Approval requested by:** Vincent Van Seumeren
**Date:** 2026-02-01
