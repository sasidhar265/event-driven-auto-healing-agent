/* Runtime connection settings, health details, and audit export. */
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
