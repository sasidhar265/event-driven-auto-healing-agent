const scenarios = {
  ui: {
    symbol: "⌖", name: "UI locator", summary: "Obsolete XPath after a DOM change",
    type: "ui.xpath.element_not_found", source: "ci://checkout-ui-tests",
    payload: {
      failure_category: "ui",
      test_file: "tests/ui/test_checkout.py",
      test_name: "test_submit_order",
      error: "NoSuchElement: XPath did not match any element",
      failed_locator: {strategy: "xpath", value: "//button[@id='submit-order']"},
      dom_candidates: [{
        tag: "button", text: "Submit order",
        attributes: {"data-testid": "submit-order", "aria-label": "Submit order"}
      }],
      build_id: "preprod-762"
    },
    route: [
      ["Evidence", "failed_locator and dom_candidates identify a browser locator failure."],
      ["Classification", "Explicit UI category receives the strongest routing weight."],
      ["Specialist", "XPath investigator compares stable locator candidates."],
      ["Expected fix", "Replace obsolete XPath with a unique data-testid selector."]
    ]
  },
  api: {
    symbol: "⇄", name: "API timeout", summary: "Orders endpoint exceeds its latency budget",
    type: "api.test.timeout", source: "ci://orders-integration-tests",
    payload: {
      failure_category: "api", test_file: "tests/api/test_orders.py",
      test_name: "test_create_order", source_file: "app/orders.py",
      method_name: "create_order", endpoint: "/orders", http_method: "POST",
      timeout_ms: 5000, response_time_ms: 8120, exception_type: "ReadTimeout",
      trace_id: "trace-preprod-42", error: "POST /orders timed out after 5000ms"
    },
    route: [
      ["Evidence", "Endpoint, HTTP method, timeout, and trace ID identify an API boundary."],
      ["Classification", "Structured API fields outweigh incidental text in logs."],
      ["Specialist", "API agent targets app/orders.py:create_order."],
      ["Expected fix", "Trace downstream latency before changing handler or timeout behavior."]
    ]
  },
  logic: {
    symbol: "ƒ", name: "Logic exception", summary: "Null state reaches a calculation branch",
    type: "application.logic.exception", source: "ci://pricing-unit-tests",
    payload: {
      failure_category: "logic", test_file: "tests/test_pricing.py",
      test_name: "test_discount_without_membership", source_file: "app/pricing.py",
      method_name: "calculate_discount", exception_type: "TypeError",
      stack_trace: "TypeError: unsupported operand for None\n  at app/pricing.py:74 in calculate_discount",
      expected_result: 0, actual_result: "exception",
      error: "membership discount was None"
    },
    route: [
      ["Evidence", "Exception type, stack trace, source file, and method locate the failing branch."],
      ["Classification", "Explicit logic category resolves competing functional signals."],
      ["Specialist", "Logic agent targets the first application stack frame."],
      ["Expected fix", "Restore the violated invariant and add a regression test."]
    ]
  },
  functional: {
    symbol: "⇥", name: "Workflow", summary: "Order state differs from the expected result",
    type: "business.workflow.assertion_failed", source: "ci://orders-functional-tests",
    payload: {
      failure_category: "functional", test_file: "tests/functional/test_orders.py",
      test_name: "test_paid_order_transitions_to_fulfilment",
      source_file: "app/workflows/orders.py", method_name: "advance_order",
      workflow: "order_fulfilment", expected_result: "ready_for_fulfilment",
      actual_result: "payment_confirmed", error: "order did not advance after payment"
    },
    route: [
      ["Evidence", "Expected/actual states and workflow name identify a business transition."],
      ["Classification", "Functional fields route away from generic logic handling."],
      ["Specialist", "Workflow agent targets advance_order."],
      ["Expected fix", "Correct the transition while preserving adjacent valid states."]
    ]
  },
  test_data: {
    symbol: "▦", name: "Test data", summary: "Fixture no longer matches the input schema",
    type: "test.fixture.validation_failed", source: "ci://customer-tests",
    payload: {
      failure_category: "test_data", test_file: "tests/fixtures/customers.py",
      test_name: "test_create_customer", fixture: "valid_customer",
      dataset: "customer-v3", expected_result: "email is required",
      actual_result: "email field absent", error: "ValidationError: email is required"
    },
    route: [
      ["Evidence", "Fixture, dataset, and schema expectation identify test data."],
      ["Classification", "Explicit test_data category routes to the data specialist."],
      ["Specialist", "Test-data agent inspects the smallest invalid fixture value."],
      ["Expected fix", "Update the fixture to the current schema and rerun consumers."]
    ]
  },
  database: {
    symbol: "◉", name: "Database", summary: "PostgreSQL deadlock aborts an order update",
    type: "database.transaction.deadlock", source: "apm://orders-database",
    payload: {
      failure_category: "database", database_system: "postgres",
      sql_state: "40P01", query_name: "update_order_status",
      query: "UPDATE orders SET status = $1 WHERE id = $2",
      source_file: "app/repositories/orders.py", method_name: "update_status",
      trace_id: "trace-db-preprod", error: "DeadlockDetected: deadlock detected"
    },
    route: [
      ["Evidence", "SQL state, query identity, and database engine identify transactional failure."],
      ["Classification", "Database fields outweigh the generic exception text."],
      ["Specialist", "Database agent targets the repository transaction boundary."],
      ["Expected fix", "Normalize lock ordering and validate transaction and query-plan behavior."]
    ]
  },
  infrastructure: {
    symbol: "△", name: "Infrastructure", summary: "Kubernetes workload is repeatedly OOM-killed",
    type: "kubernetes.pod.oomkilled", source: "monitoring://preprod-eu",
    payload: {
      failure_category: "infrastructure", cluster: "preprod-eu",
      namespace: "orders", pod: "orders-api-7d8f", container: "api",
      resource_metrics: {memory_limit_mb: 512, peak_memory_mb: 611},
      manifest_file: "deploy/orders-api.yaml", resource_name: "orders-api",
      error: "OOMKilled with exit code 137"
    },
    route: [
      ["Evidence", "Cluster, workload identity, exit reason, and resource metrics locate the failure."],
      ["Classification", "Kubernetes and OOM signals route to infrastructure."],
      ["Specialist", "Infrastructure agent targets the owning deployment manifest."],
      ["Expected fix", "Confirm leak versus capacity, then make a bounded manifest change."]
    ]
  },
  dependency: {
    symbol: "⛓", name: "Dependency", summary: "Payments service is unavailable upstream",
    type: "dependency.upstream.unavailable", source: "apm://orders-api",
    payload: {
      failure_category: "dependency", dependency_name: "payments-api",
      dependency_endpoint: "/authorize", upstream_status: 503,
      config_file: "config/orders-resilience.yaml", resource_name: "payments-client",
      trace_id: "trace-dependency-preprod", error: "upstream service unavailable"
    },
    route: [
      ["Evidence", "Dependency name, endpoint, status, and trace identify an upstream boundary."],
      ["Classification", "Explicit dependency evidence prevents misrouting as a local API bug."],
      ["Specialist", "Dependency agent inspects health and resilience configuration."],
      ["Expected fix", "Correct the boundary or resilience policy without masking persistent failure."]
    ]
  },
  security: {
    symbol: "◆", name: "Security", summary: "Service principal is denied an approved action",
    type: "security.authorization.forbidden", source: "security://access-control",
    payload: {
      failure_category: "security", security_control: "authorization",
      principal: "orders-worker", permission: "payments.authorize",
      source_file: "access/orders.rego", resource_name: "payments-authorization",
      error: "403 forbidden: required permission is absent"
    },
    route: [
      ["Evidence", "Security control, principal, and permission identify authorization failure."],
      ["Classification", "Security evidence takes precedence over the HTTP 403 symptom."],
      ["Specialist", "Security agent targets the least-privilege access definition."],
      ["Expected fix", "Restore only the required permission through an approved workflow."]
    ]
  },
  performance: {
    symbol: "⌁", name: "Performance", summary: "Endpoint p95 regresses far beyond baseline",
    type: "performance.latency.regression", source: "apm://orders-api",
    payload: {
      failure_category: "performance", endpoint: "/orders",
      baseline_ms: 180, observed_ms: 1450, p95_ms: 1700,
      profile: "orders-create-preprod", source_file: "app/orders.py",
      method_name: "create_order", trace_id: "trace-performance-preprod",
      error: "p95 latency regression above service objective"
    },
    route: [
      ["Evidence", "Baseline, observed latency, percentile, and profile quantify a regression."],
      ["Classification", "Explicit performance category avoids routing as a generic API timeout."],
      ["Specialist", "Performance agent targets the profiled endpoint method."],
      ["Expected fix", "Optimize the measured bottleneck and rerun representative benchmarks."]
    ]
  }
};

const titles = {
  dashboard: "Runtime overview", simulate: "Incident intake",
  suggestions: "Remediation suggestions", audit: "Audit trail"
};
let activeScenario = "ui";
let suggestionFilter = "all";
let lastAudit = [];
let recentEvents = [];
let currentSuggestions = [];
let decisionRecords = [];

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const pageParameters = new URLSearchParams(window.location.search);
const requestedEnvironment = pageParameters.get("environment");
const escapeHtml = (value = "") => String(value).replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
}[char]));
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

function settings() {
  return {
    base: localStorage.getItem("art.base") || "",
    key: localStorage.getItem("art.key") || "change-me",
    tenant: "retail-banking-preprod",
    actor: localStorage.getItem("art.actor") || "qe-operations"
  };
}

async function api(path, options = {}) {
  const config = settings();
  const response = await fetch(`${config.base}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": config.key,
      "X-Tenant-Id": config.tenant,
      "X-Actor": config.actor,
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* no JSON */ }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function toast(message, error = false) {
  const item = document.createElement("div");
  item.className = `toast${error ? " error" : ""}`;
  item.textContent = message;
  $("#toast-region").append(item);
  setTimeout(() => item.remove(), 3500);
}

function showDetails(title, eyebrow, content) {
  $("#details-title").textContent = title;
  $("#details-eyebrow").textContent = eyebrow;
  $("#details-content").innerHTML = content;
  bootstrap.Modal.getOrCreateInstance($("#details-dialog")).show();
}

function detailJson(label, value) {
  return `
    <section class="modal-detail">
      <b>${escapeHtml(label)}</b>
      <pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>
    </section>`;
}

function renderTraceStage(stage, index) {
  const details = stage.details || {};
  const hasDetails = Object.keys(details).length > 0;
  const level = ["failed", "suppressed", "rejected"].includes(stage.status) ? "error" :
    ["pending", "processing", "review"].includes(stage.status) ? "warn" : "info";
  return `
    <article class="trace-log-row ${escapeHtml(level)}">
      <div class="trace-log-main">
        <time>${escapeHtml(formatLogTime(stage.timestamp))}</time>
        <span class="trace-sequence">${String(index + 1).padStart(2, "0")}</span>
        <span class="trace-level">${escapeHtml(level.toUpperCase())}</span>
        <div>
          <span class="trace-stage-name">${escapeHtml(stage.name)}</span>
          <span class="trace-message">${escapeHtml(stage.summary)}</span>
        </div>
        <span class="pill ${escapeHtml(stage.status)}">${escapeHtml(stage.status)}</span>
      </div>
      <div class="trace-log-meta">
        <div>
          <b>runtime</b>
          <code>${escapeHtml(stage.api)}</code>
        </div>
        <div>
          <b>data</b>
          <code>${escapeHtml(stage.data.join(" · "))}</code>
        </div>
      </div>
      ${hasDetails ? `<details><summary>View structured context</summary>${detailJson("Log context", details)}</details>` : ""}
    </article>`;
}

function formatLogTime(value) {
  if (!value) return "pending";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
    hour12: false
  }).format(new Date(value));
}

async function showEventDetails(item) {
  showDetails(item.event_type, "INCIDENT PROCESSING TRACE", `
    <div class="detail-summary">
      <span class="pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>
      <span>${escapeHtml(item.external_id)}</span>
    </div>
    <dl class="detail-list">
      <div><dt>Identified by</dt><dd>${escapeHtml(item.source || "Source not provided")}</dd></div>
      <div><dt>Environment</dt><dd>${escapeHtml(item.environment || "unknown")}</dd></div>
      <div><dt>Created</dt><dd>${formatDate(item.created_at)}</dd></div>
      <div><dt>Severity</dt><dd>${escapeHtml(item.severity)}</dd></div>
      <div><dt>Event ID</dt><dd><code>${escapeHtml(item.id)}</code></dd></div>
    </dl>
    <div class="trace-loading">Loading lifecycle stages from PostgreSQL…</div>`);

  try {
    const trace = await api(`/v1/events/${encodeURIComponent(item.id)}/trace`);
    $("#details-content").innerHTML = `
      <div class="detail-summary">
        <span class="pill ${escapeHtml(trace.event_status)}">${escapeHtml(trace.event_status)}</span>
        <span>${escapeHtml(item.external_id)}</span>
      </div>
      <dl class="detail-list trace-context">
        <div><dt>Correlation ID</dt><dd><code>${escapeHtml(trace.correlation_id)}</code></dd></div>
        <div><dt>Environment</dt><dd>${escapeHtml(trace.environment)}</dd></div>
        <div><dt>Identified by</dt><dd>${escapeHtml(item.source || "Source not provided")}</dd></div>
      </dl>
      <div class="trace-intro">
        <p class="eyebrow">CORRELATED RUNTIME LOG</p>
        <h3>Incident processing logs</h3>
        <p>Chronological entries reconstructed from tenant-scoped API and PostgreSQL records.</p>
      </div>
      <div class="trace-log">
        <div class="trace-log-header">
          <span>Timestamp</span><span>Seq</span><span>Level</span><span>Stage and message</span><span>Status</span>
        </div>
        ${trace.stages.map(renderTraceStage).join("")}
      </div>`;
  } catch (error) {
    $(".trace-loading").textContent = `Unable to load lifecycle trace: ${error.message}`;
  }
}

function showSuggestionDetails(item) {
  const route = item.proposed_changes.routing || {};
  const target = item.proposed_changes.target || {};
  const canDecide = item.status === "review" || item.status === "ready";

  showDetails(item.title, "REMEDIATION SUGGESTION", `
    <div class="detail-summary">
      <span class="category ${escapeHtml(route.category || item.agent_type)}">${escapeHtml(item.agent_type)}</span>
      <span class="pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>
      <strong>${(item.confidence * 100).toFixed(0)}% confidence</strong>
    </div>
    <p class="modal-rationale">${escapeHtml(item.rationale)}</p>
    <div class="modal-detail-grid">
      ${detailJson("Routing and target", {
        category: route.category,
        matched_signals: route.matched_signals,
        file: target.file,
        method: target.method
      })}
      ${detailJson("Proposed changes", item.proposed_changes)}
    </div>
    ${canDecide ? `
      <div class="modal-actions">
        <button class="btn btn-outline-secondary button secondary" data-modal-decision="rejected" data-id="${item.id}">Reject</button>
        <button class="btn btn-primary button primary" data-modal-decision="accepted" data-id="${item.id}">Accept suggestion</button>
      </div>` : ""}`);

  $$("[data-modal-decision]").forEach(button => {
    button.addEventListener("click", decideSuggestion);
  });
}

function navigate(view) {
  $$(".view").forEach(item => item.classList.toggle("active", item.id === view));
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === view));
  $("#page-title").textContent = titles[view];
  window.location.hash = view;
  if (view === "suggestions") loadSuggestions();
  if (view === "audit") loadAudit();
  if (view === "dashboard") loadOverview();
  window.scrollTo({top: 0, behavior: "smooth"});
}

function renderScenarios() {
  $("#scenario-grid").innerHTML = Object.entries(scenarios).map(([key, item]) => `
    <button class="btn scenario ${key === activeScenario ? "active" : ""}" data-scenario="${key}">
      <span class="scenario-symbol">${item.symbol}</span>
      <b>${item.name}</b><small>${item.summary}</small>
    </button>`).join("");
  $$(".scenario").forEach(button => button.addEventListener("click", () => selectScenario(button.dataset.scenario)));
}

function selectScenario(key) {
  activeScenario = key;
  const item = scenarios[key];
  renderScenarios();
  $("#scenario-title").textContent = item.name;
  $("#category-badge").textContent = key.replace("_", " ");
  $("#category-badge").className = `category ${key}`;
  $("#event-type").value = item.type;
  $("#event-source").value = item.source;
  $("#correlation-key").value = crypto.randomUUID();
  $("#event-payload").value = JSON.stringify(item.payload, null, 2);
  $("#route-preview").innerHTML = item.route.map((step, index) => `
    <div class="route-step"><i>${index + 1}</i><div><b>${step[0]}</b><small>${step[1]}</small></div></div>
  `).join("");
  $("#result-panel").classList.add("hidden");
  validatePayload();
}

function validatePayload() {
  try {
    JSON.parse($("#event-payload").value);
    $("#event-validity").textContent = "Valid JSON";
    $("#event-validity").classList.remove("invalid");
    return true;
  } catch (error) {
    $("#event-validity").textContent = error.message;
    $("#event-validity").classList.add("invalid");
    return false;
  }
}

async function submitEvent(event) {
  event.preventDefault();
  if (!validatePayload()) return;
  const button = event.submitter;
  button.disabled = true;
  button.textContent = "Processing…";
  try {
    const body = {
      external_id: `incident-${crypto.randomUUID()}`,
      event_type: $("#event-type").value,
      source: $("#event-source").value,
      severity: $("#severity").value,
      correlation_key: $("#correlation-key").value,
      payload: {
        ...JSON.parse($("#event-payload").value),
        environment: $("#event-environment").value,
        deployment_region: "eu-west-2",
        service_tier: $("#service-tier").value
      }
    };
    const created = await api("/v1/events", {method: "POST", body: JSON.stringify(body)});
    $("#result-panel").classList.remove("hidden");
    $("#processing-result").innerHTML = `
      <div class="result-status"><b>Event accepted</b><span class="pill received">received</span></div>
      <p>The ART worker is classifying and routing this event. Event ID:<br><code>${escapeHtml(created.id)}</code></p>`;
    toast("Failure event accepted");
    let trace = null;
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await sleep(750);
      trace = await api(`/v1/events/${encodeURIComponent(created.id)}/trace`);
      const outcome = trace.stages.find(stage => stage.key === "outcome");
      if (outcome && outcome.status !== "pending") break;
    }
    const suggestion = trace?.stages.find(stage => stage.key === "suggestion");
    const confidence = trace?.stages.find(stage => stage.key === "confidence");
    const outcome = trace?.stages.find(stage => stage.key === "outcome");
    if (suggestion?.details?.title) {
      $("#processing-result").innerHTML = `
        <div class="result-status"><b>${escapeHtml(suggestion.details.agent)} specialist</b><span class="pill ${escapeHtml(outcome.status)}">${escapeHtml(outcome.status)}</span></div>
        <h3>${escapeHtml(suggestion.details.title)}</h3>
        <p>${escapeHtml(suggestion.details.rationale)}</p>
        <p><b>Confidence:</b> ${escapeHtml(confidence.details.score_percent)}%</p>
        <button class="btn btn-outline-secondary button secondary" id="view-result">View processing logs</button>`;
      $("#view-result").addEventListener("click", () => showEventDetails({
        ...created,
        source: body.source,
        environment: body.payload.environment
      }));
    } else {
      $("#processing-result").innerHTML += `<p>No suggestion was produced yet. The event remains available in the audit trail.</p>`;
    }
    loadOverview();
  } catch (error) {
    toast(error.message, true);
    showDisconnected();
  } finally {
    button.disabled = false;
    button.innerHTML = "Send event to runtime <span>→</span>";
  }
}

function showDisconnected() {
  $("#connection-banner").classList.remove("hidden");
}

async function loadOverview() {
  try {
    const environment = $("#activity-environment").value;
    const query = environment ? `?environment=${encodeURIComponent(environment)}` : "";
    const data = await api(`/v1/overview${query}`);
    recentEvents = data.recent_events;
    $("#connection-banner").classList.add("hidden");
    ["events", "processing", "suggestions", "ready"].forEach(key => {
      $(`#metric-${key}`).textContent = data[key];
    });
    const decisionModel = data.decision_model || {counts: {}, total: 0};
    ["suppressed", "review", "ready"].forEach(classification => {
      $(`#decision-${classification}`).textContent =
        decisionModel.counts[classification] || 0;
    });
    $("#decision-summary").textContent = decisionModel.total
      ? `${decisionModel.total} suggestion${decisionModel.total === 1 ? "" : "s"} classified by confidence and policy evidence.`
      : "No suggestions classified for this environment.";
    decisionRecords = decisionModel.records || [];
    renderDecisionRecords();
    $("#recent-events").classList.remove("empty-state");
    $("#recent-events").innerHTML = data.recent_events.length ? data.recent_events.map(item => `
      <button class="btn event-row event-row-button" data-event-id="${item.id}" type="button">
        <span class="event-icon">${eventIcon(item.event_type)}</span>
        <div>
          <b>${escapeHtml(item.event_type)}</b>
          <small>
            <span class="category ${escapeHtml(item.environment)}">${escapeHtml(item.environment)}</span>
            Identified by ${escapeHtml(item.source || "unknown source")} · ${formatDate(item.created_at)}
          </small>
        </div>
        <span class="pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>
      </button>`).join("") : `<div class="empty-state">No incidents have been received for this tenant.</div>`;
    $$("[data-event-id]").forEach(button => {
      button.addEventListener("click", () => {
        const item = recentEvents.find(event => event.id === button.dataset.eventId);
        if (item) showEventDetails(item);
      });
    });
  } catch (_) {
    showDisconnected();
    $("#recent-events").className = "event-list empty-state";
    $("#recent-events").textContent = "Connect to a running API and PostgreSQL database to see activity.";
  }
}

function renderDecisionRecords() {
  const state = $("#decision-state-filter").value;
  const ranking = $("#decision-ranking").value;
  const records = decisionRecords
    .filter(item => state === "all" || item.classification === state)
    .sort((left, right) => {
      if (ranking === "lowest") return left.confidence - right.confidence;
      if (ranking === "newest") return new Date(right.created_at) - new Date(left.created_at);
      return right.confidence - left.confidence;
    });
  $("#decision-records").innerHTML = records.length ? records.map(item => `
    <div class="decision-row">
      <code title="${escapeHtml(item.failure_id)}">${escapeHtml(item.failure_id)}</code>
      <span title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</span>
      <b>${(item.confidence * 100).toFixed(0)}%</b>
      <span class="pill ${escapeHtml(item.classification)}">${escapeHtml(item.classification)}</span>
      <span class="pill ${escapeHtml(item.recorded_status)}">${escapeHtml(item.recorded_status)}</span>
    </div>`).join("") : `<div class="decision-empty">No suggestions match this state.</div>`;
}

function eventIcon(type) {
  if (type.includes("ui") || type.includes("xpath")) return "⌖";
  if (type.includes("api") || type.includes("http")) return "⇄";
  if (type.includes("fixture") || type.includes("data")) return "▦";
  if (type.includes("database")) return "◉";
  if (type.includes("kubernetes") || type.includes("infrastructure")) return "△";
  if (type.includes("dependency")) return "⛓";
  if (type.includes("security")) return "◆";
  if (type.includes("performance")) return "⌁";
  if (type.includes("workflow")) return "⇥";
  return "ƒ";
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
  }).format(new Date(value));
}

async function loadSuggestions() {
  const container = $("#suggestion-list");
  container.innerHTML = `<div class="empty-state">Loading suggestions…</div>`;
  try {
    const items = await api("/v1/suggestions");
    currentSuggestions = items;
    const statusCounts = items.reduce((counts, item) => {
      const status = String(item.status).toLowerCase();
      counts[status] = (counts[status] || 0) + 1;
      return counts;
    }, {all: items.length});
    $$("[data-status]").forEach(button => {
      button.querySelector(".filter-count").textContent = statusCounts[button.dataset.status] || 0;
    });
    const filtered = suggestionFilter === "all"
      ? items
      : items.filter(item => String(item.status).toLowerCase() === suggestionFilter);
    container.innerHTML = filtered.length ? filtered.map(renderSuggestion).join("") :
      `<div class="panel empty-state">No ${suggestionFilter === "all" ? "" : suggestionFilter} suggestions yet.</div>`;
    $$("[data-decision]").forEach(button => button.addEventListener("click", decideSuggestion));
    $$("[data-suggestion-id]").forEach(button => {
      button.addEventListener("click", () => {
        const item = currentSuggestions.find(
          suggestion => suggestion.id === button.dataset.suggestionId
        );
        if (item) showSuggestionDetails(item);
      });
    });
  } catch (error) {
    container.innerHTML = `<div class="panel empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderSuggestion(item) {
  const route = item.proposed_changes.routing || {};
  const canDecide = item.status === "review" || item.status === "ready";
  return `
    <article class="suggestion-card ${escapeHtml(item.status)}">
      <i></i><div class="suggestion-body">
        <div class="suggestion-top">
          <div>
            <div class="suggestion-meta"><span class="category ${escapeHtml(route.category || item.agent_type)}">${escapeHtml(item.agent_type)}</span><span class="pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></div>
            <h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.rationale)}</p>
          </div>
          <div class="confidence-number">${(item.confidence * 100).toFixed(0)}%<small>CONFIDENCE</small></div>
        </div>
        <div class="card-actions">
          <button class="btn btn-outline-secondary button secondary" data-suggestion-id="${item.id}">View full details</button>
          ${canDecide ? `<div class="suggestion-decision-actions"><button class="btn btn-outline-secondary button secondary" data-decision="rejected" data-id="${item.id}">Reject</button><button class="btn btn-primary button primary" data-decision="accepted" data-id="${item.id}">Accept suggestion</button></div>` : `<span class="pill ${escapeHtml(item.status)}">Decision: ${escapeHtml(item.status)}</span>`}
        </div>
      </div>
    </article>`;
}

async function decideSuggestion(event) {
  const button = event.currentTarget;
  try {
    await api(`/v1/suggestions/${button.dataset.id}/decision`, {
      method: "POST",
      body: JSON.stringify({
        decision: button.dataset.decision,
        reason: `Decision recorded from operations console by ${settings().actor}`
      })
    });
    toast(`Suggestion ${button.dataset.decision}`);
    bootstrap.Modal.getOrCreateInstance($("#details-dialog")).hide();
    loadSuggestions();
  } catch (error) { toast(error.message, true); }
}

async function loadAudit() {
  try {
    const environment = $("#audit-environment").value;
    const query = new URLSearchParams({limit: "200"});
    if (environment) query.set("environment", environment);
    const correlationId = $("#audit-correlation").value.trim();
    if (correlationId) query.set("correlation_id", correlationId);

    const selectedRange = $("#audit-time-range").value;
    const ranges = {
      "30m": 30 * 60 * 1000,
      "1h": 60 * 60 * 1000,
      "2h": 2 * 60 * 60 * 1000,
      "4h": 4 * 60 * 60 * 1000,
      "6h": 6 * 60 * 60 * 1000,
      "12h": 12 * 60 * 60 * 1000,
      "1d": 24 * 60 * 60 * 1000,
      "2d": 2 * 24 * 60 * 60 * 1000,
      "3d": 3 * 24 * 60 * 60 * 1000,
      "4d": 4 * 24 * 60 * 60 * 1000,
      "5d": 5 * 24 * 60 * 60 * 1000,
      "6d": 6 * 24 * 60 * 60 * 1000,
      "1w": 7 * 24 * 60 * 60 * 1000,
      "2w": 14 * 24 * 60 * 60 * 1000,
      "3w": 21 * 24 * 60 * 60 * 1000,
      "4w": 28 * 24 * 60 * 60 * 1000
    };
    if (ranges[selectedRange]) {
      query.set("from_time", new Date(Date.now() - ranges[selectedRange]).toISOString());
      query.set("to_time", new Date().toISOString());
    } else if (selectedRange === "custom") {
      const fromTime = $("#audit-from-time").value;
      const toTime = $("#audit-to-time").value;
      if (fromTime) query.set("from_time", new Date(fromTime).toISOString());
      if (toTime) query.set("to_time", new Date(toTime).toISOString());
    }
    lastAudit = await api(`/v1/audit?${query}`);
    $("#audit-list").innerHTML = lastAudit.length ? lastAudit.map(item => `
      <button class="btn audit-row audit-row-button" data-audit-id="${item.id}" type="button">
        <span>${formatDate(item.created_at)}</span><span>${escapeHtml(item.actor)}</span>
        <span><b>${escapeHtml(item.action)}</b></span>
        <span>${escapeHtml(item.resource_type)} · ${escapeHtml(item.resource_id.slice(0, 12))}</span>
        <code title="${escapeHtml(item.correlation_id || "Not associated")}">${escapeHtml(item.correlation_id || "—")}</code>
        <code title="${escapeHtml(item.failure_id || "Not associated")}">${escapeHtml(item.failure_id || "—")}</code>
        <code>${escapeHtml(JSON.stringify(item.details))}</code>
      </button>`).join("") : `<div class="empty-state">No audit activity yet.</div>`;
    $$("[data-audit-id]").forEach(button => button.addEventListener("click", () => {
      const item = lastAudit.find(row => String(row.id) === button.dataset.auditId);
      showDetails(item.action, "AUDIT RECORD", detailJson("Audit details", item));
    }));
  } catch (error) { toast(error.message, true); }
}

function updateCustomAuditRange() {
  const custom = $("#audit-time-range").value === "custom";
  $$(".audit-custom").forEach(field => field.classList.toggle("hidden", !custom));
  if (custom && !$("#audit-to-time").value) {
    const now = new Date();
    const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
    $("#audit-from-time")._flatpickr.setDate(oneHourAgo, true);
    $("#audit-to-time")._flatpickr.setDate(now, true);
  }
}

function initializeAuditCalendars() {
  const options = {
    enableTime: true,
    time_24hr: true,
    minuteIncrement: 1,
    dateFormat: "Y-m-d H:i",
    allowInput: false,
    clickOpens: true
  };
  flatpickr("#audit-from-time", options);
  flatpickr("#audit-to-time", options);
}

function openDateTimePicker(event) {
  const input = $(`#${event.currentTarget.dataset.pickerTarget}`);
  input._flatpickr.open();
}

function clearAuditFilters() {
  $("#audit-environment").value = "";
  $("#audit-time-range").value = "";
  $("#audit-correlation").value = "";
  $("#audit-from-time")._flatpickr.clear();
  $("#audit-to-time")._flatpickr.clear();
  updateCustomAuditRange();
  loadAudit();
}

async function openSettings() {
  const config = settings();
  $("#setting-base-url").value = config.base;
  $("#setting-api-key").value = config.key;
  $("#setting-actor").value = config.actor;
  bootstrap.Modal.getOrCreateInstance($("#settings-dialog")).show();
  $("#connection-api-endpoint").textContent = config.base || window.location.origin;
  $("#connection-runtime-status").textContent = "Checking…";
  $("#connection-database-status").textContent = "Checking…";
  try {
    const health = await api("/health/live");
    $("#connection-runtime-status").textContent =
      health.status === "ok" ? "Connected" : health.status;
    $("#connection-api-profile").textContent = health.api_profile || "unknown";
    $("#connection-database-status").textContent = health.database?.status || "unknown";
    $("#connection-database-server").textContent =
      `${health.database?.engine || "database"}://${health.database?.host || "unknown"}:${health.database?.port || "default"}`;
    $("#connection-database-identity").textContent =
      `${health.database?.name || "unknown"} / ${health.database?.username || "unknown"}`;
  } catch (error) {
    $("#connection-runtime-status").textContent = "Unavailable";
    $("#connection-database-status").textContent = "Not checked";
    $("#connection-api-profile").textContent = "—";
    $("#connection-database-server").textContent = "—";
    $("#connection-database-identity").textContent = "—";
  }
}

function saveSettings(event) {
  event.preventDefault();
  localStorage.setItem("art.base", $("#setting-base-url").value.replace(/\/$/, ""));
  localStorage.setItem("art.key", $("#setting-api-key").value);
  localStorage.setItem("art.actor", $("#setting-actor").value);
  bootstrap.Modal.getOrCreateInstance($("#settings-dialog")).hide();
  toast("Runtime connection saved");
  loadOverview();
}

function exportAudit() {
  const blob = new Blob([JSON.stringify(lastAudit, null, 2)], {type: "application/json"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `art-audit-${$("#audit-environment").value || "all-environments"}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function bindEvents() {
  $$(".nav-item").forEach(button => button.addEventListener("click", () => navigate(button.dataset.view)));
  $$(".route-button").forEach(button => button.addEventListener("click", () => navigate(button.dataset.route)));
  $("#event-payload").addEventListener("input", validatePayload);
  $("#event-form").addEventListener("submit", submitEvent);
  $("#activity-environment").addEventListener("change", loadOverview);
  $("#decision-state-filter").addEventListener("change", renderDecisionRecords);
  $("#decision-ranking").addEventListener("change", renderDecisionRecords);
  $("#audit-time-range").addEventListener("change", updateCustomAuditRange);
  $$(".audit-calendar-button").forEach(button => button.addEventListener("click", openDateTimePicker));
  $("#audit-filter-form").addEventListener("submit", event => {
    event.preventDefault();
    loadAudit();
  });
  $("#clear-audit-filters").addEventListener("click", clearAuditFilters);
  $("#settings-button").addEventListener("click", openSettings);
  $("#banner-settings").addEventListener("click", openSettings);
  $("#settings-form").addEventListener("submit", saveSettings);
  $("#refresh-button").addEventListener("click", () => navigate(location.hash.slice(1) || "dashboard"));
  $("#export-audit").addEventListener("click", exportAudit);
  $$(".filter").forEach(button => button.addEventListener("click", () => {
    suggestionFilter = button.dataset.status.toLowerCase();
    $$(".filter").forEach(item => item.classList.toggle("active", item === button));
    loadSuggestions();
  }));
}

if (["dev", "test", "preprod", "prod"].includes(requestedEnvironment)) {
  $("#event-environment").value = requestedEnvironment;
  $("#activity-environment").value = requestedEnvironment;
  $("#audit-environment").value = requestedEnvironment;
}
renderScenarios();
selectScenario("ui");
initializeAuditCalendars();
bindEvents();
navigate(titles[location.hash.slice(1)] ? location.hash.slice(1) : "dashboard");
