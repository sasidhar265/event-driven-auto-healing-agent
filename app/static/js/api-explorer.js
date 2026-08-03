/* Live OpenAPI discovery and UI-to-endpoint correlation. */
const apiUiUsage = {
  "POST /v1/art/failure-events": {
    purpose: "Register a normalized execution, API, UI, data, batch, or infrastructure failure.",
    use: "Use when ART receives a new failure that needs classification and remediation analysis.",
    data: "Writes failure_events; large or sensitive evidence should be supplied by payload_ref or artifact_refs.",
    input: "Requires correlation_id, environment, source_system, category, and severity context."
  },
  "GET /v1/art/failure-events": {
    purpose: "Retrieve failure records together with correlated event transport history.",
    use: "Use for incident intake screens, diagnostics, and correlation-based failure investigation.",
    data: "Reads failure_events and includes event_inbox and event_outbox rows in data.related.",
    input: "Filter with correlation_id, environment, and limit."
  },
  "POST /v1/art/agent-runs": {
    purpose: "Start and persist an ART workflow triggered by a change or failure.",
    use: "Use when classification, impact analysis, test selection, orchestration, or self-maintenance begins.",
    data: "Writes agent_runs with workflow, status, governance, retry, and provenance metadata.",
    input: "Requires correlation_id, environment, and workflow_type."
  },
  "GET /v1/art/agent-runs": {
    purpose: "Retrieve an agent workflow with its execution and explainability details.",
    use: "Use for workflow monitoring, agent diagnostics, decision review, and audit evidence.",
    data: "Reads agent_runs and includes agent_run_steps and agent_decision_journals in data.related.",
    input: "Filter with correlation_id, environment, and limit."
  },
  "POST /v1/art/impact-assessments": {
    purpose: "Persist the assessed impact of a change or failure on a component or capability.",
    use: "Use after context analysis determines affected services, risk, confidence, or test tags.",
    data: "Writes impact_assessments; dependencies remain normalized in impact_dependencies.",
    input: "Requires correlation_id, environment, impact_source, component_name, and impact_level."
  },
  "GET /v1/art/impact-assessments": {
    purpose: "Retrieve impact analysis and its upstream, downstream, or lateral dependencies.",
    use: "Use for blast-radius views, risk review, dependency analysis, and test-planning context.",
    data: "Reads impact_assessments and includes impact_dependencies in data.related.",
    input: "Filter with correlation_id, environment, and limit."
  },
  "POST /v1/art/execution-intents": {
    purpose: "Record ART's governed intention to execute selected and sequenced tests.",
    use: "Use after test selection and governance evaluation; this records intent and does not bypass approval.",
    data: "Writes execution_intents with tests, sequence, constraints, policy decision, and approval state.",
    input: "Requires correlation_id, environment, execution_target, and selected_tests."
  },
  "GET /v1/art/execution-intents": {
    purpose: "Retrieve the execution decision and the complete correlated outcome bundle.",
    use: "Use for governance review, execution monitoring, healing review, and outcome learning.",
    data: "Includes test selections, result references, self-heal proposals, outcome feedback, and event_outbox in data.related.",
    input: "Filter with correlation_id, environment, and limit."
  }
};

function apiUsage(method, path, operation) {
  return apiUiUsage[`${method.toUpperCase()} ${path}`] || {
    purpose: operation.description || "Runtime API operation.",
    use: "Use through the active runtime API profile.",
    data: "See the OpenAPI schema for persisted fields.",
    input: "See interactive API docs for parameters."
  };
}

async function loadApis() {
  const container = $("#api-list");
  $("#swagger-link").href = `${settings().base || ""}/docs`;
  container.className = "api-list empty-state";
  container.textContent = "Loading the active OpenAPI contract…";
  try {
    const contract = await api("/openapi.json", {cache: "no-store"});
    const endpoints = Object.entries(contract.paths || {})
      .flatMap(([path, operations]) => Object.entries(operations)
        .filter(([method]) => ["get", "post", "put", "patch", "delete"].includes(method))
        .map(([method, operation]) => ({path, method, operation}))
      )
      .sort((left, right) => left.path.localeCompare(right.path)
        || left.method.localeCompare(right.method));
    container.className = "api-list";
    container.innerHTML = endpoints.length ? endpoints.map(({path, method, operation}) => {
      const usage = apiUsage(method, path, operation);
      return `
      <article class="api-row">
        <span class="api-method ${escapeHtml(method)}">${escapeHtml(method.toUpperCase())}</span>
        <div class="api-description">
          <code>${escapeHtml(path)}</code>
          <b>${escapeHtml(operation.summary || operation.operationId || "API operation")}</b>
          <p>${escapeHtml(usage.purpose)}</p>
          <dl class="api-usage">
            <div><dt>When to use</dt><dd>${escapeHtml(usage.use)}</dd></div>
            <div><dt>Database usage</dt><dd>${escapeHtml(usage.data)}</dd></div>
            <div><dt>Request / filters</dt><dd>${escapeHtml(usage.input)}</dd></div>
          </dl>
        </div>
        <span class="category">${escapeHtml((operation.tags || ["Operations"])[0])}</span>
      </article>`;
    }).join("") : `<div class="empty-state">No APIs are exposed in this profile.</div>`;
  } catch (error) {
    container.className = "api-list empty-state";
    container.textContent = `Unable to load APIs: ${error.message}`;
  }
}
