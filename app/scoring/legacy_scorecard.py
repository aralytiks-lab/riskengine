"""
Legacy WoE Scorecard (A–E Risk Bands)

Original 6-factor logistic regression scorecard.
Kept for backward compatibility with existing reports and BAWAG reporting.

Intercept: 389
Score range: ~333 to ~502
Bands:  A (>428) → B (401-428) → C (381-400) → D (361-380) → E (≤360)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.schemas.risk_request import RiskEvaluationRequest


def compute_legacy_score(
    request: RiskEvaluationRequest,
    dscr_output,
) -> tuple[Optional[int], Optional[str]]:
    """
    Returns (points_total, band_letter) using the original WoE scorecard.
    """
    cust = request.customer
    contract = request.contract
    vehicle = request.vehicle

    score = 389  # intercept

    # ── LTV (financed_amt / vehicle_price) ──
    ltv = (contract.financed_amount / vehicle.vehicle_price * 100) if vehicle.vehicle_price > 0 else 100
    if 75 <= ltv <= 85:
        score += 15
    elif 85 < ltv <= 95:
        score += 7
    elif ltv < 75:
        score += 36
    else:  # >95%
        score -= 18

    # ── Term ──
    if 37 <= contract.term_months <= 48:
        score += 25
    elif contract.term_months > 48:
        score -= 7
    else:  # ≤36
        score += 22

    # ── Age ──
    age = (datetime.now().date() - cust.date_of_birth).days / 365.25
    if 18 <= age <= 25:
        score -= 16
    elif 26 <= age <= 35:
        score += 6
    elif 36 <= age <= 45:
        score -= 3
    elif 46 <= age <= 55:
        score += 28
    elif age >= 56:
        score -= 8

    # ── Intrum ──
    intrum = cust.intrum_score
    if intrum is None or intrum == 0:
        score -= 7
    elif intrum == 1:
        score += 1
    elif 1 < intrum <= 3:
        score -= 3
    elif intrum > 3:
        score += 8

    # ── Permit ──
    if cust.party_type.value == "B2B":
        score -= 6
    elif cust.permit_type and cust.permit_type.value == "B":
        score -= 5
    elif cust.permit_type and cust.permit_type.value == "C":
        score += 6
    else:
        score += 7  # Other_B2C

    # ── DSCR ──
    dscr = dscr_output.dscr_value
    if dscr is not None:
        if 0 <= dscr <= 3:
            score -= 1
        elif 3 < dscr <= 7:
            score += 0
        elif 7 < dscr <= 15:
            score -= 3
        elif dscr < 0:
            score -= 6
        elif dscr > 15:
            score += 9

    # ── Band assignment ──
    score = int(round(score))
    if score > 428:
        band = "A"
    elif score >= 401:
        band = "B"
    elif score >= 381:
        band = "C"
    elif score >= 361:
        band = "D"
    else:
        band = "E"

    return score, band
