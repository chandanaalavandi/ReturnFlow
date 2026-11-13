"use strict";

const state = {
  scale: "starter",
  status: "ALL",
  query: "",
  page: 1,
  pages: 1,
  debounce: null,
};

const $ = (selector) => document.querySelector(selector);
const numberFormat = new Intl.NumberFormat("en-US");
const moneyFormat = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.hidden = false;
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => { toast.hidden = true; }, 6500);
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  if (!button.dataset.originalLabel) button.dataset.originalLabel = button.textContent.trim();
  button.textContent = busy ? label : button.dataset.originalLabel;
}

function renderStatusBars(statuses, total) {
  const rows = [
    ["APPROVED", "Approved", "fill-approved"],
    ["PARTIALLY_APPROVED", "Partial", "fill-partial"],
    ["REJECTED", "Rejected", "fill-rejected"],
  ];
  const host = $("#status-bars");
  host.replaceChildren();
  for (const [key, label, fillClass] of rows) {
    const count = statuses[key] || 0;
    const row = document.createElement("div");
    row.className = "status-row";
    const name = document.createElement("span");
    name.className = "status-name";
    name.textContent = label;
    const track = document.createElement("span");
    track.className = "status-track";
    const fill = document.createElement("span");
    fill.className = `status-fill ${fillClass}`;
    fill.style.width = `${total ? Math.max(1, count / total * 100) : 0}%`;
    track.append(fill);
    const value = document.createElement("span");
    value.className = "status-count";
    value.textContent = numberFormat.format(count);
    row.append(name, track, value);
    host.append(row);
  }
}

function renderDispositions(dispositions) {
  const labels = [
    ["RESTOCK", "Restocked", ""],
    ["REFURBISH", "Refurbish", "refurbish"],
    ["QUARANTINE", "Quarantine", "quarantine"],
    ["SCRAP", "Scrapped", "scrap"],
  ];
  const host = $("#disposition-list");
  host.replaceChildren();
  for (const [key, label, color] of labels) {
    const item = document.createElement("div");
    item.className = "disposition-item";
    const mark = document.createElement("span");
    mark.className = `disposition-mark ${color}`;
    const copy = document.createElement("span");
    copy.className = "disposition-copy";
    const name = document.createElement("span");
    name.textContent = label;
    const count = document.createElement("strong");
    count.textContent = numberFormat.format(dispositions[key] || 0);
    copy.append(name, count);
    item.append(mark, copy);
    host.append(item);
  }
}

const exceptionNames = {
  RETURN_QTY_EXCEEDS_PURCHASE: "Quantity exceeds purchase",
  REFUND_EXCEEDS_PAID_AMOUNT: "Over-refund blocked",
  RESTOCK_BEFORE_INSPECTION: "Restock held before inspection",
  LATE_WITHOUT_OVERRIDE: "Late return without override",
  DUPLICATE_REFUND_ATTEMPT: "Duplicate payout blocked",
  MISSING_RETURN_SHIPMENT: "Return shipment missing",
};

function renderExceptions(exceptions) {
  const host = $("#exception-list");
  host.replaceChildren();
  $("#exception-count").textContent = `${exceptions.length} labelled cases`;
  for (const item of exceptions) {
    const card = document.createElement("article");
    card.className = "exception-card";
    const head = document.createElement("div");
    head.className = "exception-head";
    const dot = document.createElement("span");
    dot.className = `severity-dot ${item.severity.toLowerCase()}`;
    const title = document.createElement("span");
    title.className = "exception-title";
    title.textContent = exceptionNames[item.issue_type] || item.issue_type.replaceAll("_", " ");
    head.append(dot, title);
    const entity = document.createElement("div");
    entity.className = "exception-entity";
    entity.textContent = `${item.entity_type} / ${item.entity_id}`;
    const outcome = document.createElement("p");
    outcome.className = "exception-outcome";
    outcome.textContent = item.expected_outcome;
    card.append(head, entity, outcome);
    host.append(card);
  }
}

async function loadSummary() {
  const summary = await requestJson(`/api/summary?scale=${encodeURIComponent(state.scale)}`);
  const metrics = summary.metrics;
  const requests = metrics.return_requests;
  $("#metric-orders").textContent = numberFormat.format(metrics.orders);
  $("#metric-requests").textContent = numberFormat.format(requests);
  $("#metric-rate").textContent = `${metrics.orders ? (requests / metrics.orders * 100).toFixed(1) : "0.0"}%`;
  $("#metric-authorized").textContent = numberFormat.format(metrics.authorized_requests);
  $("#metric-refunds").textContent = moneyFormat.format(metrics.refund_amount_issued_cents / 100);
  const successfulRefunds = (metrics.refund_attempts_by_status.ISSUED || 0)
    + (metrics.refund_attempts_by_status.CREDIT_ISSUED || 0);
  $("#metric-refund-count").textContent = numberFormat.format(successfulRefunds);
  $("#filter-all").textContent = numberFormat.format(requests);
  $("#filter-approved").textContent = numberFormat.format(metrics.requests_by_status.APPROVED || 0);
  $("#filter-partial").textContent = numberFormat.format(metrics.requests_by_status.PARTIALLY_APPROVED || 0);
  $("#filter-rejected").textContent = numberFormat.format(metrics.requests_by_status.REJECTED || 0);
  $("#dataset-note").textContent =
    `${summary.profile} dataset  |  ${numberFormat.format(requests)} requests  |  seed ${summary.seed}  |  as of ${summary.as_of_date}`;
  $("#footer-seed").textContent = `Fixed seed ${summary.seed}`;
  renderStatusBars(metrics.requests_by_status, requests);
  renderDispositions(metrics.inventory_dispositions);
  renderExceptions(summary.exceptions);
}

function statusBadge(status) {
  const labels = {
    APPROVED: ["Approved", "badge-approved"],
    PARTIALLY_APPROVED: ["Partial", "badge-partial"],
    REJECTED: ["Rejected", "badge-rejected"],
  };
  const [label, className] = labels[status] || [status, "badge-rejected"];
  const badge = document.createElement("span");
  badge.className = `status-badge ${className}`;
  badge.textContent = label;
  return badge;
}

function buildReturnRow(item) {
  const row = document.createElement("tr");
  const identity = document.createElement("td");
  const rma = document.createElement("div");
  rma.className = "id-primary";
  rma.textContent = item.rma_id;
  const order = document.createElement("div");
  order.className = "id-secondary";
  order.textContent = item.order_id;
  identity.append(rma, order);

  const date = document.createElement("td");
  date.textContent = item.requested_at;
  const reason = document.createElement("td");
  reason.textContent = item.reason.replaceAll("_", " ").toLowerCase();
  const quantity = document.createElement("td");
  quantity.textContent = `${item.approved_qty} / ${item.requested_qty}`;
  const shipmentCell = document.createElement("td");
  const shipment = document.createElement("span");
  const missingShipment = item.shipment_status === "MISSING";
  shipment.className = `shipment-badge ${missingShipment ? "shipment-missing" : "shipment-received"}`;
  shipment.textContent = missingShipment
    ? "Missing"
    : item.shipment_status === "NOT_REQUIRED" ? "Not needed" : "Received";
  shipmentCell.append(shipment);
  const refundCell = document.createElement("td");
  const amount = document.createElement("span");
  amount.className = "refund-amount";
  amount.textContent = item.refund_amount_cents ? moneyFormat.format(item.refund_amount_cents / 100) : "--";
  const refundStatus = document.createElement("span");
  refundStatus.className = "refund-status";
  refundStatus.textContent = item.refund_statuses.length
    ? item.refund_statuses.map((value) => value.replaceAll("_", " ").toLowerCase()).join(", ")
    : "Not issued";
  refundCell.append(amount, refundStatus);
  const status = document.createElement("td");
  status.append(statusBadge(item.status));
  row.append(identity, date, reason, quantity, shipmentCell, refundCell, status);
  return row;
}

async function loadReturns() {
  const params = new URLSearchParams({
    scale: state.scale,
    status: state.status,
    q: state.query,
    page: String(state.page),
    page_size: "10",
  });
  const result = await requestJson(`/api/returns?${params}`);
  const body = $("#returns-body");
  body.replaceChildren();
  if (!result.items.length) {
    const row = document.createElement("tr");
    const message = document.createElement("td");
    message.className = "table-message";
    message.colSpan = 7;
    message.textContent = "No matching return requests.";
    row.append(message);
    body.append(row);
  } else {
    for (const item of result.items) body.append(buildReturnRow(item));
  }
  $("#table-count").textContent = result.total
    ? `Showing ${numberFormat.format((result.page - 1) * result.page_size + 1)}-${numberFormat.format(Math.min(result.page * result.page_size, result.total))} of ${numberFormat.format(result.total)} requests`
    : "No requests found";
  state.pages = result.pages;
  $("#page-number").textContent = `${result.page} / ${result.pages}`;
  $("#previous-page").disabled = result.page <= 1;
  $("#next-page").disabled = result.page >= result.pages;
}

async function refreshDashboard() {
  try {
    await loadSummary();
    await loadReturns();
  } catch (error) {
    showToast(error.message, true);
    $("#returns-body").replaceChildren();
    const row = document.createElement("tr");
    const message = document.createElement("td");
    message.colSpan = 7;
    message.className = "table-message";
    message.textContent = error.message;
    row.append(message);
    $("#returns-body").append(row);
  }
}

$("#scale-select").addEventListener("change", async (event) => {
  state.scale = event.target.value;
  state.page = 1;
  await refreshDashboard();
});

$("#generate-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  setBusy(button, true, "Generating...");
  try {
    const result = await requestJson("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scale: state.scale }),
    });
    showToast(`${result.message}: ${numberFormat.format(result.counts.orders)} orders, ${numberFormat.format(result.counts.return_requests)} requests, ${numberFormat.format(result.counts.return_lines)} lines. Validation passed.`);
    await refreshDashboard();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(button, false, "Generate data");
  }
});

$("#validate-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "Validating...";
  try {
    const result = await requestJson("/api/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scale: state.scale }),
    });
    if (result.pass) {
      showToast(`Validation passed: ${numberFormat.format(result.orders)} orders, ${numberFormat.format(result.return_requests)} requests, zero structural errors.`);
    } else {
      showToast(`Validation found ${result.structural_error_count} structural errors.`, true);
    }
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Run validation <span aria-hidden="true">-&gt;</span>';
  }
});

document.querySelectorAll(".filter-chip").forEach((button) => {
  button.addEventListener("click", async () => {
    document.querySelectorAll(".filter-chip").forEach((chip) => chip.classList.remove("selected"));
    button.classList.add("selected");
    state.status = button.dataset.status;
    state.page = 1;
    try { await loadReturns(); } catch (error) { showToast(error.message, true); }
  });
});

$("#search-input").addEventListener("input", (event) => {
  window.clearTimeout(state.debounce);
  state.query = event.target.value;
  state.page = 1;
  state.debounce = window.setTimeout(async () => {
    try { await loadReturns(); } catch (error) { showToast(error.message, true); }
  }, 180);
});

$("#previous-page").addEventListener("click", async () => {
  if (state.page <= 1) return;
  state.page -= 1;
  try { await loadReturns(); } catch (error) { showToast(error.message, true); }
});

$("#next-page").addEventListener("click", async () => {
  if (state.page >= state.pages) return;
  state.page += 1;
  try { await loadReturns(); } catch (error) { showToast(error.message, true); }
});

refreshDashboard();
