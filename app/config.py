from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "auto-healing-agent-runtime"
    api_profile: Literal["operations", "integration", "admin", "full"] = "operations"
    database_url: str = "postgresql+asyncpg://healing:healing@localhost:5432/healing"
    api_key: str = "change-me"
    worker_poll_seconds: float = 1.0
    confidence_review_threshold: float = Field(0.60, ge=0, le=1)
    confidence_delivery_threshold: float = Field(0.80, ge=0, le=1)
    ai_provider: str = "deterministic"
    ai_endpoint: str | None = None
    ai_api_key: str | None = None
    webhook_signing_secret: str = "change-webhook-secret"
    webhook_max_attempts: int = Field(8, ge=1, le=50)
    webhook_timeout_seconds: float = Field(10, gt=0, le=60)
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_input_topic: str = "enterprise.failures"
    kafka_dead_letter_topic: str = "enterprise.failures.dead-letter"
    kafka_consumer_group: str = "auto-healing-agent-runtime"
    kafka_auto_offset_reset: str = Field("earliest", pattern="^(earliest|latest)$")
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_sasl_mechanism: str | None = None
    kafka_sasl_username: str | None = None
    kafka_sasl_password: str | None = None
    external_postgres_enabled: bool = False
    external_postgres_url: str | None = None
    external_poll_seconds: float = Field(2.0, gt=0, le=300)
    external_batch_size: int = Field(20, ge=1, le=500)
    external_event_table: str = "public.failure_events"
    external_event_id_column: str = "id"
    external_event_type_column: str = "event_type"
    external_event_source_column: str = "source"
    external_event_severity_column: str = "severity"
    external_event_correlation_column: str = "correlation_key"
    external_event_payload_column: str = "payload"
    external_event_tenant_column: str = "tenant_id"
    external_event_actor_column: str = "actor"
    external_event_created_column: str = "created_at"
    external_event_processed_column: str = "art_ingested_at"
    external_result_mode: str = Field("insert", pattern="^(insert|update_event)$")
    external_result_table: str = "public.art_suggestions"
    external_result_suggestion_id_column: str = "suggestion_id"
    external_result_event_id_column: str = "event_id"
    external_result_status_column: str = "status"
    external_result_confidence_column: str = "confidence"
    external_result_agent_column: str = "agent_type"
    external_result_payload_column: str = "suggestion"
    external_result_created_column: str = "created_at"
    external_event_result_column: str = "art_suggestion"
    external_event_result_status_column: str = "art_status"


@lru_cache
def get_settings() -> Settings:
    return Settings()
