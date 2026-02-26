"""
Response payload returned to Flowable.

Flowable uses: tier, decision, score, and override_reasons
to drive the business process (auto-approve / manual review / decline).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class RiskTier(str, Enum):
    BRIGHT_GREEN = "BRIGHT_GREEN"
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class Decision(str, Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    APPROVE_STANDARD = "APPROVE_STANDARD"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    DECLINE = "DECLINE"


class FactorScore(BaseModel):
    """Individual factor contribution to the total score."""
    factor_name: str
    raw_value: Optional[str] = None
    bin_label: str
    weight: float
    raw_score: float
    weighted_score: float


class DSCRResult(BaseModel):
    """DSCR calculation breakdown."""
    dscr_value: Optional[float] = None
    monthly_disposable_income: Optional[float] = None
    monthly_payment: float
    calculation_method: str = Field(description="B2B_EBITDA | B2C_NET_INCOME | FALLBACK")
    is_valid: bool = True


class BusinessRuleOverride(BaseModel):
    """When a hard business rule forces the tier to RED."""
    rule_code: str
    rule_description: str
    triggered_value: str


class RiskEvaluationResponse(BaseModel):
    """
    Returned to Flowable synchronously.
    """
    request_id: str
    assessment_id: str = Field(description="Internal UUID for audit trail")
    model_version: str

    # ── Primary outputs (what Flowable needs) ──
    total_score: float = Field(description="Composite score, range approx -75 to +53")
    tier: RiskTier
    decision: Decision
    probability_of_default: Optional[float] = Field(None, description="Calibrated PD estimate")

    # ── Breakdown ──
    factor_scores: list[FactorScore]
    dscr: DSCRResult
    business_rule_overrides: list[BusinessRuleOverride] = []

    # ── Metadata ──
    evaluated_at: datetime
    processing_time_ms: int

    # ── Legacy scorecard (A-E) for backward compatibility ──
    legacy_score: Optional[int] = Field(None, description="WoE scorecard points (333-502 range)")
    legacy_band: Optional[str] = Field(None, description="A/B/C/D/E band")
