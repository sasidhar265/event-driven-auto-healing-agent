/* Operational metrics, recent events, and confidence decision records. */
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
