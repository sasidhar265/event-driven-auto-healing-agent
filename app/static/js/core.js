/* Shared DOM, API, escaping, notification, and modal utilities. */
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
