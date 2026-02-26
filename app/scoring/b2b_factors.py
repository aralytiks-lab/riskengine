"""
B2B Scoring Factors — v1.2

Separate factor set for B2B (corporate) lease applications.
B2B replaces 4 of the 10 B2C factors with company-specific equivalents:

  B2C factor      →  B2B equivalent
  ─────────────────────────────────
  Age             →  CompanyAge     (years since founding)
  Intrum          →  DebtRatio      (total debt service / annual revenue)
  DSCR            →  DSCR           (same factor, different bins — B2B EBITDA-based)
  Permit          →  CompanyType    (legal form + Zefix status)
  ZEK             →  IndustryRisk   (mapped from NACE/UID industry code)

The remaining 5 factors (LTV, Term, CRIF, VehiclePriceTier, DealerRisk)
are shared with B2C and imported from factors.py.

B2B weights (must sum to 1.0):
  LTV              0.15
  Term             0.10
  CompanyAge       0.10
  CRIF             0.10   (lower than B2C — CRIF less reliable for companies)
  DebtRatio        0.10
  DSCR             0.20   (highest weight — EBITDA coverage is key B2B metric)
  CompanyType      0.10
  VehiclePriceTier 0.05
  IndustryRisk     0.10
  DealerRisk       0.05
  ─────────────────────
  Total            1.00

Convention: HIGHER score = LOWER risk.
"""
from __future__ import annotations

from typing import Optional

from app.scoring.factors import FactorResult


# ═══════════════════════════════════════════════════════════════
# 3B. COMPANY AGE  (weight = 0.10)   replaces: Age
#    Years since company founding in the Zefix/UID register.
# ═══════════════════════════════════════════════════════════════
def score_company_age(company_age_years: Optional[int]) -> FactorResult:
    if company_age_years is None:
        return FactorResult("CompanyAge", "N/A", "MISSING", -5.0)

    age = company_age_years

    if age < 2:
        # Hard decline (BR-B03) — also reflected as a strongly negative score
        return FactorResult("CompanyAge", f"{age}y", "<2y (Too new)", -10.0)
    elif age < 5:
        return FactorResult("CompanyAge", f"{age}y", "2-5y (Startup)", -4.0)
    elif age < 10:
        return FactorResult("CompanyAge", f"{age}y", "5-10y (Growing)", 0.0)
    elif age < 20:
        return FactorResult("CompanyAge", f"{age}y", "10-20y (Established)", 5.0)
    else:
        return FactorResult("CompanyAge", f"{age}y", ">=20y (Mature)", 8.0)


# ═══════════════════════════════════════════════════════════════
# 5B. DEBT RATIO  (weight = 0.10)    replaces: Intrum
#    Total annual debt service as % of annual revenue.
#    Measures financial leverage — lower is better.
# ═══════════════════════════════════════════════════════════════
def score_debt_ratio(
    total_debt_service: Optional[float],   # CHF/year (existing + new contract annualised)
    annual_revenue: Optional[float],        # CHF/year
) -> FactorResult:
    if annual_revenue is None or annual_revenue <= 0 or total_debt_service is None:
        return FactorResult("DebtRatio", "N/A", "MISSING", -4.0)

    ratio = total_debt_service / annual_revenue

    if ratio < 0.20:
        return FactorResult("DebtRatio", f"{ratio:.0%}", "<20% (Low leverage)", 5.0)
    elif ratio < 0.40:
        return FactorResult("DebtRatio", f"{ratio:.0%}", "20-40% (Moderate)", 2.0)
    elif ratio < 0.60:
        return FactorResult("DebtRatio", f"{ratio:.0%}", "40-60% (High)", -2.0)
    else:
        return FactorResult("DebtRatio", f"{ratio:.0%}", ">60% (Distressed)", -6.0)


# ═══════════════════════════════════════════════════════════════
# 6B. B2B DSCR  (weight = 0.20)      replaces: B2C DSCR
#    EBITDA-based DSCR = EBITDA / (existing_annual_ds + monthly_payment × 12)
#    Different bins from B2C (B2B healthy DSCR is typically ≥1.25)
# ═══════════════════════════════════════════════════════════════
def score_b2b_dscr(dscr_value: Optional[float]) -> FactorResult:
    """
    B2B DSCR bins are tighter than B2C because EBITDA-based coverage
    uses a fundamentally different scale (ratios ~1-3 are normal vs B2C ~3-15).
    """
    if dscr_value is None:
        return FactorResult("DSCR", "N/A", "MISSING", -5.0)

    if dscr_value < 1.0:
        return FactorResult("DSCR", f"{dscr_value:.2f}", "<1.0 (Cannot service)", -8.0)
    elif dscr_value < 1.25:
        return FactorResult("DSCR", f"{dscr_value:.2f}", "1.0-1.25 (Tight)", -3.0)
    elif dscr_value < 1.5:
        return FactorResult("DSCR", f"{dscr_value:.2f}", "1.25-1.5 (Adequate)", 0.0)
    elif dscr_value < 2.0:
        return FactorResult("DSCR", f"{dscr_value:.2f}", "1.5-2.0 (Good)", 5.0)
    else:
        return FactorResult("DSCR", f"{dscr_value:.2f}", ">=2.0 (Strong)", 7.0)


# ═══════════════════════════════════════════════════════════════
# 7B. COMPANY TYPE  (weight = 0.10)  replaces: Permit
#    Swiss legal form + Zefix active status.
#    Dissolved/Suspended/NotFound → hard decline in business rules,
#    but also scored negatively here for completeness.
# ═══════════════════════════════════════════════════════════════
def score_company_type(
    legal_form: Optional[str],   # AG, GmbH, KG, Einzelfirma, Other, Unknown
    zefix_status: Optional[str], # ACTIVE, DISSOLVED, SUSPENDED, NOT_FOUND, UNKNOWN
) -> FactorResult:
    status = (zefix_status or "UNKNOWN").upper()
    form = (legal_form or "UNKNOWN").upper()

    # Hard-decline statuses are also scored worst here
    if status in ("DISSOLVED", "SUSPENDED"):
        return FactorResult("CompanyType", f"{form}/{status}", "Dissolved/Suspended", -10.0)
    if status == "NOT_FOUND":
        return FactorResult("CompanyType", f"{form}/{status}", "Not in Zefix", -8.0)

    # Active or Unknown status — score by legal form
    if form == "AG":
        score, label = 5.0, "AG (Aktiengesellschaft)"
    elif form == "GMBH":
        score, label = 3.0, "GmbH"
    elif form == "KG":
        score, label = 0.0, "KG (Kommanditgesellschaft)"
    elif form == "EINZELFIRMA":
        score, label = -2.0, "Einzelfirma (Sole prop.)"
    elif form in ("OTHER", "UNKNOWN"):
        score, label = 0.0, "Other/Unknown form"
    else:
        score, label = 0.0, form

    # Slight penalty if Zefix was not checked
    if status == "UNKNOWN":
        score = max(score - 1.0, -3.0)
        label += " (Zefix not checked)"

    return FactorResult("CompanyType", f"{form}/{status}", label, score)


# ═══════════════════════════════════════════════════════════════
# 9B. INDUSTRY RISK  (weight = 0.10)  replaces: ZEK
#    Risk tier mapped from NACE / UID industry code by upstream service.
#    LeaseTeq-specific mapping based on Swiss default rate data.
# ═══════════════════════════════════════════════════════════════
def score_industry_risk(industry_risk: Optional[str]) -> FactorResult:
    """
    industry_risk expected values: Low | Medium | High | Critical | Unknown
    These map from NACE codes upstream (e.g. in Flowable or a lookup table).

    Example NACE → tier mapping:
      Low:      A (Agriculture - actually food-stable), Q (Health), P (Education), K (Finance)
      Medium:   C (Manufacturing), G (Retail), I (Accommodation), N (Services)
      High:     F (Construction), H (Transport/logistics), A (Agriculture - volatile)
      Critical: B (Mining), D (Energy utilities - cyclical), highly concentrated industries
    """
    risk = (industry_risk or "Unknown").strip()

    if risk == "Low":
        return FactorResult("IndustryRisk", risk, "Low risk industry", 5.0)
    elif risk == "Medium":
        return FactorResult("IndustryRisk", risk, "Medium risk industry", 0.0)
    elif risk == "High":
        return FactorResult("IndustryRisk", risk, "High risk industry", -4.0)
    elif risk == "Critical":
        return FactorResult("IndustryRisk", risk, "Critical risk industry", -8.0)
    else:
        # Unknown / not classified
        return FactorResult("IndustryRisk", risk, "Industry not classified", -2.0)
