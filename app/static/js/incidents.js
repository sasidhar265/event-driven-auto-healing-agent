/* Incident trace, navigation, scenario selection, and event submission. */
function compactLogValue(value) {
  const serialized = typeof value === "string" ? value : JSON.stringify(value);
  return serialized.length > 120 ? `${serialized.slice(0, 117)}…` : serialized;
}

function renderClassificationDecision(details) {
  const input = details.input_event || {};
  const evidence = Object.entries(details.payload_evidence || {});
  const scores = details.category_scores || [
    {category: details.category, score: details.confidence || 0},
    ...(details.alternatives || [])
  ];
  const maximum = Math.max(...scores.map(item => Number(item.score) || 0), 1);
  const calculation = details.confidence_calculation || {};
  const percent = value => `${(Number(value || 0) * 100).toFixed(1)}%`;
  return `
    <section class="classification-decision" aria-label="Classification decision explanation">
      <div class="classification-input">
        <p class="classification-label">1 · Incoming event</p>
        <strong>${escapeHtml(input.event_type || "Unknown event type")}</strong>
        <div class="classification-input-meta">
          <span>Source <b>${escapeHtml(input.source || "unknown")}</b></span>
          <span>Severity <b>${escapeHtml(input.severity || "unknown")}</b></span>
        </div>
        <details><summary>View incoming payload evidence (${evidence.length} fields)</summary>
          <div class="classification-evidence">${evidence.map(([key, value]) => `
            <div><code>${escapeHtml(key)}</code><span>${escapeHtml(compactLogValue(value))}</span></div>`).join("")}</div>
        </details>
      </div>
      <div class="classification-signal-flow" aria-hidden="true"><span>→</span></div>
      <div class="classification-analysis">
        <p class="classification-label">2 · Weighted evidence</p>
        <div class="classification-signals">${(details.matched_signals || []).map(signal => {
          const kind = signal.startsWith("explicit:") ? "explicit" : signal.startsWith("field:") ? "field" : "text";
          return `<span class="${kind}">${escapeHtml(signal)}</span>`;
        }).join("") || "<span>No matching signals</span>"}</div>
        <div class="classification-scores">${scores.map(item => `
          <div><span>${escapeHtml(item.category)}</span><i><b style="width:${Math.max(2, (Number(item.score) || 0) / maximum * 100)}%"></b></i><strong>${Number(item.score || 0).toFixed(1)}</strong></div>`).join("")}</div>
        ${calculation.formula ? `<div class="confidence-calculation">
          <p>Confidence calculation</p>
          <div class="confidence-equation">
            <span><b>${percent(calculation.base)}</b><small>Base</small></span><i>+</i>
            <span><b>${percent(calculation.score_contribution)}</b><small>Winning score</small></span><i>+</i>
            <span><b>${percent(calculation.separation_contribution)}</b><small>Category separation</small></span><i>=</i>
            <span class="total"><b>${percent(calculation.final_confidence)}</b><small>Final</small></span>
          </div>
          <details><summary>Show formula inputs and caps</summary>
            <code>min(${percent(calculation.maximum)}, ${percent(calculation.base)} + min(${Number(calculation.winning_score).toFixed(1)}, ${Number(calculation.winning_score_cap).toFixed(1)}) × ${Number(calculation.score_multiplier).toFixed(2)} + min(${Number(calculation.separation).toFixed(1)}, ${Number(calculation.separation_cap).toFixed(1)}) × ${Number(calculation.separation_multiplier).toFixed(2)})</code>
            <small>Winner ${Number(calculation.winning_score).toFixed(1)} vs runner-up ${Number(calculation.runner_up_score).toFixed(1)}. ${calculation.ambiguity_cap_applied ? `The ${percent(calculation.ambiguity_cap)} ambiguity cap was applied.` : `Separation meets the ${Number(calculation.ambiguity_margin).toFixed(2)} ambiguity rule.`}</small>
          </details>
        </div>` : ""}
      </div>
      <div class="classification-signal-flow" aria-hidden="true"><span>→</span></div>
      <div class="classification-result">
        <p class="classification-label">3 · Routing decision</p>
        <span class="classification-category">${escapeHtml(details.category || "pending")}</span>
        <strong>${Math.round(Number(details.confidence || 0) * 100)}% confidence</strong>
        <small>${details.ambiguous ? "Ambiguous evidence—request more context" : `Route to the ${escapeHtml(details.category || "selected")} specialist`}</small>
      </div>
    </section>`;
}

function renderSuggestionConfidenceCalculation(details) {
  const calculation = details.calculation || {};
  if (!calculation.formula) return "";
  const percent = value => `${(Number(value || 0) * 100).toFixed(1)}%`;
  const adjustments = calculation.policy_adjustments || [];
  return `
    <section class="suggestion-confidence-calculation">
      <p class="classification-label">Suggestion confidence calculation</p>
      <div class="confidence-equation suggestion-equation">
        <span><b>${percent(calculation.specialist_base)}</b><small>Specialist evidence score</small></span><i>+</i>
        <span><b>${percent(calculation.adjustment_total)}</b><small>Policy adjustments</small></span><i>=</i>
        <span class="total"><b>${percent(calculation.final_confidence)}</b><small>Final confidence</small></span>
      </div>
      <p class="confidence-basis">The specialist score comes from matched failure evidence and available repair context. Governance policies can then increase or decrease it before the 0–100% clamp.</p>
      <div class="confidence-thresholds">
        <span><b>&lt; ${percent(calculation.review_threshold)}</b> Suppressed</span>
        <span><b>${percent(calculation.review_threshold)}–${percent(calculation.ready_threshold)}</b> Review</span>
        <span><b>≥ ${percent(calculation.ready_threshold)}</b> Ready</span>
      </div>
      <details><summary>Show policy adjustments and formula</summary>
        <code>${escapeHtml(calculation.formula)}</code>
        <small>${adjustments.length ? adjustments.map(item => `${item.policy}: ${percent(item.value)}`).join(" · ") : "No tenant policy changed the specialist score."}</small>
        <small>Decision: ${escapeHtml(calculation.decision || details.decision || "pending")}</small>
      </details>
    </section>`;
}

function renderTraceStage(stage, index) {
  const details = stage.details || {};
  const hasDetails = Object.keys(details).length > 0;
  const level = ["failed", "suppressed", "rejected"].includes(stage.status) ? "error" :
    ["pending", "processing", "review"].includes(stage.status) ? "warn" : "info";
  const searchable = [stage.name, stage.summary, stage.api, ...(stage.data || []), JSON.stringify(details)].join(" ").toLowerCase();
  return `
    <article class="trace-log-row ${escapeHtml(level)}" data-log-level="${escapeHtml(level)}" data-log-search="${escapeHtml(searchable)}">
      <div class="trace-rail"><span></span><i></i></div>
      <div class="trace-entry">
        <div class="trace-entry-head">
          <div class="trace-entry-identity">
            <span class="trace-sequence">${String(index + 1).padStart(2, "0")}</span>
            <time>${escapeHtml(formatLogTime(stage.timestamp))}</time>
            <span class="trace-level">${escapeHtml(level.toUpperCase())}</span>
          </div>
          <span class="pill ${escapeHtml(stage.status)}">${escapeHtml(stage.status)}</span>
        </div>
        <div class="trace-entry-message">
          <span class="trace-stage-name">${escapeHtml(stage.name)}</span>
          <span class="trace-message">${escapeHtml(stage.summary)}</span>
        </div>
        ${stage.key === "classification" && details.category ? renderClassificationDecision(details) : ""}
        ${stage.key === "confidence" ? renderSuggestionConfidenceCalculation(details) : ""}
        <div class="trace-log-meta">
          <span><b>Source</b><code>${escapeHtml(stage.api)}</code></span>
          <span><b>Data</b><code>${escapeHtml(stage.data.join(" · "))}</code></span>
        </div>
        ${hasDetails ? `<details><summary>Inspect structured context</summary>${detailJson("Log context", details)}</details>` : ""}
      </div>
    </article>`;
}

function filterTraceLogs() {
  const query = ($("#trace-search")?.value || "").trim().toLowerCase();
  const level = $("#trace-level-filter")?.value || "all";
  let visible = 0;
  $$(".trace-log-row").forEach(row => {
    const matches = (!query || row.dataset.logSearch.includes(query)) &&
      (level === "all" || row.dataset.logLevel === level);
    row.classList.toggle("hidden", !matches);
    if (matches) visible += 1;
  });
  $("#trace-visible-count").textContent = visible;
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
    const errorCount = trace.stages.filter(stage => ["failed", "suppressed", "rejected"].includes(stage.status)).length;
    const warningCount = trace.stages.filter(stage => ["pending", "processing", "review"].includes(stage.status)).length;
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
        <div><p class="eyebrow">CORRELATED RUNTIME LOG</p><h3>Incident processing logs</h3><p>Chronological entries reconstructed from tenant-scoped API and PostgreSQL records.</p></div>
        <div class="trace-stats">
          <span><b id="trace-visible-count">${trace.stages.length}</b> entries</span>
          <span class="warn"><b>${warningCount}</b> attention</span>
          <span class="error"><b>${errorCount}</b> errors</span>
        </div>
      </div>
      <div class="trace-controls">
        <label class="trace-search"><span>⌕</span><input class="form-control" id="trace-search" type="search" placeholder="Search stage, message, source, or data" aria-label="Search processing logs"></label>
        <select class="form-select" id="trace-level-filter" aria-label="Filter processing logs by level">
          <option value="all">All levels</option><option value="info">Info</option><option value="warn">Attention</option><option value="error">Errors</option>
        </select>
      </div>
      <div class="trace-log">
        ${trace.stages.map(renderTraceStage).join("")}
      </div>`;
    $("#trace-search").addEventListener("input", filterTraceLogs);
    $("#trace-level-filter").addEventListener("change", filterTraceLogs);
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
  window.location.hash = view;
  if (view === "suggestions") loadSuggestions();
  if (view === "audit") loadAudit();
  if (view === "api-explorer") loadApis();
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
