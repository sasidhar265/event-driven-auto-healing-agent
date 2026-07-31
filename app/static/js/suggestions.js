/* Suggestion loading, rendering, detail, and operator decisions. */
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
