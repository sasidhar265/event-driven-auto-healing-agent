from pathlib import Path


STATIC = Path(__file__).parents[1] / "app" / "static"


def test_demo_ui_contains_core_workflows():
    html = (STATIC / "index.html").read_text()
    for element_id in (
        'id="dashboard"', 'id="simulate"', 'id="suggestions"',
        'id="governance"', 'id="audit"', 'id="event-form"',
    ):
        assert element_id in html


def test_demo_ui_defines_all_failure_scenarios_and_real_api_calls():
    javascript = (STATIC / "app.js").read_text()
    for category in (
        "ui", "api", "logic", "functional", "test_data", "database",
        "infrastructure", "dependency", "security", "performance",
    ):
        assert f"  {category}:" in javascript
    assert 'api("/v1/events"' in javascript
    assert 'api("/v1/suggestions' in javascript
    assert 'api("/v1/audit' in javascript


def test_detail_actions_use_modal_overlays():
    html = (STATIC / "index.html").read_text()
    javascript = (STATIC / "app.js").read_text()

    assert 'id="details-dialog"' in html
    assert 'id="details-content"' in html
    assert 'bootstrap.Modal.getOrCreateInstance($("#details-dialog")).show()' in javascript
    assert "showSuggestionDetails(result)" in javascript
    assert "data-event-id=" in javascript
    assert "data-audit-id=" in javascript


def test_bootstrap_is_loaded_and_used_for_modals_and_forms():
    html = (STATIC / "index.html").read_text()

    assert "bootstrap@5.3.8/dist/css/bootstrap.min.css" in html
    assert "bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js" in html
    assert 'class="modal fade"' in html
    assert 'class="form-control"' in html
    assert 'data-bs-dismiss="modal"' in html
