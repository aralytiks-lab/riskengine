"""
Migration 004: Expanded data model for historical data integration,
WoE scorecard parameters, model monitoring, and full audit trail.

Adds:
  - lt_risk_engine.scoring_factor_bins     (WoE/scorecard config, seeds v1.2 data)
  - lt_risk_engine.model_version           (version control for scorecard config)
  - lt_risk_engine.risk_assessment         (extended: stores full input + output JSON)
  - lt_risk_engine.applied_defaults        (tracks missing field fallbacks per scoring)
  - lt_risk_engine.dealer_risk_metrics     (refreshed nightly from DWH - dealer DR%)
  - lt_risk_engine.portfolio_segment_metrics (quarterly vintage metrics for recalibration)
  - lt_risk_engine.model_performance       (actual vs predicted PD for monitoring)

Revision ID: 004
Revises: 003
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    # ─────────────────────────────────────────────
    # 1. MODEL VERSION TABLE
    # ─────────────────────────────────────────────
    op.create_table(
        'model_version',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('version_code', sa.String(20), nullable=False, unique=True),  # e.g. 'v1.2'
        sa.Column('description', sa.Text),
        sa.Column('intercept', sa.Numeric(10, 4), nullable=False, default=0),   # WoE intercept (+389 for legacy)
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('activated_at', sa.DateTime, default=datetime.utcnow),
        sa.Column('created_by', sa.String(100)),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        schema='lt_risk_engine'
    )

    # ─────────────────────────────────────────────
    # 2. SCORING FACTOR BINS TABLE (scorecard config)
    # ─────────────────────────────────────────────
    op.create_table(
        'scoring_factor_bins',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('model_version_id', sa.Integer,
                  sa.ForeignKey('lt_risk_engine.model_version.id'), nullable=False),
        sa.Column('factor_name', sa.String(50), nullable=False),  # e.g. 'LTV', 'DSCR'
        sa.Column('bin_label', sa.String(50), nullable=False),    # e.g. '75-85%', '>15'
        sa.Column('bin_min', sa.Numeric(15, 4)),                  # numeric lower bound (NULL = open)
        sa.Column('bin_max', sa.Numeric(15, 4)),                  # numeric upper bound (NULL = open)
        sa.Column('category_value', sa.String(50)),               # for categorical: 'B2B', 'C_permit' etc.
        sa.Column('woe', sa.Numeric(10, 4)),                      # Weight of Evidence
        sa.Column('observed_default_rate', sa.Numeric(8, 4)),     # from dev sample
        sa.Column('sample_count', sa.Integer),                    # N in dev sample
        sa.Column('coefficient', sa.Numeric(10, 4)),              # logistic regression coeff
        sa.Column('points', sa.Integer, nullable=False),          # scorecard points (+/-)
        sa.Column('weight', sa.Numeric(8, 4)),                    # for v1.2 weighted model
        sa.Column('effective_from', sa.Date, nullable=False),
        sa.Column('effective_to', sa.Date),                       # NULL = currently active
        schema='lt_risk_engine'
    )
    op.create_index(
        'ix_sfb_model_factor',
        'scoring_factor_bins',
        ['model_version_id', 'factor_name'],
        schema='lt_risk_engine'
    )

    # ─────────────────────────────────────────────
    # 3. RISK ASSESSMENT TABLE (extended)
    #    Drop and recreate with full audit columns
    # ─────────────────────────────────────────────
    # If table already exists from migration 001, we alter it rather than recreate.
    # Adding missing columns:
    op.add_column('risk_assessment',
        sa.Column('model_version_id', sa.Integer,
                  sa.ForeignKey('lt_risk_engine.model_version.id')),
        schema='lt_risk_engine')
    op.add_column('risk_assessment',
        sa.Column('input_json', JSONB),  # full raw input payload from Flowable
        schema='lt_risk_engine')
    op.add_column('risk_assessment',
        sa.Column('output_json', JSONB),  # full response returned to Flowable
        schema='lt_risk_engine')
    op.add_column('risk_assessment',
        sa.Column('factor_scores_json', JSONB),  # each factor: {name, bin, points, weight}
        schema='lt_risk_engine')
    op.add_column('risk_assessment',
        sa.Column('rules_triggered_json', JSONB),  # list of triggered business rules
        schema='lt_risk_engine')
    op.add_column('risk_assessment',
        sa.Column('composite_score', sa.Numeric(8, 2)),
        schema='lt_risk_engine')
    op.add_column('risk_assessment',
        sa.Column('legacy_score', sa.Integer),  # WoE scorecard A-E score
        schema='lt_risk_engine')
    op.add_column('risk_assessment',
        sa.Column('legacy_band', sa.String(2)),  # A/B/C/D/E
        schema='lt_risk_engine')
    op.add_column('risk_assessment',
        sa.Column('processing_ms', sa.Integer),  # scoring latency
        schema='lt_risk_engine')
    op.add_column('risk_assessment',
        sa.Column('idempotency_key', sa.String(100)),  # from Flowable header
        schema='lt_risk_engine')
    op.add_column('risk_assessment',
        sa.Column('flowable_process_id', sa.String(100)),
        schema='lt_risk_engine')
    op.create_index(
        'ix_ra_idempotency',
        'risk_assessment',
        ['idempotency_key'],
        schema='lt_risk_engine',
        unique=True
    )

    # ─────────────────────────────────────────────
    # 4. APPLIED DEFAULTS TABLE
    #    Records every missing field that used a fallback value
    # ─────────────────────────────────────────────
    op.create_table(
        'applied_defaults',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('assessment_id', sa.Integer,
                  sa.ForeignKey('lt_risk_engine.risk_assessment.id',
                                ondelete='CASCADE'), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=False),    # e.g. 'crif_score'
        sa.Column('expected_source', sa.String(100)),               # 'SST', 'CRIF_API', 'INTRUM_API'
        sa.Column('default_value_used', sa.String(200)),            # the fallback applied
        sa.Column('fallback_reason', sa.Text),                      # 'field_null', 'api_timeout', etc.
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        schema='lt_risk_engine'
    )
    op.create_index(
        'ix_ad_assessment',
        'applied_defaults',
        ['assessment_id'],
        schema='lt_risk_engine'
    )

    # ─────────────────────────────────────────────
    # 5. DEALER RISK METRICS TABLE
    #    Refreshed nightly from DWH dwh.dim_contract
    #    Used by DealerRisk factor at scoring time
    # ─────────────────────────────────────────────
    op.create_table(
        'dealer_risk_metrics',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('dealer_id', sa.Integer, nullable=False),
        sa.Column('dealer_name', sa.String(200)),
        sa.Column('total_contracts', sa.Integer),
        sa.Column('defaults_90dpd', sa.Integer),     # contracts with DPD >= 90
        sa.Column('write_offs', sa.Integer),         # contracts with wo_amt > 0
        sa.Column('default_rate_pct', sa.Numeric(6, 2)),  # DR% used in scoring
        sa.Column('avg_financed_amt', sa.Numeric(12, 2)),
        sa.Column('as_of_date', sa.Date, nullable=False),
        sa.Column('is_current', sa.Boolean, default=True),
        sa.Column('refreshed_at', sa.DateTime, default=datetime.utcnow),
        schema='lt_risk_engine'
    )
    op.create_index(
        'ix_drm_dealer_current',
        'dealer_risk_metrics',
        ['dealer_id', 'is_current'],
        schema='lt_risk_engine'
    )

    # ─────────────────────────────────────────────
    # 6. PORTFOLIO SEGMENT METRICS TABLE
    #    Quarterly aggregates per risk feature bin
    #    Used by batch recalibration / model monitoring
    # ─────────────────────────────────────────────
    op.create_table(
        'portfolio_segment_metrics',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('as_of_quarter', sa.Date, nullable=False),   # e.g. 2025-10-01
        sa.Column('segment_type', sa.String(50)),               # 'LTV_BIN', 'VINTAGE', 'DEALER', 'OVERALL'
        sa.Column('segment_label', sa.String(100)),             # e.g. '75-85%', '2024-Q1'
        sa.Column('total_contracts', sa.Integer),
        sa.Column('defaults_count', sa.Integer),
        sa.Column('observed_default_rate', sa.Numeric(8, 4)),  # actual DR in this segment
        sa.Column('model_predicted_pd', sa.Numeric(8, 4)),     # what the model predicted
        sa.Column('avg_composite_score', sa.Numeric(8, 2)),
        sa.Column('gini_coefficient', sa.Numeric(6, 4)),
        sa.Column('ks_statistic', sa.Numeric(6, 4)),
        sa.Column('refreshed_at', sa.DateTime, default=datetime.utcnow),
        schema='lt_risk_engine'
    )

    # ─────────────────────────────────────────────
    # 7. MODEL PERFORMANCE / MONITORING TABLE
    #    Tracks actual vs predicted at assessment level
    #    Populated retrospectively via batch job
    # ─────────────────────────────────────────────
    op.create_table(
        'model_performance',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('assessment_id', sa.Integer,
                  sa.ForeignKey('lt_risk_engine.risk_assessment.id',
                                ondelete='SET NULL')),
        sa.Column('contract_number', sa.String(50)),
        sa.Column('score_date', sa.Date),
        sa.Column('model_version_id', sa.Integer,
                  sa.ForeignKey('lt_risk_engine.model_version.id')),
        sa.Column('predicted_tier', sa.String(20)),         # BRIGHT_GREEN/GREEN/YELLOW/RED
        sa.Column('predicted_pd', sa.Numeric(8, 4)),        # model's probability of default
        sa.Column('composite_score_at_scoring', sa.Numeric(8, 2)),
        sa.Column('observed_default', sa.Boolean),          # populated retrospectively
        sa.Column('observed_dpd_max', sa.Integer),          # max DPD observed in 12m
        sa.Column('observed_dpd_at_12m', sa.Integer),
        sa.Column('write_off_flag', sa.Boolean),
        sa.Column('outcome_updated_at', sa.DateTime),       # when batch job set observed_default
        sa.Column('months_on_book', sa.Integer),            # at time of outcome capture
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        schema='lt_risk_engine'
    )
    op.create_index(
        'ix_mp_contract',
        'model_performance',
        ['contract_number', 'score_date'],
        schema='lt_risk_engine'
    )


def downgrade():
    for table in ['model_performance', 'portfolio_segment_metrics',
                  'dealer_risk_metrics', 'applied_defaults']:
        op.drop_table(table, schema='lt_risk_engine')

    for col in ['model_version_id', 'input_json', 'output_json', 'factor_scores_json',
                'rules_triggered_json', 'composite_score', 'legacy_score', 'legacy_band',
                'processing_ms', 'idempotency_key', 'flowable_process_id']:
        op.drop_column('risk_assessment', col, schema='lt_risk_engine')

    op.drop_table('scoring_factor_bins', schema='lt_risk_engine')
    op.drop_table('model_version', schema='lt_risk_engine')
