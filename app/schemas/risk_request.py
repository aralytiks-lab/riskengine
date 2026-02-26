"""
Inbound payload from Flowable.

Flowable sends ALL context data in a single synchronous POST.
The risk engine never fetches from ODS/DWH — everything arrives here.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ── Enums matching LeaseTeq domain ──

class PermitType(str, Enum):
    B = "B"
    C = "C"
    L = "L"
    DIPLOMAT = "Diplomat"
    UNKNOWN = "Unknown"


class PartyType(str, Enum):
    B2B = "B2B"
    B2C = "B2C"


class IncomeType(str, Enum):
    EMPLOYED = "employed"
    SELF_EMPLOYED = "self_employed"
    RETIRED = "retired"
    UNEMPLOYED = "unemployed"
    OTHER = "other"


# ── Sub-models ──

class CustomerData(BaseModel):
    """Demographics + bureau scores — provided by Flowable from ODS."""
    customer_id: str
    date_of_birth: date
    party_type: PartyType
    permit_type: Optional[PermitType] = None
    nationality: Optional[str] = None
    income_type: Optional[IncomeType] = None

    # Monthly financials (CHF) — used for DSCR calc
    monthly_gross_income: Optional[float] = Field(None, ge=0)
    monthly_net_income: Optional[float] = Field(None, ge=0)
    monthly_existing_obligations: Optional[float] = Field(None, ge=0, description="Sum of existing lease/loan payments")
    monthly_rent: Optional[float] = Field(None, ge=0)
    monthly_insurance: Optional[float] = Field(None, ge=0)
    monthly_alimony: Optional[float] = Field(None, ge=0)

    # B2B fields
    annual_revenue: Optional[float] = Field(None, ge=0, description="For B2B: company annual revenue CHF")
    annual_ebitda: Optional[float] = Field(None, ge=0, description="For B2B: company EBITDA CHF")
    total_debt_service: Optional[float] = Field(None, ge=0, description="For B2B: annual debt service CHF")

    # Bureau scores (already fetched by upstream services)
    crif_score: Optional[int] = Field(None, ge=0, le=1000)
    intrum_score: Optional[int] = Field(None, ge=0, le=10)
    zek_has_entries: Optional[bool] = Field(None, description="True if customer has negative ZEK entries")
    zek_entry_count: Optional[int] = Field(None, ge=0)


class VehicleData(BaseModel):
    """Vehicle / collateral details."""
    vehicle_price: float = Field(gt=0, description="Full vehicle price CHF incl. VAT")
    vehicle_type: Optional[str] = None
    vehicle_age_months: Optional[int] = Field(None, ge=0)
    is_electric: Optional[bool] = None
    eurotax_code: Optional[str] = None


class ContractData(BaseModel):
    """Lease/financing contract terms."""
    contract_id: str
    financed_amount: float = Field(gt=0, description="Total financed amount CHF")
    downpayment_amount: float = Field(ge=0)
    residual_value: Optional[float] = Field(None, ge=0)
    term_months: int = Field(gt=0, le=84)
    monthly_payment: float = Field(gt=0)
    interest_rate: Optional[float] = Field(None, ge=0)
    product_type: Optional[str] = None


class DealerData(BaseModel):
    """Dealer / partner context."""
    dealer_id: str
    dealer_name: Optional[str] = None
    dealer_default_rate: Optional[float] = Field(None, ge=0, le=1, description="Historical default rate 0-1")
    dealer_active_months: Optional[int] = Field(None, ge=0)
    dealer_volume_tier: Optional[str] = None


# ── Top-level request ──

class RiskEvaluationRequest(BaseModel):
    """
    POST /v1/risk/evaluate

    Synchronous call from Flowable.
    Contains ALL data needed — the risk engine is stateless.
    """
    request_id: str = Field(description="Idempotency key from Flowable")
    timestamp: str = Field(description="ISO-8601 timestamp of request")
    customer: CustomerData
    vehicle: VehicleData
    contract: ContractData
    dealer: DealerData
    model_version: Optional[str] = Field(None, description="Override scoring model version")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        from datetime import datetime
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("timestamp must be ISO-8601")
        return v
