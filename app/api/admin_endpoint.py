"""
Admin / Calibration API — CRUD for scoring rules.

Used by the Calibration UI to manage factor bins, tier thresholds,
and business rules without code deployments.

All changes are audit-logged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_token
from app.models.database import get_db

logger = structlog.get_logger()
router = APIRouter(prefix="/v1/admin", tags=["admin"])

SCHEMA = "lt_risk_engine"


# ── Pydantic Schemas ──

class FactorConfigResponse(BaseModel):
    factor_name: str
    weight: float
    enabled: bool
    description: Optional[str]
    score_range_min: Optional[float]
    score_range_max: Optional[float]
    display_order: int


class FactorBinResponse(BaseModel):
    id: int
    factor_name: str
    bin_order: int
    bin_label: str
    lower_bound: Optional[float]
    upper_bound: Optional[float]
    lower_inclusive: bool
    upper_inclusive: bool
    match_value: Optional[str]
    is_missing_bin: bool
    raw_score: float
    risk_interpretation: Optional[str]


class FactorBinUpdate(BaseModel):
    bin_label: Optional[str] = None
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    raw_score: Optional[float] = None
    risk_interpretation: Optional[str] = None


class TierResponse(BaseModel):
    id: int
    tier_name: str
    tier_order: int
    min_score: Optional[float]
    decision: str
    estimated_pd: Optional[float]
    color_hex: Optional[str]
    description: Optional[str]


class TierUpdate(BaseModel):
    min_score: Optional[float] = None
    decision: Optional[str] = None
    estimated_pd: Optional[float] = None


class BusinessRuleResponse(BaseModel):
    id: int
    rule_code: str
    rule_name: str
    description: Optional[str]
    condition_field: str
    condition_operator: str
    condition_value: str
    forced_tier: str
    forced_decision: str
    enabled: bool
    severity: str


class BusinessRuleUpdate(BaseModel):
    condition_value: Optional[str] = None
    enabled: Optional[bool] = None
    severity: Optional[str] = None


class ModelVersionResponse(BaseModel):
    version_id: str
    description: Optional[str]
    status: str
    published_at: Optional[datetime]
    published_by: Optional[str]
    created_at: datetime
    created_by: str


# ── Endpoints ──

@router.get("/versions", response_model=list[ModelVersionResponse])
async def list_versions(db: AsyncSession = Depends(get_db), token: dict = Depends(verify_token)):
    result = await db.execute(text(f"SELECT * FROM {SCHEMA}.model_version ORDER BY created_at DESC"))
    return [ModelVersionResponse(**dict(r._mapping)) for r in result]


@router.get("/factors/{version_id}", response_model=list[FactorConfigResponse])
async def list_factors(version_id: str, db: AsyncSession = Depends(get_db), token: dict = Depends(verify_token)):
    result = await db.execute(text(
        f"SELECT * FROM {SCHEMA}.scoring_factor_config WHERE version_id = :v ORDER BY display_order"
    ), {"v": version_id})
    rows = [FactorConfigResponse(**dict(r._mapping)) for r in result]
    if not rows:
        raise HTTPException(404, f"No factors found for version {version_id}")
    return rows


@router.get("/factors/{version_id}/{factor_name}/bins", response_model=list[FactorBinResponse])
async def list_factor_bins(version_id: str, factor_name: str, db: AsyncSession = Depends(get_db), token: dict = Depends(verify_token)):
    result = await db.execute(text(
        f"SELECT * FROM {SCHEMA}.scoring_factor_bins WHERE version_id = :v AND factor_name = :f ORDER BY bin_order"
    ), {"v": version_id, "f": factor_name})
    return [FactorBinResponse(**dict(r._mapping)) for r in result]


@router.put("/factors/{version_id}/{factor_name}/bins/{bin_id}")
async def update_factor_bin(
    version_id: str, factor_name: str, bin_id: int,
    update: FactorBinUpdate,
    db: AsyncSession = Depends(get_db), token: dict = Depends(verify_token),
):
    # Get current values for audit
    current = await db.execute(text(
        f"SELECT * FROM {SCHEMA}.scoring_factor_bins WHERE id = :id AND version_id = :v"
    ), {"id": bin_id, "v": version_id})
    row = current.first()
    if not row:
        raise HTTPException(404, "Bin not found")

    updates = update.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    # Apply updates
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = bin_id
    updates["v"] = version_id
    await db.execute(text(
        f"UPDATE {SCHEMA}.scoring_factor_bins SET {set_clause} WHERE id = :id AND version_id = :v"
    ), updates)

    # Audit log
    user = token.get("sub", "unknown")
    for field, new_val in update.model_dump(exclude_none=True).items():
        old_val = getattr(row, field, None) if hasattr(row, field) else dict(row._mapping).get(field)
        await db.execute(text(f"""
            INSERT INTO {SCHEMA}.calibration_audit_log
                (version_id, action, table_name, record_id, field_name, old_value, new_value, changed_by)
            VALUES (:v, 'UPDATED', 'scoring_factor_bins', :rid, :field, :old, :new, :user)
        """), {"v": version_id, "rid": str(bin_id), "field": field, "old": str(old_val), "new": str(new_val), "user": user})

    await db.commit()
    return {"status": "updated", "bin_id": bin_id}


@router.get("/tiers/{version_id}", response_model=list[TierResponse])
async def list_tiers(version_id: str, db: AsyncSession = Depends(get_db), token: dict = Depends(verify_token)):
    result = await db.execute(text(
        f"SELECT * FROM {SCHEMA}.scoring_tier_thresholds WHERE version_id = :v ORDER BY tier_order"
    ), {"v": version_id})
    return [TierResponse(**dict(r._mapping)) for r in result]


@router.put("/tiers/{version_id}/{tier_id}")
async def update_tier(
    version_id: str, tier_id: int,
    update: TierUpdate,
    db: AsyncSession = Depends(get_db), token: dict = Depends(verify_token),
):
    updates = update.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = tier_id
    updates["v"] = version_id
    await db.execute(text(
        f"UPDATE {SCHEMA}.scoring_tier_thresholds SET {set_clause} WHERE id = :id AND version_id = :v"
    ), updates)

    user = token.get("sub", "unknown")
    for field, new_val in update.model_dump(exclude_none=True).items():
        await db.execute(text(f"""
            INSERT INTO {SCHEMA}.calibration_audit_log
                (version_id, action, table_name, record_id, field_name, old_value, new_value, changed_by)
            VALUES (:v, 'UPDATED', 'scoring_tier_thresholds', :rid, :field, NULL, :new, :user)
        """), {"v": version_id, "rid": str(tier_id), "field": field, "new": str(new_val), "user": user})

    await db.commit()
    return {"status": "updated", "tier_id": tier_id}


@router.get("/rules/{version_id}", response_model=list[BusinessRuleResponse])
async def list_rules(version_id: str, db: AsyncSession = Depends(get_db), token: dict = Depends(verify_token)):
    result = await db.execute(text(
        f"SELECT * FROM {SCHEMA}.business_rules WHERE version_id = :v ORDER BY rule_code"
    ), {"v": version_id})
    return [BusinessRuleResponse(**dict(r._mapping)) for r in result]


@router.put("/rules/{version_id}/{rule_code}")
async def update_rule(
    version_id: str, rule_code: str,
    update: BusinessRuleUpdate,
    db: AsyncSession = Depends(get_db), token: dict = Depends(verify_token),
):
    updates = update.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["code"] = rule_code
    updates["v"] = version_id
    await db.execute(text(
        f"UPDATE {SCHEMA}.business_rules SET {set_clause} WHERE rule_code = :code AND version_id = :v"
    ), updates)

    user = token.get("sub", "unknown")
    for field, new_val in update.model_dump(exclude_none=True).items():
        await db.execute(text(f"""
            INSERT INTO {SCHEMA}.calibration_audit_log
                (version_id, action, table_name, record_id, field_name, old_value, new_value, changed_by)
            VALUES (:v, 'UPDATED', 'business_rules', :rid, :field, NULL, :new, :user)
        """), {"v": version_id, "rid": rule_code, "field": field, "new": str(new_val), "user": user})

    await db.commit()
    return {"status": "updated", "rule_code": rule_code}


@router.post("/publish/{version_id}")
async def publish_version(version_id: str, db: AsyncSession = Depends(get_db), token: dict = Depends(verify_token)):
    """Publish a model version (makes it the active scoring config)."""
    user = token.get("sub", "unknown")

    # Archive any currently published version
    await db.execute(text(
        f"UPDATE {SCHEMA}.model_version SET status = 'ARCHIVED' WHERE status = 'PUBLISHED' AND version_id != :v"
    ), {"v": version_id})

    # Publish this version
    await db.execute(text(
        f"UPDATE {SCHEMA}.model_version SET status = 'PUBLISHED', published_at = NOW(), published_by = :user WHERE version_id = :v"
    ), {"v": version_id, "user": user})

    await db.execute(text(f"""
        INSERT INTO {SCHEMA}.calibration_audit_log
            (version_id, action, table_name, record_id, changed_by)
        VALUES (:v, 'PUBLISHED', 'model_version', :v, :user)
    """), {"v": version_id, "user": user})

    await db.commit()
    logger.info("model_version_published", version_id=version_id, published_by=user)
    return {"status": "published", "version_id": version_id}


@router.get("/audit/{version_id}")
async def list_audit_log(version_id: str, limit: int = 50, db: AsyncSession = Depends(get_db), token: dict = Depends(verify_token)):
    result = await db.execute(text(
        f"SELECT * FROM {SCHEMA}.calibration_audit_log WHERE version_id = :v ORDER BY changed_at DESC LIMIT :l"
    ), {"v": version_id, "l": limit})
    return [dict(r._mapping) for r in result]
