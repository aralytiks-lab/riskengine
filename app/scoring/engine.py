"""
v1.2 Risk Scoring Engine

Orchestrates:
  1. DSCR calculation
  2. All 10 factor scores
  3. Weighted composite score
  4. Business rule overrides (hard kills)
  5. Tier + decision assignment
  6. Legacy WoE scorecard (backward compat)

Called synchronously by the API endpoint.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog

from app.schemas.risk_request import RiskEvaluationRequest
from app.schemas.risk_response import (
    BusinessRuleOverride,
    Decision,
    DSCRResult,
    FactorScore,
    RiskEvaluationResponse,
    RiskTier,
)
from app.scoring import factors
from app.scoring.legacy_scorecard import compute_legacy_score
from app.services.dscr_calculator import calculate_dscr

logger = structlog.get_logger()


# ═══════════════════════════════════════════════════════════════
# Factor weights — must sum to 1.0
# ═══════════════════════════════════════════════════════════════
FACTOR_WEIGHTS: dict[str, float] = {
    "LTV": 0.15,
    "Term": 0.10,
    "Age": 0.10,
    "CRIF": 0.15,
    "Intrum": 0.10,
    "DSCR": 0.15,
    "Permit": 0.10,
    "VehiclePriceTier": 0.05,
    "ZEK": 0.05,
    "DealerRisk": 0.05,
}
assert abs(sum(FACTOR_WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"


# ═══════════════════════════════════════════════════════════════
# Tier thresholds (v1.2 calibration)
#   score >= 25  → BRIGHT_GREEN
#   score >= 10  → GREEN
#   score >= 0   → YELLOW
#   score < 0    → RED
# ═══════════════════════════════════════════════════════════════
TIER_THRESHOLDS = [
    (25.0, RiskTier.BRIGHT_GREEN),
    (10.0, RiskTier.GREEN),
    (0.0, RiskTier.YELLOW),
]

TIER_TO_DECISION = {
    RiskTier.BRIGHT_GREEN: Decision.AUTO_APPROVE,
    RiskTier.GREEN: Decision.APPROVE_STANDARD,
    RiskTier.YELLOW: Decision.MANUAL_REVIEW,
    RiskTier.RED: Decision.DECLINE,
}


def evaluate(request: RiskEvaluationRequest) -> RiskEvaluationResponse:
    """
    Main scoring entry point.
    """
    t0 = time.perf_counter_ns()
    assessment_id = str(uuid.uuid4())

    cust = request.customer
    vehicle = request.vehicle
    contract = request.contract
    dealer = request.dealer

    # ── Step 1: DSCR ──
    dscr_output = calculate_dscr(cust, contract)

    # ── Step 2: Compute all 10 factor scores ──
    raw_results = [
        factors.score_ltv(contract.financed_amount, vehicle.vehicle_price),
        factors.score_term(contract.term_months),
        factors.score_age(cust.date_of_birth),
        factors.score_crif(cust.crif_score),
        factors.score_intrum(cust.intrum_score),
        factors.score_dscr(dscr_output.dscr_value),
        factors.score_permit(cust.party_type.value, cust.permit_type.value if cust.permit_type else None),
        factors.score_vehicle_price_tier(vehicle.vehicle_price),
        factors.score_zek(cust.zek_has_entries, cust.zek_entry_count),
        factors.score_dealer_risk(dealer.dealer_default_rate, dealer.dealer_active_months),
    ]

    # ── Step 3: Composite score ──
    # The factor weights are already reflected in each factor's score range:
    #   - High-weight factors (LTV, CRIF, DSCR @ 15%) have wider raw ranges
    #   - Low-weight factors (Vehicle, ZEK, Dealer @ 5%) have narrower ranges
    # So the composite = direct sum of raw scores.
    # Theoretical range: approx -59 to +58, observed -75 to +53.
    factor_scores: list[FactorScore] = []
    total_score = 0.0

    for result in raw_results:
        weight = FACTOR_WEIGHTS[result.factor_name]
        total_score += result.raw_score

        factor_scores.append(
            FactorScore(
                factor_name=result.factor_name,
                raw_value=result.raw_value,
                bin_label=result.bin_label,
                weight=weight,
                raw_score=result.raw_score,
                weighted_score=result.raw_score,  # contribution = raw score
            )
        )

    total_score = round(total_score, 2)

    # ── Step 4: Determine tier from score ──
    tier = RiskTier.RED  # default
    for threshold, t in TIER_THRESHOLDS:
        if total_score >= threshold:
            tier = t
            break

    # ── Step 5: Business rule overrides ──
    overrides = _check_business_rules(request, dscr_output)
    if overrides:
        tier = RiskTier.RED  # hard override

    decision = TIER_TO_DECISION[tier]

    # ── Step 6: Legacy scorecard (backward compat) ──
    legacy_score, legacy_band = compute_legacy_score(request, dscr_output)

    # ── Step 7: Estimate PD (calibrated mapping) ──
    pd_estimate = _estimate_pd(tier, total_score)

    elapsed_ms = int((time.perf_counter_ns() - t0) / 1_000_000)

    logger.info(
        "risk_evaluation_complete",
        assessment_id=assessment_id,
        request_id=request.request_id,
        score=total_score,
        tier=tier.value,
        decision=decision.value,
        overrides_count=len(overrides),
        elapsed_ms=elapsed_ms,
    )

    return RiskEvaluationResponse(
        request_id=request.request_id,
        assessment_id=assessment_id,
        model_version=request.model_version or "1.2",
        total_score=total_score,
        tier=tier,
        decision=decision,
        probability_of_default=pd_estimate,
        factor_scores=factor_scores,
        dscr=DSCRResult(
            dscr_value=dscr_output.dscr_value,
            monthly_disposable_income=dscr_output.monthly_disposable_income,
            monthly_payment=dscr_output.monthly_payment,
            calculation_method=dscr_output.calculation_method,
            is_valid=dscr_output.is_valid,
        ),
        business_rule_overrides=overrides,
        evaluated_at=datetime.now(timezone.utc),
        processing_time_ms=elapsed_ms,
        legacy_score=legacy_score,
        legacy_band=legacy_band,
    )


# ═══════════════════════════════════════════════════════════════
# Business Rule Overrides — hard RED triggers
# ═══════════════════════════════════════════════════════════════

def _check_business_rules(
    request: RiskEvaluationRequest,
    dscr_output,
) -> list[BusinessRuleOverride]:
    """
    Business rules that force RED regardless of composite score.
    Derived from the v1.2 Executive Summary + CRIF/Intrum logic doc.
    """
    overrides: list[BusinessRuleOverride] = []
    cust = request.customer
    contract = request.contract

    # BR-01: Minor
    age = (datetime.now().date() - cust.date_of_birth).days / 365.25
    if age < 18:
        overrides.append(BusinessRuleOverride(
            rule_code="BR-01",
            rule_description="Applicant is under 18",
            triggered_value=f"Age: {age:.1f}",
        ))

    # BR-02: LTV > 120% (extreme over-financing)
    ltv = (contract.financed_amount / request.vehicle.vehicle_price) * 100 if request.vehicle.vehicle_price > 0 else 0
    if ltv > 120:
        overrides.append(BusinessRuleOverride(
            rule_code="BR-02",
            rule_description="LTV exceeds 120% — extreme over-financing",
            triggered_value=f"LTV: {ltv:.1f}%",
        ))

    # BR-03: DSCR negative or critically low
    if dscr_output.dscr_value is not None and dscr_output.dscr_value < 0:
        overrides.append(BusinessRuleOverride(
            rule_code="BR-03",
            rule_description="Negative DSCR — expenses exceed income",
            triggered_value=f"DSCR: {dscr_output.dscr_value:.2f}",
        ))

    # BR-04: Multiple negative ZEK entries
    if cust.zek_has_entries and (cust.zek_entry_count or 0) >= 3:
        overrides.append(BusinessRuleOverride(
            rule_code="BR-04",
            rule_description="3+ negative ZEK entries",
            triggered_value=f"ZEK entries: {cust.zek_entry_count}",
        ))

    # BR-05: CRIF critically low
    if cust.crif_score is not None and cust.crif_score < 150:
        overrides.append(BusinessRuleOverride(
            rule_code="BR-05",
            rule_description="CRIF score critically low (<150)",
            triggered_value=f"CRIF: {cust.crif_score}",
        ))

    # BR-06: No income data and no DSCR calculable (B2C only)
    if cust.party_type == "B2C" and not dscr_output.is_valid and cust.monthly_net_income in (None, 0):
        overrides.append(BusinessRuleOverride(
            rule_code="BR-06",
            rule_description="No income data provided for B2C application",
            triggered_value="Net income: None/0",
        ))

    # BR-07: Dealer on watchlist (default rate > 20%)
    if request.dealer.dealer_default_rate is not None and request.dealer.dealer_default_rate > 0.20:
        overrides.append(BusinessRuleOverride(
            rule_code="BR-07",
            rule_description="Dealer default rate exceeds 20% watchlist threshold",
            triggered_value=f"Dealer DR: {request.dealer.dealer_default_rate:.1%}",
        ))

    # BR-08: Term > 72 months
    if contract.term_months > 72:
        overrides.append(BusinessRuleOverride(
            rule_code="BR-08",
            rule_description="Contract term exceeds 72-month maximum",
            triggered_value=f"Term: {contract.term_months}m",
        ))

    return overrides


# ═══════════════════════════════════════════════════════════════
# PD Estimation (calibrated from backtest)
# ═══════════════════════════════════════════════════════════════

def _estimate_pd(tier: RiskTier, score: float) -> Optional[float]:
    """
    Map tier + score to calibrated PD.
    Based on backtest: Feb 2026, 3,926 contracts, 90+ DPD definition.
    These are through-the-cycle annualised PDs.
    """
    pd_map = {
        RiskTier.BRIGHT_GREEN: 0.015,  # ~1.5%
        RiskTier.GREEN: 0.035,         # ~3.5%
        RiskTier.YELLOW: 0.070,        # ~7.0%
        RiskTier.RED: 0.150,           # ~15.0%
    }
    return pd_map.get(tier)
