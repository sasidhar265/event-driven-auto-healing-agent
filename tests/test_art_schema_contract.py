"""Regression checks for the ART_Feedback.docx database contract."""

from sqlalchemy import Numeric
from sqlalchemy.dialects.postgresql import ENUM

from app.art_models import Base


REQUIRED_TABLES = {
    "failure_events", "agent_runs", "agent_run_steps", "agent_decision_journals",
    "impact_assessments", "impact_dependencies", "test_selection_decisions",
    "execution_intents", "execution_result_refs", "self_heal_proposals",
    "outcome_feedback", "event_inbox", "event_outbox",
}


def art_tables():
    return {table.name: table for table in Base.metadata.tables.values() if table.schema == "art"}


def test_requirement_tables_have_enterprise_context():
    tables = art_tables()

    assert REQUIRED_TABLES <= tables.keys()
    for name in REQUIRED_TABLES:
        columns = tables[name].columns
        assert not columns["correlation_id"].nullable
        assert not columns["tenant_id"].nullable
        assert not columns["environment"].nullable
        assert isinstance(columns["environment"].type, ENUM)
        assert columns["environment"].type.name == "art_environment"


def test_controlled_values_use_requirement_postgres_enums():
    tables = art_tables()
    expected = {
        ("failure_events", "failure_category"): "art_failure_category",
        ("failure_events", "severity"): "art_severity",
        ("agent_runs", "workflow_type"): "art_workflow_type",
        ("agent_runs", "status"): "art_status",
        ("agent_decision_journals", "decision_type"): "art_decision_type",
        ("impact_assessments", "impact_source"): "art_change_type",
        ("execution_intents", "approval_status"): "art_approval_status",
        ("self_heal_proposals", "proposal_type"): "art_self_heal_type",
    }

    for (table, column), enum_name in expected.items():
        assert isinstance(tables[table].columns[column].type, ENUM)
        assert tables[table].columns[column].type.name == enum_name


def test_scores_use_document_precision():
    tables = art_tables()

    for table, column in (
        ("agent_run_steps", "confidence_score"),
        ("agent_decision_journals", "confidence_score"),
        ("impact_assessments", "risk_score"),
        ("impact_dependencies", "dependency_confidence"),
        ("test_selection_decisions", "risk_coverage"),
        ("self_heal_proposals", "confidence_score"),
    ):
        data_type = tables[table].columns[column].type
        assert isinstance(data_type, Numeric)
        assert (data_type.precision, data_type.scale) == (5, 4)
