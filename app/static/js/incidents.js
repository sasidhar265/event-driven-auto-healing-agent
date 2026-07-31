/* Incident trace, navigation, scenario selection, and event submission. */
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
