/* UI event binding and application startup. */
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
  $("#reload-apis").addEventListener("click", loadApis);
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
