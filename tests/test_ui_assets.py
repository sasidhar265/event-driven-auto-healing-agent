import re
from pathlib import Path

STATIC = Path(__file__).parents[1] / "app" / "static"


def javascript_source() -> str:
    """Return all ordered browser feature scripts as one searchable source."""
    return "\n".join(path.read_text() for path in sorted((STATIC / "js").glob("*.js")))


def test_operations_ui_contains_core_workflows():
    html = (STATIC / "index.html").read_text()
    for element_id in (
        'id="dashboard"',
        'id="simulate"',
        'id="suggestions"',
        'id="audit"',
        'id="event-form"',
        'id="api-explorer"',
    ):
        assert element_id in html
    assert 'data-view="governance"' not in html
    assert 'id="knowledge-form"' not in html
    assert 'id="policy-form"' not in html
    assert 'id="tenant-label"' not in html
    assert 'id="setting-tenant"' not in html


def test_api_explorer_uses_the_live_openapi_contract():
    html = (STATIC / "index.html").read_text()
    javascript = javascript_source()

    assert 'data-view="api-explorer"' in html
    assert 'id="api-list"' in html
    assert 'id="swagger-link"' in html
    assert 'api("/openapi.json", {cache: "no-store"})' in javascript
    assert '.filter(([path]) => path.startsWith("/v1/art/"))' in javascript
    assert "left.path.localeCompare(right.path)" in javascript
    assert '"GET /v1/art/agent-runs"' in javascript
    assert "Open all interactive API docs" in html
    assert "When to use" in javascript
    assert "Database usage" in javascript
    assert "Request / filters" in javascript
    assert "agent_run_steps and agent_decision_journals" in javascript


def test_ui_uses_layered_glass_surfaces():
    styles = (STATIC / "styles.css").read_text()

    assert "--glass:" in styles
    assert "backdrop-filter: blur(20px)" in styles
    assert "--glass-shadow:" in styles
    assert ".modal-content" in styles
    assert "background-attachment: fixed" in styles


def test_primary_navigation_uses_top_glass_layout():
    html = (STATIC / "index.html").read_text()
    styles = (STATIC / "styles.css").read_text()

    sidebar = html.split('<aside class="sidebar">', 1)[1].split("</aside>", 1)[0]
    assert 'class="nav-actions"' in sidebar
    assert 'id="refresh-button"' in sidebar
    assert 'id="settings-button"' in sidebar
    assert 'class="topbar"' not in html
    assert 'id="page-title"' not in html
    assert "Top navigation preview" in styles
    assert "position: sticky" in styles
    assert "flex-direction: row" in styles
    assert "rgba(17,31,25,.94)" in styles


def test_operations_ui_defines_failure_domains_and_real_api_calls():
    javascript = javascript_source()
    for category in (
        "ui",
        "api",
        "logic",
        "functional",
        "test_data",
        "database",
        "infrastructure",
        "dependency",
        "security",
        "performance",
    ):
        assert f"  {category}:" in javascript
    assert 'api("/v1/events"' in javascript
    assert "api(`/v1/suggestions" in javascript
    assert "api(`/v1/audit" in javascript


def test_suggestion_filters_cover_lifecycle_statuses_and_show_counts():
    html = (STATIC / "index.html").read_text()
    javascript = javascript_source()

    for status in ("all", "ready", "review", "suppressed", "accepted", "rejected"):
        assert f'data-status="{status}"' in html
    assert html.count('class="filter-count"') == 6
    assert 'query.set("status", suggestionFilter)' in javascript
    assert 'button.querySelector(".filter-count").textContent' in javascript
    assert 'class="suggestion-decision-actions"' in javascript


def test_suggestions_support_correlation_search_and_pagination():
    html = (STATIC / "index.html").read_text()
    javascript = javascript_source()

    for element_id in (
        'id="suggestion-filter-form"',
        'id="suggestion-correlation"',
        'id="suggestion-page-size"',
        'id="suggestion-pagination"',
        'id="suggestion-previous"',
        'id="suggestion-next"',
        'id="suggestion-page-summary"',
    ):
        assert element_id in html
    assert 'query.set("correlation_id", correlationId)' in javascript
    assert "function renderSuggestionPage()" in javascript
    assert 'offset: String((suggestionPage - 1) * pageSize)' in javascript
    assert 'response.headers.get("X-Total-Count")' in javascript
    assert "item.correlation_id" in javascript


def test_decision_model_renders_live_confidence_classifications():
    html = (STATIC / "index.html").read_text()
    javascript = javascript_source()

    for classification in ("suppressed", "review", "ready"):
        assert f'id="decision-{classification}"' in html
    assert 'id="decision-summary"' in html
    assert 'id="decision-state-filter"' in html
    assert 'id="decision-ranking"' in html
    assert 'id="decision-records"' in html
    assert "data.decision_model" in javascript
    assert "classified by confidence and policy evidence" in javascript
    assert "renderDecisionRecords" in javascript


def test_audit_trail_supports_time_environment_and_correlation_filters():
    html = (STATIC / "index.html").read_text()
    javascript = javascript_source()

    for element_id in (
        'id="audit-filter-form"',
        'id="audit-environment"',
        'id="audit-time-range"',
        'id="audit-correlation"',
        'id="audit-from-time"',
        'id="audit-to-time"',
        'id="clear-audit-filters"',
    ):
        assert element_id in html
    for range_value in (
        "30m",
        "1h",
        "2h",
        "4h",
        "6h",
        "12h",
        "1d",
        "2d",
        "3d",
        "4d",
        "5d",
        "6d",
        "1w",
        "2w",
        "3w",
        "4w",
        "custom",
    ):
        assert f'value="{range_value}"' in html
    assert 'query.set("correlation_id", correlationId)' in javascript
    assert 'query.set("from_time"' in javascript
    assert 'query.set("to_time"' in javascript
    assert "clearAuditFilters" in javascript
    assert html.count('class="btn btn-outline-secondary audit-calendar-button"') == 2
    assert "flatpickr@4.6.13/dist/flatpickr.min.css" in html
    assert "flatpickr@4.6.13/dist/flatpickr.min.js" in html
    assert "enableTime: true" in javascript
    assert "input._flatpickr.open()" in javascript
    assert "<span>Correlation ID</span><span>Failure ID</span>" in html
    assert "item.correlation_id" in javascript
    assert "item.failure_id" in javascript


def test_detail_actions_use_modal_overlays():
    html = (STATIC / "index.html").read_text()
    javascript = javascript_source()

    assert 'id="details-dialog"' in html
    assert 'id="details-content"' in html
    assert 'bootstrap.Modal.getOrCreateInstance($("#details-dialog")).show()' in javascript
    assert "showSuggestionDetails(item)" in javascript
    assert "/trace`" in javascript
    assert "Incident processing logs" in javascript
    assert "Inspect structured context" in javascript
    assert "stage.api" in javascript
    assert "stage.data" in javascript
    assert 'id="trace-search"' in javascript
    assert 'id="trace-level-filter"' in javascript
    assert "filterTraceLogs" in javascript
    assert "trace-visible-count" in javascript
    assert "renderClassificationDecision" in javascript
    assert "Incoming event" in javascript
    assert "Weighted evidence" in javascript
    assert "Routing decision" in javascript
    assert "payload_evidence" in javascript
    assert "category_scores" in javascript
    assert "Confidence calculation" in javascript
    assert "Winning score" in javascript
    assert "Category separation" in javascript
    assert "ambiguity cap" in javascript
    assert "data-confidence-id=" in javascript
    assert "showSuggestionConfidence" in javascript
    assert "renderSuggestionConfidenceCalculation" in javascript
    assert "Specialist evidence score" in javascript
    assert "Policy adjustments" in javascript
    assert "<dt>Identified by</dt>" in javascript
    assert "<dt>Environment</dt>" in javascript
    assert "Identified by ${escapeHtml(item.source" in javascript
    assert 'id="event-environment"' in html
    assert 'id="activity-environment"' in html
    assert 'id="audit-environment"' in html
    assert 'query.set("environment", environment)' in javascript
    assert "data-event-id=" in javascript
    assert "data-audit-id=" in javascript


def test_connection_action_shows_safe_runtime_and_database_details():
    html = (STATIC / "index.html").read_text()
    javascript = javascript_source()

    for element_id in (
        'id="connection-details"',
        'id="connection-runtime-status"',
        'id="connection-api-endpoint"',
        'id="connection-api-profile"',
        'id="connection-database-status"',
        'id="connection-database-server"',
        'id="connection-database-identity"',
    ):
        assert element_id in html
    assert 'api("/health/live")' in javascript
    assert "health.database?.status" in javascript


def test_bootstrap_is_loaded_and_used_for_modals_and_forms():
    html = (STATIC / "index.html").read_text()

    assert "bootstrap@5.3.8/dist/css/bootstrap.min.css" in html
    assert "bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js" in html
    assert 'class="modal fade"' in html
    assert 'class="form-control"' in html
    assert 'class="form-select"' in html
    assert html.count('class="form-control"') >= 8
    assert html.count('class="form-select') >= 3
    assert 'data-bs-dismiss="modal"' in html


def test_every_interactive_control_uses_bootstrap_foundations():
    html = (STATIC / "index.html").read_text()
    javascript = javascript_source()
    markup = f"{html}\n{javascript}"

    button_classes = re.findall(r'<button[^>]*class="([^"]+)"', markup)
    assert len(button_classes) == len(re.findall(r"<button\b", markup))
    for classes in button_classes:
        class_names = classes.split()
        assert "btn" in class_names or "btn-close" in class_names

    for classes in re.findall(r'<input[^>]*class="([^"]+)"', markup):
        assert "form-control" in classes.split()

    for classes in re.findall(r'<textarea[^>]*class="([^"]+)"', markup):
        assert "form-control" in classes.split()

    for classes in re.findall(r'<select[^>]*class="([^"]+)"', markup):
        assert "form-select" in classes.split()

    styles = (STATIC / "styles.css").read_text()
    assert ".btn { min-height: 42px; }" in styles
    assert ".form-control, .form-select {\n  min-height: 42px;" in styles
    assert ".button { min-height: 42px;" in styles
    assert ".filter { min-height: 42px;" in styles
    assert ".audit-filters > .form-label {\n  margin-bottom: 0;" in styles
    assert ".audit-filter-actions .button {\n  flex: 1;\n  height: 42px;" in styles
    assert "max-height: 62vh;" in styles
    assert "overflow: auto;" in styles
    assert ".audit-head { position: sticky;" in styles
