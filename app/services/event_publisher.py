"""
Kafka event publisher — fire-and-forget.

Publishes risk assessment events for downstream consumers
(dashboards, monitoring, data warehouse sync).
Gracefully degrades if Kafka is unavailable.
"""
from __future__ import annotations

import json
import structlog
from app.core.config import get_settings
from app.schemas.risk_response import RiskEvaluationResponse

logger = structlog.get_logger()

_producer = None


async def _get_producer():
    global _producer
    settings = get_settings()
    if not settings.kafka_enabled:
        return None
    if _producer is None:
        from aiokafka import AIOKafkaProducer
        _producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap)
        await _producer.start()
    return _producer


async def publish_risk_event(response: RiskEvaluationResponse) -> None:
    settings = get_settings()
    if not settings.kafka_enabled:
        return

    try:
        producer = await _get_producer()
        if producer:
            event = {
                "event_type": "RISK_ASSESSMENT_COMPLETED",
                "assessment_id": response.assessment_id,
                "request_id": response.request_id,
                "tier": response.tier.value,
                "decision": response.decision.value,
                "total_score": response.total_score,
                "model_version": response.model_version,
                "evaluated_at": response.evaluated_at.isoformat(),
            }
            await producer.send_and_wait(
                settings.kafka_topic_risk_events,
                json.dumps(event).encode("utf-8"),
                key=response.request_id.encode("utf-8"),
            )
            logger.info("kafka_event_published", assessment_id=response.assessment_id)
    except Exception as e:
        # Fire-and-forget: log but don't fail the request
        logger.warning("kafka_publish_failed", error=str(e))
