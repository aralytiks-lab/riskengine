"""
v1.2 Scoring Model — 10 Factor Definitions

Each factor:
  1. Takes raw input from the request payload
  2. Maps it to a bin
  3. Returns a raw score for that bin

Weights are applied in the engine, not here.

Score ranges and bins are derived from:
  - B2C Credit Scoring Model v1.2 — Executive Summary
  - WoE analysis on the LeaseTeq portfolio (2,461 dev sample)
  - Backtest on full 3,930 portfolio (validated Feb 2026)

Convention: HIGHER score = LOWER risk (positive is good).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class FactorResult:
    factor_name: str
    raw_value: str
    bin_label: str
    raw_score: float


# ═══════════════════════════════════════════════════════════════
# 1. LTV  (weight = 0.15)
#    LTV = financed_amount / vehicle_price
# ═══════════════════════════════════════════════════════════════
def score_ltv(financed_amount: float, vehicle_price: float) -> FactorResult:
    if vehicle_price <= 0:
        return FactorResult("LTV", "N/A", "MISSING", -5.0)

    ltv = (financed_amount / vehicle_price) * 100

    if ltv < 75:
        return FactorResult("LTV", f"{ltv:.1f}%", "<75%", 8.0)
    elif ltv <= 85:
        return FactorResult("LTV", f"{ltv:.1f}%", "75-85%", 4.0)
    elif ltv <= 95:
        return FactorResult("LTV", f"{ltv:.1f}%", "85-95%", 0.0)
    else:
        return FactorResult("LTV", f"{ltv:.1f}%", ">95%", -8.0)


# ═══════════════════════════════════════════════════════════════
# 2. TERM LENGTH  (weight = 0.10)
# ═══════════════════════════════════════════════════════════════
def score_term(term_months: int) -> FactorResult:
    if term_months <= 36:
        return FactorResult("Term", f"{term_months}m", "≤36m", 5.0)
    elif term_months <= 48:
        return FactorResult("Term", f"{term_months}m", "37-48m", 6.0)
    else:
        return FactorResult("Term", f"{term_months}m", ">48m", -3.0)


# ═══════════════════════════════════════════════════════════════
# 3. CUSTOMER AGE  (weight = 0.10)
# ═══════════════════════════════════════════════════════════════
def score_age(date_of_birth: date, reference_date: Optional[date] = None) -> FactorResult:
    ref = reference_date or date.today()
    age = (ref - date_of_birth).days / 365.25

    if age < 18:
        return FactorResult("Age", f"{age:.0f}", "<18 (minor)", -10.0)
    elif age <= 25:
        return FactorResult("Age", f"{age:.0f}", "18-25", -6.0)
    elif age <= 35:
        return FactorResult("Age", f"{age:.0f}", "26-35", 2.0)
    elif age <= 45:
        return FactorResult("Age", f"{age:.0f}", "36-45", 0.0)
    elif age <= 55:
        return FactorResult("Age", f"{age:.0f}", "46-55", 7.0)
    else:
        return FactorResult("Age", f"{age:.0f}", "56+", -2.0)


# ═══════════════════════════════════════════════════════════════
# 4. CRIF SCORE  (weight = 0.15)
#    External bureau score 0-1000, higher = better
# ═══════════════════════════════════════════════════════════════
def score_crif(crif_score: Optional[int]) -> FactorResult:
    if crif_score is None:
        return FactorResult("CRIF", "N/A", "MISSING", -5.0)

    if crif_score >= 700:
        return FactorResult("CRIF", str(crif_score), "≥700 (Excellent)", 8.0)
    elif crif_score >= 500:
        return FactorResult("CRIF", str(crif_score), "500-699 (Good)", 4.0)
    elif crif_score >= 300:
        return FactorResult("CRIF", str(crif_score), "300-499 (Fair)", -2.0)
    else:
        return FactorResult("CRIF", str(crif_score), "<300 (Poor)", -8.0)


# ═══════════════════════════════════════════════════════════════
# 5. INTRUM SCORE  (weight = 0.10)
#    Swiss debt collection score: higher = more entries = BETTER
#    0 = no Intrum data (risky), >3 = established track record
# ═══════════════════════════════════════════════════════════════
def score_intrum(intrum_score: Optional[int]) -> FactorResult:
    if intrum_score is None or intrum_score == 0:
        return FactorResult("Intrum", str(intrum_score or 0), "0 (No data)", -4.0)
    elif intrum_score == 1:
        return FactorResult("Intrum", str(intrum_score), "1", 1.0)
    elif intrum_score <= 3:
        return FactorResult("Intrum", str(intrum_score), "2-3", -1.0)
    else:
        return FactorResult("Intrum", str(intrum_score), ">3 (Established)", 5.0)


# ═══════════════════════════════════════════════════════════════
# 6. DSCR  (weight = 0.15)
#    Debt Service Coverage Ratio — computed by dscr_calculator
# ═══════════════════════════════════════════════════════════════
def score_dscr(dscr_value: Optional[float]) -> FactorResult:
    if dscr_value is None:
        return FactorResult("DSCR", "N/A", "MISSING", -5.0)

    if dscr_value < 0:
        return FactorResult("DSCR", f"{dscr_value:.2f}", "<0 (Negative)", -8.0)
    elif dscr_value <= 3:
        return FactorResult("DSCR", f"{dscr_value:.2f}", "0-3 (Tight)", -3.0)
    elif dscr_value <= 7:
        return FactorResult("DSCR", f"{dscr_value:.2f}", "3-7 (Adequate)", 0.0)
    elif dscr_value <= 15:
        return FactorResult("DSCR", f"{dscr_value:.2f}", "7-15 (Good)", 3.0)
    else:
        return FactorResult("DSCR", f"{dscr_value:.2f}", ">15 (Strong)", 7.0)


# ═══════════════════════════════════════════════════════════════
# 7. PERMIT TYPE  (weight = 0.10)
#    Combined party_type + permit for B2C
# ═══════════════════════════════════════════════════════════════
def score_permit(party_type: str, permit_type: Optional[str]) -> FactorResult:
    if party_type == "B2B":
        return FactorResult("Permit", "B2B", "B2B", -3.0)

    # B2C path
    permit = (permit_type or "Unknown").upper()

    if permit == "C":
        return FactorResult("Permit", "C_permit", "C_permit", 5.0)
    elif permit == "B":
        return FactorResult("Permit", "B_permit", "B_permit", -3.0)
    elif permit in ("L", "DIPLOMAT"):
        return FactorResult("Permit", permit, permit, -1.0)
    else:
        # Unknown / NULL — large portion of portfolio
        return FactorResult("Permit", "Unknown", "Other_B2C", 2.0)


# ═══════════════════════════════════════════════════════════════
# 8. VEHICLE PRICE TIER  (weight = 0.05)
#    Risk varies by price segment of the collateral
# ═══════════════════════════════════════════════════════════════
def score_vehicle_price_tier(vehicle_price: float) -> FactorResult:
    if vehicle_price <= 20_000:
        return FactorResult("VehiclePriceTier", f"{vehicle_price:.0f}", "≤20k (Economy)", -2.0)
    elif vehicle_price <= 50_000:
        return FactorResult("VehiclePriceTier", f"{vehicle_price:.0f}", "20k-50k (Mid)", 3.0)
    elif vehicle_price <= 100_000:
        return FactorResult("VehiclePriceTier", f"{vehicle_price:.0f}", "50k-100k (Premium)", 2.0)
    else:
        return FactorResult("VehiclePriceTier", f"{vehicle_price:.0f}", ">100k (Luxury)", -1.0)


# ═══════════════════════════════════════════════════════════════
# 9. ZEK PROFILE  (weight = 0.05)
#    Swiss central credit information bureau
# ═══════════════════════════════════════════════════════════════
def score_zek(has_entries: Optional[bool], entry_count: Optional[int] = None) -> FactorResult:
    if has_entries is None:
        return FactorResult("ZEK", "N/A", "NOT_CHECKED", 0.0)

    if not has_entries:
        return FactorResult("ZEK", "Clean", "No negative entries", 5.0)

    count = entry_count or 1
    if count <= 1:
        return FactorResult("ZEK", f"{count} entry", "1 entry", -3.0)
    else:
        return FactorResult("ZEK", f"{count} entries", "2+ entries", -7.0)


# ═══════════════════════════════════════════════════════════════
# 10. DEALER RISK  (weight = 0.05)
#     Based on dealer's historical default rate
# ═══════════════════════════════════════════════════════════════
def score_dealer_risk(
    dealer_default_rate: Optional[float],
    dealer_active_months: Optional[int],
) -> FactorResult:
    # New dealer with no track record
    if dealer_default_rate is None or dealer_active_months is None or dealer_active_months < 6:
        return FactorResult("DealerRisk", "New/Unknown", "NEW_DEALER", -2.0)

    if dealer_default_rate <= 0.03:
        return FactorResult("DealerRisk", f"{dealer_default_rate:.1%}", "≤3% (Low)", 4.0)
    elif dealer_default_rate <= 0.08:
        return FactorResult("DealerRisk", f"{dealer_default_rate:.1%}", "3-8% (Average)", 0.0)
    elif dealer_default_rate <= 0.15:
        return FactorResult("DealerRisk", f"{dealer_default_rate:.1%}", "8-15% (Elevated)", -3.0)
    else:
        return FactorResult("DealerRisk", f"{dealer_default_rate:.1%}", ">15% (High)", -6.0)
