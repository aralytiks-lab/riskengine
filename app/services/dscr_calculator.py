"""
DSCR Calculator

Two calculation paths based on the DSCR-Calc-Service spec:

B2C (individuals):
    DSCR = (Net Income - Living Costs - Existing Obligations) / New Monthly Payment
    Where Living Costs = Rent + Insurance + Alimony + Minimum Living Cost buffer

B2B (companies):
    DSCR = EBITDA / Total Annual Debt Service (including new contract annualised)

Fallback:
    If insufficient data, return None with is_valid=False.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.schemas.risk_request import CustomerData, ContractData


# Swiss minimum living cost (Betreibungsrechtliches Existenzminimum)
# Single person baseline — CHF/month (2025 reference)
MINIMUM_LIVING_COST_SINGLE = 1_350.0
MINIMUM_LIVING_COST_BUFFER_PCT = 0.10  # 10% safety margin


@dataclass(frozen=True)
class DSCROutput:
    dscr_value: Optional[float]
    monthly_disposable_income: Optional[float]
    monthly_payment: float
    calculation_method: str  # B2C_NET_INCOME | B2B_EBITDA | FALLBACK
    is_valid: bool


def calculate_dscr(customer: CustomerData, contract: ContractData) -> DSCROutput:
    """
    Main entry point.  Dispatches to B2B or B2C logic.
    """
    monthly_payment = contract.monthly_payment

    if customer.party_type == "B2B":
        return _calc_b2b(customer, monthly_payment, contract.term_months)
    else:
        return _calc_b2c(customer, monthly_payment)


def _calc_b2c(customer: CustomerData, monthly_payment: float) -> DSCROutput:
    """
    B2C DSCR using net income after deductions.
    """
    net_income = customer.monthly_net_income
    if net_income is None or net_income <= 0:
        return DSCROutput(
            dscr_value=None,
            monthly_disposable_income=None,
            monthly_payment=monthly_payment,
            calculation_method="FALLBACK",
            is_valid=False,
        )

    # Sum all monthly obligations
    rent = customer.monthly_rent or 0.0
    insurance = customer.monthly_insurance or 0.0
    alimony = customer.monthly_alimony or 0.0
    existing_obligations = customer.monthly_existing_obligations or 0.0

    min_living = MINIMUM_LIVING_COST_SINGLE * (1 + MINIMUM_LIVING_COST_BUFFER_PCT)

    total_deductions = rent + insurance + alimony + existing_obligations + min_living
    disposable = net_income - total_deductions

    if monthly_payment <= 0:
        return DSCROutput(
            dscr_value=None,
            monthly_disposable_income=disposable,
            monthly_payment=monthly_payment,
            calculation_method="B2C_NET_INCOME",
            is_valid=False,
        )

    dscr = disposable / monthly_payment

    return DSCROutput(
        dscr_value=round(dscr, 2),
        monthly_disposable_income=round(disposable, 2),
        monthly_payment=monthly_payment,
        calculation_method="B2C_NET_INCOME",
        is_valid=True,
    )


def _calc_b2b(customer: CustomerData, monthly_payment: float, term_months: int) -> DSCROutput:
    """
    B2B DSCR using EBITDA / Total Debt Service.
    """
    ebitda = customer.annual_ebitda
    total_existing_debt_service = customer.total_debt_service or 0.0

    if ebitda is None or ebitda <= 0:
        return DSCROutput(
            dscr_value=None,
            monthly_disposable_income=None,
            monthly_payment=monthly_payment,
            calculation_method="FALLBACK",
            is_valid=False,
        )

    # Annualise the new contract's debt service
    new_annual_service = monthly_payment * 12
    total_annual_ds = total_existing_debt_service + new_annual_service

    if total_annual_ds <= 0:
        return DSCROutput(
            dscr_value=None,
            monthly_disposable_income=None,
            monthly_payment=monthly_payment,
            calculation_method="B2B_EBITDA",
            is_valid=False,
        )

    dscr = ebitda / total_annual_ds

    return DSCROutput(
        dscr_value=round(dscr, 2),
        monthly_disposable_income=round(ebitda / 12 - monthly_payment, 2),
        monthly_payment=monthly_payment,
        calculation_method="B2B_EBITDA",
        is_valid=True,
    )
