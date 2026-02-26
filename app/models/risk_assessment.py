"""
Persistent audit table — every risk evaluation is stored.
Schema: lt_risk_engine.risk_assessment
"""
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Boolean, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class RiskAssessment(Base):
    __tablename__ = "risk_assessment"
    __table_args__ = {"schema": "lt_risk_engine"}

    assessment_id = Column(String(36), primary_key=True)
    request_id = Column(String(100), nullable=False, unique=True, index=True)
    contract_id = Column(String(100), nullable=False, index=True)
    customer_id = Column(String(100), nullable=False, index=True)

    # ── Scoring outputs ──
    model_version = Column(String(10), nullable=False)
    total_score = Column(Float, nullable=False)
    tier = Column(String(20), nullable=False)
    decision = Column(String(30), nullable=False)
    probability_of_default = Column(Float, nullable=True)

    # ── Factor breakdown (JSON for flexibility) ──
    factor_scores_json = Column(JSON, nullable=False)
    dscr_json = Column(JSON, nullable=False)
    business_rule_overrides_json = Column(JSON, nullable=True)

    # ── Legacy scorecard ──
    legacy_score = Column(Integer, nullable=True)
    legacy_band = Column(String(1), nullable=True)

    # ── Full request/response for replay ──
    request_payload = Column(JSON, nullable=False)
    response_payload = Column(JSON, nullable=False)

    # ── Metadata ──
    processing_time_ms = Column(Integer, nullable=False)
    evaluated_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<RiskAssessment {self.assessment_id} tier={self.tier} score={self.total_score}>"
