"""
002 — Calibration tables for rule/score management via UI

These tables store ALL scoring parameters so they can be recalibrated
quarterly through the web UI without code deployments.

Tables:
  - model_version: Snapshot of a published model config
  - scoring_factor_config: Factor metadata (name, weight, enabled)
  - scoring_factor_bins: Bin definitions per factor (boundaries, scores)
  - scoring_tier_thresholds: Tier definitions (thresholds, PD, decisions)
  - business_rules: Business rule definitions (conditions, enabled)
  - calibration_audit_log: Every change tracked for governance

Revision ID: 002
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

SCHEMA = "lt_risk_engine"


def upgrade() -> None:

    # ── Model Version (snapshot of a complete config) ──
    op.create_table(
        "model_version",
        sa.Column("version_id", sa.String(20), primary_key=True),  # e.g. "1.2.0", "1.2.1"
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),  # DRAFT | PUBLISHED | ARCHIVED
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.String(100), nullable=False),
        schema=SCHEMA,
    )

    # ── Factor Configuration ──
    op.create_table(
        "scoring_factor_config",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.String(20), sa.ForeignKey(f"{SCHEMA}.model_version.version_id"), nullable=False),
        sa.Column("factor_name", sa.String(50), nullable=False),  # LTV, Term, Age, CRIF, etc.
        sa.Column("weight", sa.Float, nullable=False),            # 0.15, 0.10, 0.05
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("score_range_min", sa.Float, nullable=True),    # for documentation: e.g. -8
        sa.Column("score_range_max", sa.Float, nullable=True),    # for documentation: e.g. +8
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_factor_config_version_factor",
        "scoring_factor_config", ["version_id", "factor_name"],
        unique=True, schema=SCHEMA,
    )

    # ── Factor Bin Definitions ──
    op.create_table(
        "scoring_factor_bins",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.String(20), sa.ForeignKey(f"{SCHEMA}.model_version.version_id"), nullable=False),
        sa.Column("factor_name", sa.String(50), nullable=False),
        sa.Column("bin_order", sa.Integer, nullable=False),       # display/evaluation order
        sa.Column("bin_label", sa.String(100), nullable=False),   # e.g. "75-85%", ">3 (Established)"
        sa.Column("lower_bound", sa.Float, nullable=True),        # NULL = open-ended
        sa.Column("upper_bound", sa.Float, nullable=True),        # NULL = open-ended
        sa.Column("lower_inclusive", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("upper_inclusive", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("match_value", sa.String(100), nullable=True),  # for categorical bins: "B2B", "C", etc.
        sa.Column("is_missing_bin", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("raw_score", sa.Float, nullable=False),         # the calibratable score!
        sa.Column("risk_interpretation", sa.String(200), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_factor_bins_version_factor",
        "scoring_factor_bins", ["version_id", "factor_name", "bin_order"],
        unique=True, schema=SCHEMA,
    )

    # ── Tier Thresholds ──
    op.create_table(
        "scoring_tier_thresholds",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.String(20), sa.ForeignKey(f"{SCHEMA}.model_version.version_id"), nullable=False),
        sa.Column("tier_name", sa.String(30), nullable=False),      # BRIGHT_GREEN, GREEN, YELLOW, RED
        sa.Column("tier_order", sa.Integer, nullable=False),         # evaluation order (1=highest)
        sa.Column("min_score", sa.Float, nullable=True),             # NULL = no lower bound (RED)
        sa.Column("decision", sa.String(30), nullable=False),        # AUTO_APPROVE, APPROVE_STANDARD, etc.
        sa.Column("estimated_pd", sa.Float, nullable=True),          # calibrated PD
        sa.Column("color_hex", sa.String(7), nullable=True),         # for UI: #27AE60
        sa.Column("description", sa.Text, nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_tier_version_tier",
        "scoring_tier_thresholds", ["version_id", "tier_name"],
        unique=True, schema=SCHEMA,
    )

    # ── Business Rules ──
    op.create_table(
        "business_rules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.String(20), sa.ForeignKey(f"{SCHEMA}.model_version.version_id"), nullable=False),
        sa.Column("rule_code", sa.String(10), nullable=False),       # BR-01, BR-02, ...
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("condition_field", sa.String(100), nullable=False), # e.g. "age", "ltv", "dscr_value"
        sa.Column("condition_operator", sa.String(10), nullable=False), # <, >, <=, >=, ==, !=
        sa.Column("condition_value", sa.String(100), nullable=False), # e.g. "18", "120", "0"
        sa.Column("forced_tier", sa.String(30), nullable=False, server_default="RED"),
        sa.Column("forced_decision", sa.String(30), nullable=False, server_default="DECLINE"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("severity", sa.String(20), nullable=False, server_default="HARD"),  # HARD = always force, SOFT = advisory
        schema=SCHEMA,
    )
    op.create_index(
        "ix_rules_version_code",
        "business_rules", ["version_id", "rule_code"],
        unique=True, schema=SCHEMA,
    )

    # ── Audit Log ──
    op.create_table(
        "calibration_audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.String(20), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),  # CREATED, UPDATED, PUBLISHED, ARCHIVED
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("record_id", sa.String(100), nullable=True),
        sa.Column("field_name", sa.String(100), nullable=True),
        sa.Column("old_value", sa.Text, nullable=True),
        sa.Column("new_value", sa.Text, nullable=True),
        sa.Column("changed_by", sa.String(100), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("change_reason", sa.Text, nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_audit_version", "calibration_audit_log", ["version_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_audit_changed_at", "calibration_audit_log", ["changed_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("calibration_audit_log", schema=SCHEMA)
    op.drop_table("business_rules", schema=SCHEMA)
    op.drop_table("scoring_tier_thresholds", schema=SCHEMA)
    op.drop_table("scoring_factor_bins", schema=SCHEMA)
    op.drop_table("scoring_factor_config", schema=SCHEMA)
    op.drop_table("model_version", schema=SCHEMA)
