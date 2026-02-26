"""
POST /v1/risk/evaluate

The single endpoint called by Flowable.
Synchronous request → score → response.
Persists every evaluation to the audit table.
Publishes events to Kafka (if enabled).
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_token
from app.models.database import get_db
from app.models.risk_assessment import RiskAssessment
from app.schemas.risk_request import RiskEvaluationRequest
from app.schemas.risk_response import RiskEvaluationResponse
from app.scoring.engine import evaluate
from app.services.event_publisher import publish_risk_event

logger = structlog.get_logger()
router = APIRouter(prefix="/v1/risk", tags=["risk"])


@router.post(
    "/evaluate",
    response_model=RiskEvaluationResponse,
    summary="Evaluate credit risk for a lease application",
    description="Called synchronously by Flowable. Receives all context, returns tier + decision.",
)
async def evaluate_risk(
    request: RiskEvaluationRequest,
    token_payload: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
) -> RiskEvaluationResponse:

    logger.info(
        "risk_evaluation_started",
        request_id=request.request_id,
        contract_id=request.contract.contract_id,
        customer_id=request.customer.customer_id,
        caller=token_payload.get("sub", "unknown"),
    )

    # ── Idempotency check ──
    existing = await db.get(RiskAssessment, None)  # check by request_id below
    from sqlalchemy import select
    stmt = select(RiskAssessment).where(RiskAssessment.request_id == request.request_id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        logger.info("duplicate_request", request_id=request.request_id, assessment_id=existing.assessment_id)
        return RiskEvaluationResponse(**existing.response_payload)

    # ── Score ──
    try:
        response = evaluate(request)
    except Exception as e:
        logger.error("scoring_failed", request_id=request.request_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Scoring engine error: {e}")

    # ── Persist ──
    assessment = RiskAssessment(
        assessment_id=response.assessment_id,
        request_id=request.request_id,
        contract_id=request.contract.contract_id,
        customer_id=request.customer.customer_id,
        model_version=response.model_version,
        total_score=response.total_score,
        tier=response.tier.value,
        decision=response.decision.value,
        probability_of_default=response.probability_of_default,
        factor_scores_json=[fs.model_dump() for fs in response.factor_scores],
        dscr_json=response.dscr.model_dump(),
        business_rule_overrides_json=[br.model_dump() for br in response.business_rule_overrides],
        legacy_score=response.legacy_score,
        legacy_band=response.legacy_band,
        request_payload=request.model_dump(mode="json"),
        response_payload=response.model_dump(mode="json"),
        processing_time_ms=response.processing_time_ms,
        evaluated_at=response.evaluated_at,
    )

    db.add(assessment)
    await db.commit()

    # ── Publish to Kafka (fire-and-forget) ──
    await publish_risk_event(response)

    return response


@router.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "lt-risk-engine", "model_version": "1.2"}
