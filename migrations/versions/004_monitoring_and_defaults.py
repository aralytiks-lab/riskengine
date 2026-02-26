"""
004 — Model monitoring, default value tracking, and historical performance tables

New tables:
  - scoring_defaults_applied: Tracks when NULL inputs required default substitution
  - population_segment_performance: Historical default rates per segment (from datahub ETL)
  - model_monitoring_snapshot: Periodic model performance metrics (Gini, KS, PSI)
  - dealer_risk_metrics: Dealer-level portfolio stats refreshed from datahub
  - woe_scorecard_params: Stores the logistic regression parameters (intercept, coefficients, points)

These tables support:
  1. Audit trail for default value substitution during scoring
  2. Periodic recalibration from datahub (historical portfolio performance)
  3. Model drift monitoring (actual vs predicted PD)
  4. Dealer risk metrics refresh pipeline

Revision ID: 004
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

SCHEMA = "lt_risk_engine"


def upgrade() -> None:

    # ══════════════════════════════════════════════════════════════
    # 1. DEFAULT VALUES APPLIED — audit trail for NULL substitution
    #    Every time a scoring request has a NULL field that gets a
    #    default value, we record it here for transparency.
    # ══════════════════════════════════════════════════════════════
    op.create_table(
        "scoring_defaults_applied",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "assessment_id",
            sa.String(36),
            sa.ForeignKey(f"{SCHEMA}.risk_assessment.assessment_id"),
            nullable=False,
        ),
        sa.Column("field_name", sa.String(100), nullable=False),       # e.g. "crif_score", "monthly_rent"
        sa.Column("original_value", sa.Text, nullable=True),            # what was received (NULL or empty)
        sa.Column("default_value", sa.Text, nullable=False),            # what was substituted
        sa.Column("default_source", sa.String(50), nullable=False),     # SYSTEM | CONFIG | POPULATION_MEAN
        sa.Column("factor_affected", sa.String(50), nullable=True),     # which factor was impacted
        sa.Column("impact_on_score", sa.Float, nullable=True),          # score delta vs if actual value existed
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_defaults_assessment_id",
        "scoring_defaults_applied", ["assessment_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_defaults_field_name",
        "scoring_defaults_applied", ["field_name"],
        schema=SCHEMA,
    )

    # ══════════════════════════════════════════════════════════════
    # 2. POPULATION SEGMENT PERFORMANCE — historical default rates
    #    Refreshed periodically from the datahub/ODS.
    #    Used for recalibration and drift detection.
    # ══════════════════════════════════════════════════════════════
    op.create_table(
        "population_segment_performance",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),            # when the snapshot was taken
        sa.Column("segment_type", sa.String(50), nullable=False),       # FACTOR_BIN | TIER | OVERALL
        sa.Column("segment_key", sa.String(100), nullable=False),       # e.g. "LTV:<75%", "TIER:GREEN"
        sa.Column("factor_name", sa.String(50), nullable=True),         # NULL for tier-level
        sa.Column("bin_label", sa.String(100), nullable=True),          # NULL for tier-level

        # Portfolio stats from datahub
        sa.Column("contract_count", sa.Integer, nullable=False),
        sa.Column("default_count", sa.Integer, nullable=False),
        sa.Column("observed_default_rate", sa.Float, nullable=False),   # actual DR from portfolio
        sa.Column("predicted_default_rate", sa.Float, nullable=True),   # what model predicted (avg PD)
        sa.Column("avg_score", sa.Float, nullable=True),                # average composite score
        sa.Column("avg_legacy_score", sa.Float, nullable=True),         # average legacy WoE score

        # For WoE recalibration
        sa.Column("observed_woe", sa.Float, nullable=True),             # ln(non-default / default) for the bin
        sa.Column("original_woe", sa.Float, nullable=True),             # WoE from dev sample
        sa.Column("woe_drift", sa.Float, nullable=True),                # observed - original

        # Metadata
        sa.Column("data_source", sa.String(100), nullable=False),       # e.g. "DATAHUB_ODS", "MANUAL"
        sa.Column("observation_window_months", sa.Integer, nullable=False, server_default="12"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.String(100), nullable=False, server_default="'system'"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_segment_perf_snapshot",
        "population_segment_performance", ["snapshot_date", "segment_type"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_segment_perf_factor",
        "population_segment_performance", ["factor_name", "bin_label"],
        schema=SCHEMA,
    )

    # ══════════════════════════════════════════════════════════════
    # 3. MODEL MONITORING SNAPSHOT — periodic model health metrics
    #    Computed from datahub data, tracks model discrimination
    #    power and calibration quality over time.
    # ══════════════════════════════════════════════════════════════
    op.create_table(
        "model_monitoring_snapshot",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("model_version", sa.String(20), nullable=False),
        sa.Column("scorecard_type", sa.String(20), nullable=False),     # V1_2_COMPOSITE | LEGACY_WOE

        # Discrimination metrics
        sa.Column("gini_coefficient", sa.Float, nullable=True),         # 0-1, higher = better
        sa.Column("ks_statistic", sa.Float, nullable=True),             # Kolmogorov-Smirnov
        sa.Column("auc_roc", sa.Float, nullable=True),                  # Area Under ROC

        # Calibration metrics
        sa.Column("overall_predicted_pd", sa.Float, nullable=True),
        sa.Column("overall_observed_dr", sa.Float, nullable=True),
        sa.Column("calibration_ratio", sa.Float, nullable=True),        # predicted / observed

        # Stability metrics
        sa.Column("psi_score", sa.Float, nullable=True),                # Population Stability Index
        sa.Column("psi_status", sa.String(20), nullable=True),          # STABLE | SHIFT | ALARM

        # Portfolio composition
        sa.Column("total_contracts", sa.Integer, nullable=False),
        sa.Column("total_defaults", sa.Integer, nullable=False),
        sa.Column("observation_window_months", sa.Integer, nullable=False),

        # Tier distribution
        sa.Column("tier_distribution_json", JSON, nullable=True),       # {"BRIGHT_GREEN": 0.42, "GREEN": 0.30, ...}

        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.String(100), nullable=False, server_default="'system'"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_monitoring_snapshot_date",
        "model_monitoring_snapshot", ["snapshot_date", "model_version"],
        unique=True, schema=SCHEMA,
    )

    # ══════════════════════════════════════════════════════════════
    # 4. DEALER RISK METRICS — refreshed from datahub
    #    Provides the dealer_default_rate that Flowable sends
    #    in the scoring request. Also tracks trends.
    # ══════════════════════════════════════════════════════════════
    op.create_table(
        "dealer_risk_metrics",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("dealer_id", sa.String(100), nullable=False),
        sa.Column("dealer_name", sa.String(200), nullable=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),

        # Current metrics
        sa.Column("active_contracts", sa.Integer, nullable=False),
        sa.Column("total_originated", sa.Integer, nullable=False),
        sa.Column("default_count", sa.Integer, nullable=False),
        sa.Column("current_default_rate", sa.Float, nullable=False),
        sa.Column("previous_default_rate", sa.Float, nullable=True),    # from prior snapshot
        sa.Column("default_rate_trend", sa.String(20), nullable=True),  # IMPROVING | STABLE | WORSENING

        # Volume & age
        sa.Column("active_months", sa.Integer, nullable=False),
        sa.Column("volume_tier", sa.String(20), nullable=True),         # BRONZE | SILVER | GOLD | PLATINUM
        sa.Column("avg_contract_size", sa.Float, nullable=True),

        # Risk flags
        sa.Column("is_watchlist", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("watchlist_reason", sa.Text, nullable=True),

        sa.Column("data_source", sa.String(100), nullable=False, server_default="'DATAHUB'"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_metrics_dealer",
        "dealer_risk_metrics", ["dealer_id", "snapshot_date"],
        unique=True, schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_metrics_watchlist",
        "dealer_risk_metrics", ["is_watchlist"],
        schema=SCHEMA,
    )

    # ══════════════════════════════════════════════════════════════
    # 5. WOE SCORECARD PARAMS — logistic regression parameters
    #    Stores the intercept, coefficients, and point allocations
    #    from the WoE model. Used by the legacy scorecard and
    #    referenced during recalibration.
    # ══════════════════════════════════════════════════════════════
    op.create_table(
        "woe_scorecard_params",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.String(20), sa.ForeignKey(f"{SCHEMA}.model_version.version_id"), nullable=False),
        sa.Column("param_type", sa.String(20), nullable=False),         # INTERCEPT | COEFFICIENT | BIN_POINTS
        sa.Column("factor_name", sa.String(50), nullable=True),         # NULL for INTERCEPT
        sa.Column("bin_label", sa.String(100), nullable=True),          # NULL for INTERCEPT and COEFFICIENT

        # Logistic regression values
        sa.Column("coefficient", sa.Float, nullable=True),              # logistic regression coefficient
        sa.Column("woe_value", sa.Float, nullable=True),                # Weight of Evidence for the bin
        sa.Column("points", sa.Float, nullable=False),                  # scaled scorecard points

        # Default rate context
        sa.Column("bin_default_rate", sa.Float, nullable=True),         # observed DR for this bin
        sa.Column("bin_count", sa.Integer, nullable=True),              # sample count in this bin
        sa.Column("bin_default_count", sa.Integer, nullable=True),      # defaults in this bin

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_woe_params_version",
        "woe_scorecard_params", ["version_id", "param_type", "factor_name"],
        schema=SCHEMA,
    )

    # ══════════════════════════════════════════════════════════════
    # 6. Add columns to risk_assessment for default tracking
    # ══════════════════════════════════════════════════════════════
    op.add_column(
        "risk_assessment",
        sa.Column("defaults_applied_count", sa.Integer, nullable=True, server_default="0"),
        schema=SCHEMA,
    )
    op.add_column(
        "risk_assessment",
        sa.Column("defaults_applied_json", JSON, nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "risk_assessment",
        sa.Column("dealer_id", sa.String(100), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "risk_assessment",
        sa.Column("source_system", sa.String(50), nullable=True, server_default="'SST'"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("risk_assessment", "source_system", schema=SCHEMA)
    op.drop_column("risk_assessment", "dealer_id", schema=SCHEMA)
    op.drop_column("risk_assessment", "defaults_applied_json", schema=SCHEMA)
    op.drop_column("risk_assessment", "defaults_applied_count", schema=SCHEMA)
    op.drop_table("woe_scorecard_params", schema=SCHEMA)
    op.drop_table("dealer_risk_metrics", schema=SCHEMA)
    op.drop_table("model_monitoring_snapshot", schema=SCHEMA)
    op.drop_table("population_segment_performance", schema=SCHEMA)
    op.drop_table("scoring_defaults_applied", schema=SCHEMA)
