/* Suggestion loading, rendering, detail, and operator decisions. */
async function loadSuggestions() {
  const container = $("#suggestion-list");
  container.innerHTML = `<div class="empty-state">Loading suggestions…</div>`;
  try {
    const pageSize = Number($("#suggestion-page-size").value);
    const query = new URLSearchParams({
      limit: String(pageSize),
      offset: String((suggestionPage - 1) * pageSize)
    });
    const correlationId = $("#suggestion-correlation").value.trim();
    if (correlationId) query.set("correlation_id", correlationId);
    if (suggestionFilter !== "all") query.set("status", suggestionFilter);
    const {data: items, response} = await api(
      `/v1/suggestions?${query}`, {includeResponse: true}
    );
    currentSuggestions = items;
    suggestionTotal = Number(response.headers.get("X-Total-Count") || items.length);
    let statusCounts = {};
    try { statusCounts = JSON.parse(response.headers.get("X-Status-Counts") || "{}"); }
    catch (_) { statusCounts = {}; }
    $$("[data-status]").forEach(button => {
      button.querySelector(".filter-count").textContent = statusCounts[button.dataset.status] || 0;
    });
    renderSuggestionPage();
  } catch (error) {
    container.innerHTML = `<div class="panel empty-state">${escapeHtml(error.message)}</div>`;
    $("#suggestion-pagination").classList.add("hidden");
  }
}

function renderSuggestionPage() {
  const container = $("#suggestion-list");
  const pageSize = Number($("#suggestion-page-size").value);
  const pageCount = Math.max(1, Math.ceil(suggestionTotal / pageSize));
  suggestionPage = Math.min(Math.max(1, suggestionPage), pageCount);
  const items = currentSuggestions;
  container.innerHTML = items.length ? items.map(renderSuggestion).join("") :
    `<div class="panel empty-state">No matching suggestions found.</div>`;
  const pagination = $("#suggestion-pagination");
  pagination.classList.toggle("hidden", suggestionTotal === 0);
  $("#suggestion-page-summary").textContent =
    `Page ${suggestionPage} of ${pageCount} · ${suggestionTotal} suggestion${suggestionTotal === 1 ? "" : "s"}`;
  $("#suggestion-previous").disabled = suggestionPage === 1;
  $("#suggestion-next").disabled = suggestionPage === pageCount;

  $$("[data-decision]").forEach(button => button.addEventListener("click", decideSuggestion));
    $$("[data-suggestion-id]").forEach(button => {
      button.addEventListener("click", () => {
        const item = currentSuggestions.find(
          suggestion => suggestion.id === button.dataset.suggestionId
        );
        if (item) showSuggestionDetails(item);
      });
    });
    $$("[data-confidence-id]").forEach(button => {
      button.addEventListener("click", () => {
        const item = currentSuggestions.find(
          suggestion => suggestion.id === button.dataset.confidenceId
        );
        if (item) showSuggestionConfidence(item);
      });
    });
}

function renderSuggestion(item) {
  const route = item.proposed_changes.routing || {};
  const canDecide = item.status === "review" || item.status === "ready";
  return `
    <article class="suggestion-card ${escapeHtml(item.status)}">
      <i></i><div class="suggestion-body">
        <div class="suggestion-top">
          <div>
            <div class="suggestion-meta"><span class="category ${escapeHtml(route.category || item.agent_type)}">${escapeHtml(item.agent_type)}</span><span class="pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span><code title="Correlation ID">${escapeHtml(item.correlation_id || "No correlation ID")}</code></div>
            <h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.rationale)}</p>
          </div>
          <button class="btn confidence-number confidence-button" data-confidence-id="${item.id}" type="button" title="View confidence calculation">${(item.confidence * 100).toFixed(0)}%<small>VIEW CALCULATION</small></button>
        </div>
        <div class="card-actions">
          <button class="btn btn-outline-secondary button secondary" data-suggestion-id="${item.id}">View full details</button>
          ${canDecide ? `<div class="suggestion-decision-actions"><button class="btn btn-outline-secondary button secondary" data-decision="rejected" data-id="${item.id}">Reject</button><button class="btn btn-primary button primary" data-decision="accepted" data-id="${item.id}">Accept suggestion</button></div>` : `<span class="pill ${escapeHtml(item.status)}">Decision: ${escapeHtml(item.status)}</span>`}
        </div>
      </div>
    </article>`;
}

async function showSuggestionConfidence(item) {
  showDetails(`${(item.confidence * 100).toFixed(0)}% confidence`, "SUGGESTION DECISION", `
    <div class="trace-loading">Loading confidence evidence and calculation…</div>`);
  try {
    const trace = await api(`/v1/events/${encodeURIComponent(item.event_id)}/trace`);
    const classification = trace.stages.find(stage => stage.key === "classification");
    const confidence = trace.stages.find(stage => stage.key === "confidence");
    $("#details-content").innerHTML = `
      <div class="detail-summary">
        <span class="category ${escapeHtml(item.agent_type)}">${escapeHtml(item.agent_type)}</span>
        <span class="pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>
        <strong>${(item.confidence * 100).toFixed(1)}%</strong>
      </div>
      <div class="trace-intro"><div><p class="eyebrow">HOW THIS SCORE WAS PRODUCED</p><h3>Confidence evidence</h3><p>Classification confidence selects the specialist; suggestion confidence determines suppression, review, or readiness.</p></div></div>
      ${classification?.details?.category ? renderClassificationDecision(classification.details) : ""}
      ${confidence ? renderSuggestionConfidenceCalculation(confidence.details) : ""}`;
  } catch (error) {
    $("#details-content").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
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
