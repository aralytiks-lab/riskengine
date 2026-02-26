"""
Application configuration — loaded from environment / .env file.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ──
    app_name: str = "lt-risk-engine"
    app_env: str = "development"
    log_level: str = "INFO"
    scoring_model_version: str = "1.2"

    # ── Database ──
    database_url: str = "postgresql+asyncpg://riskengine:changeme@localhost:5433/lt_risk_engine"

    # ── Keycloak / JWT ──
    keycloak_url: str = "https://auth.leaseteq.ch/realms/leaseteq"
    keycloak_client_id: str = "risk-engine"
    keycloak_audience: str = "risk-engine-api"
    auth_enabled: bool = True

    # ── Kafka ──
    kafka_bootstrap: str = "kafka:9092"
    kafka_topic_risk_events: str = "risk.assessment.events"
    kafka_enabled: bool = False  # toggle for local dev

    # ── Redis ──
    redis_url: str = "redis://localhost:6380/0"
    rule_cache_ttl_seconds: int = 300

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
