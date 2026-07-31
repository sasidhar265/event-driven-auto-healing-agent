"""Load and validate maintainable runtime business rules from JSON."""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from app.config import get_settings


class RoutingScoreConfig(BaseModel):
    explicit_weight: float = Field(gt=0)
    structured_field_weight: float = Field(gt=0)
    confidence_base: float = Field(ge=0, le=1)
    score_cap: float = Field(gt=0)
    score_multiplier: float = Field(gt=0)
    separation_cap: float = Field(gt=0)
    separation_multiplier: float = Field(gt=0)
    confidence_cap: float = Field(ge=0, le=1)
    ambiguity_margin: float = Field(ge=0)
    ambiguous_confidence_cap: float = Field(ge=0, le=1)


class RoutingConfig(BaseModel):
    signals: dict[str, dict[str, float]]
    structured_hints: dict[str, list[str]]
    explicit_fields: list[str]
    scoring: RoutingScoreConfig

    @model_validator(mode="after")
    def categories_match(self):
        if set(self.signals) != set(self.structured_hints):
            raise ValueError("routing signal and structured-hint categories must match")
        return self


class ConfidenceConfig(BaseModel):
    base: float = Field(ge=0, le=1)
    signal_bonus: float = Field(ge=0)
    evidence_bonus_per_item: float = Field(ge=0)
    evidence_bonus_cap: float = Field(ge=0)
    severity_bonus: dict[str, float]
    maximum: float = Field(ge=0, le=1)
    target_file_bonus: float = Field(ge=0)
    target_method_bonus: float = Field(ge=0)
    trace_bonus: float = Field(ge=0)
    missing_evidence_cap: float = Field(ge=0, le=1)


class SpecialistConfig(BaseModel):
    signals: list[str]
    action: str
    required_evidence: list[str]
    change_plan: list[dict[str, str]]
    validation: list[str] = []


class XPathConfig(BaseModel):
    detection_signals: list[str]
    missing_evidence_confidence: float = Field(ge=0, le=1)
    locator_priorities: dict[str, int]
    confidence_base: float = Field(ge=0, le=1)
    preferred_locator_bonus: float = Field(ge=0)
    other_locator_bonus: float = Field(ge=0)
    unique_bonus: float = Field(ge=0)
    evidence_bonus_per_item: float = Field(ge=0)
    evidence_bonus_cap: float = Field(ge=0)
    maximum: float = Field(ge=0, le=1)
    required_evidence: list[str]
    validation: list[str]
    missing_title: str
    missing_rationale: str
    missing_action: str
    replacement_title: str
    replacement_rationale: str
    replacement_action: str
    rollback_instruction: str

    @model_validator(mode="after")
    def validate_templates(self):
        self.replacement_rationale.format(strategy="css-selector", unique_suffix="")
        return self


class InvestigationConfig(BaseModel):
    confidence: float = Field(ge=0, le=1)
    required_evidence: list[str]
    title_template: str
    rationale: str
    action: str

    @model_validator(mode="after")
    def validate_templates(self):
        self.title_template.format(event_type="event.type")
        return self


class AgentConfig(BaseModel):
    confidence: ConfidenceConfig
    specialists: dict[str, SpecialistConfig]
    xpath: XPathConfig
    investigation: InvestigationConfig
    target_file_fields: list[str]
    target_method_fields: list[str]
    trace_required_categories: list[str]
    base_validation: list[str]
    rollback_instruction: str
    title_template: str
    rationale_template: str
    missing_target_evidence: str
    missing_trace_evidence: str

    @model_validator(mode="after")
    def validate_templates(self):
        self.title_template.format(agent_type="API", event_type="api.failure")
        self.rationale_template.format(matches="api", evidence_count=1)
        return self


class KnowledgeConfig(BaseModel):
    item_scan_limit: int = Field(ge=1)
    reference_scan_limit: int = Field(ge=1)
    result_limit: int = Field(ge=1)
    accepted_reference_bonus: int = Field(ge=0)


class LifecycleConfig(BaseModel):
    environments: list[str]
    default_environment: str
    severity_map: dict[str, str]
    default_severity: str
    category_map: dict[str, str]
    default_category: str
    self_heal_type_map: dict[str, str]
    workflow_type: str
    runtime_actor: str
    model_version: str


class DeliveryConfig(BaseModel):
    worker_batch_size: int = Field(ge=1)
    webhook_batch_size: int = Field(ge=1)
    retry_base_seconds: float = Field(gt=1)
    retry_max_seconds: int = Field(ge=1)
    cloud_event_source: str
    cloud_event_type: str
    dispatcher_actor: str
    error_message_max_length: int = Field(ge=100)


class RuntimeRules(BaseModel):
    routing: RoutingConfig
    agents: AgentConfig
    knowledge: KnowledgeConfig
    lifecycle: LifecycleConfig
    delivery: DeliveryConfig

    @model_validator(mode="after")
    def specialist_categories_match_routing(self):
        if set(self.routing.signals) != set(self.agents.specialists):
            raise ValueError("routing and specialist categories must match")
        return self


@lru_cache
def get_runtime_rules() -> RuntimeRules:
    path = Path(get_settings().runtime_rules_path)
    if not path.is_absolute():
        path = Path(__file__).parents[1] / path
    return RuntimeRules.model_validate_json(path.read_text())
