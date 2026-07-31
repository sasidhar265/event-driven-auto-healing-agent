import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models import Event
from app.runtime_config import RULE_FILES, RuntimeRules, get_runtime_rules, load_runtime_rules
from app.services import routing


def checked_in_rule_data() -> dict:
    """Reassemble the split rules for direct model-validation tests."""
    directory = Path("app/resources/runtime")
    return {
        section: json.loads((directory / filename).read_text())
        for section, filename in RULE_FILES.items()
    }


def test_checked_in_runtime_rules_are_valid_and_complete():
    rules = get_runtime_rules()

    assert set(rules.routing.signals) == set(rules.agents.specialists)
    assert rules.routing.structured_hints.keys() == rules.routing.signals.keys()
    assert rules.lifecycle.default_environment in rules.lifecycle.environments
    assert rules.agents.confidence.maximum >= rules.agents.confidence.base


def test_invalid_runtime_rules_fail_validation():
    data = checked_in_rule_data()
    del data["routing"]["structured_hints"]["api"]

    with pytest.raises(ValidationError, match="categories must match"):
        RuntimeRules.model_validate(data)


def test_split_runtime_rules_require_every_responsibility_file(tmp_path):
    """Fail startup when a required split configuration file is absent."""
    source = Path("app/resources/runtime")
    for filename in RULE_FILES.values():
        if filename != "delivery.json":
            (tmp_path / filename).write_text((source / filename).read_text())

    with pytest.raises(FileNotFoundError, match="delivery.json"):
        load_runtime_rules(tmp_path)


def test_router_reads_signals_and_weights_from_runtime_configuration(monkeypatch):
    rules = get_runtime_rules().model_copy(deep=True)
    rules.routing.signals["api"]["organization_specific_failure_code"] = 10.0
    monkeypatch.setattr(routing, "get_runtime_rules", lambda: rules)
    event = Event(
        tenant_id="configuration-test",
        external_id="failure-1",
        event_type="unclassified.failure",
        source="test",
        severity="error",
        correlation_key="configuration-test",
        payload={"error": "organization_specific_failure_code"},
    )

    route = routing.FailureRouter().classify(event)

    assert route.category == "api"
    assert "organization_specific_failure_code" in route.matched_signals
