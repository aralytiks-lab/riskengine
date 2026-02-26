# Funnel Analytics Deployment Package

**Prepared by:** Vincent Van Seumeren
**Date:** 2026-02-01
**For:** DWH Team

## Summary

This package contains SQL scripts to create a funnel analytics system in the `dwh` schema. These objects enable PowerBI dashboards for application funnel visibility.

**Impact:** Additive only - no existing tables or views are modified.

## Package Contents

| Document | Purpose |
|----------|---------|
| `BUSINESS_SPECIFICATIONS.md` | **Start here** - Business context, funnel definitions, metric explanations |
| `DEPLOYMENT_APPROVAL.md` | Approval request with object inventory and impact assessment |
| `00_FULL_DEPLOYMENT.sql` | Consolidated SQL script for deployment |
| `ROLLBACK.sql` | Complete removal script |
| `README.md` | This file - deployment instructions |

## What Gets Created

| Category | Count | Purpose |
|----------|-------|---------|
| Tables | 2 | Dimension tables for funnel stages and rejection phrases |
| Regular Views | 12+ | Mapping views, helper views, PowerBI wrapper views |
| Materialized Views | 6 | Pre-aggregated metrics for fast dashboard queries |
| Procedures | 8 | Refresh orchestration for daily updates |
| Functions | 1 | Helper function for step-to-stage lookup |

**Storage estimate:** ~10 MB total

## Deployment Instructions

### Option 1: Run the Consolidated Script (Recommended)

Execute the single consolidated script in order:

```bash
psql -h <host> -U <user> -d prod_dwh -f 00_FULL_DEPLOYMENT.sql
```

### Option 2: Run Phase-by-Phase

Execute in this exact order:

```bash
# Phase 1: Foundation (must be first)
psql -f 01_dim_funnel_stage.sql
psql -f 02_v_application_events.sql
psql -f 03_fact_application_funnel.sql

# Phase 2: Core Metrics (depends on Phase 1)
psql -f 04_agg_daily_metrics.sql
psql -f 05_agg_cohorts_stuck.sql
psql -f 06_refresh_and_dashboards.sql

# Phase 3: Loss Analysis (depends on Phases 1-2)
psql -f 07_dim_rejection_phrase.sql
psql -f 08_v_dropoff_responsibility.sql
psql -f 09_agg_loss_dashboards.sql

# Phase 4: Dealer Performance (depends on Phase 1)
psql -f 10_dealer_performance.sql
```

### Post-Deployment

After all objects are created:

```sql
-- Initial data load (required - populates all materialized views)
CALL dwh.refresh_all_funnel_views();

-- Verify row counts
SELECT COUNT(*) FROM dwh.mv_fact_application_funnel;
SELECT COUNT(*) FROM dwh.mv_agg_daily_metrics;
```

## Scheduling

Set up a scheduled job to call this procedure 3x daily (e.g., 7am, 1pm, 6pm):

```sql
CALL dwh.refresh_metric_aggregations();
```

This refreshes all aggregation MVs concurrently (non-blocking).

## PowerBI Views

Connect PowerBI to these 4 views:

| View | Dashboard | Usage |
|------|-----------|-------|
| `dwh.v_powerbi_funnel_executive` | Executive | Conversion rates, time horizons |
| `dwh.v_powerbi_funnel_operations` | Operations | Current volume, stuck apps |
| `dwh.v_powerbi_loss_analysis` | Loss Analysis | Rejection reasons, drop-offs |
| `dwh.v_powerbi_dealer_performance` | Dealer | Top 10 dealer rankings |

## Rollback

To completely remove all objects:

```sql
-- Run the rollback script
\i ROLLBACK.sql
```

## Questions?

Contact Vincent Van Seumeren for clarification on any requirements.
