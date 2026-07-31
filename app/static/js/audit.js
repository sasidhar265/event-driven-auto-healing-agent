/* Audit retrieval, filtering, date controls, and rendering. */
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
