"""
001 — Initial schema: risk_assessment table

Revision ID: 001
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS lt_risk_engine")

    op.create_table(
        "risk_assessment",
        sa.Column("assessment_id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(100), nullable=False, unique=True),
        sa.Column("contract_id", sa.String(100), nullable=False),
        sa.Column("customer_id", sa.String(100), nullable=False),

        sa.Column("model_version", sa.String(10), nullable=False),
        sa.Column("total_score", sa.Float, nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("probability_of_default", sa.Float, nullable=True),

        sa.Column("factor_scores_json", JSON, nullable=False),
        sa.Column("dscr_json", JSON, nullable=False),
        sa.Column("business_rule_overrides_json", JSON, nullable=True),

        sa.Column("legacy_score", sa.Integer, nullable=True),
        sa.Column("legacy_band", sa.String(1), nullable=True),

        sa.Column("request_payload", JSON, nullable=False),
        sa.Column("response_payload", JSON, nullable=False),

        sa.Column("processing_time_ms", sa.Integer, nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        schema="lt_risk_engine",
    )

    op.create_index("ix_risk_assessment_request_id", "risk_assessment", ["request_id"], schema="lt_risk_engine")
    op.create_index("ix_risk_assessment_contract_id", "risk_assessment", ["contract_id"], schema="lt_risk_engine")
    op.create_index("ix_risk_assessment_customer_id", "risk_assessment", ["customer_id"], schema="lt_risk_engine")
    op.create_index("ix_risk_assessment_tier", "risk_assessment", ["tier"], schema="lt_risk_engine")
    op.create_index("ix_risk_assessment_evaluated_at", "risk_assessment", ["evaluated_at"], schema="lt_risk_engine")


def downgrade() -> None:
    op.drop_table("risk_assessment", schema="lt_risk_engine")
