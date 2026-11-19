const helpers = window.ChitMirrorState;
const connection = document.querySelector("#connection");
const connectionLabel = document.querySelector("#connection-label");
const demoLoadButton = document.querySelector("#load-demo");
const sendRemindersButton = document.querySelector("#send-reminders");

function setConnection(isConnected, message) {
  if (!connection || !connectionLabel) return;
  connection.classList.toggle("connected", isConnected);
  connection.classList.toggle("failed", !isConnected);
  connectionLabel.textContent = message;
}

async function checkConnection() {
  const base = (window.CHITMIRROR_API_BASE || "").replace(/\/$/, "");
  try {
    const response = await fetch(`${base}/health`, { headers: { Accept: "application/json" } });
    if (!response.ok || (await response.json()).status !== "ok") throw new Error("Backend health check failed");
    setConnection(true, "Backend connected");
  } catch {
    setConnection(false, "Backend unavailable · showing state view");
  }
}

checkConnection();

const POLL_MS = helpers.clampPollMs(window.CHITMIRROR_POLL_MS);
const LEDGER_STATUS = {
  verified: { label: "Verified", symbol: "✓" },
  manual_approved: { label: "Manual approval", symbol: "✓" },
  needs_review: { label: "Needs review", symbol: "!" },
  overdue: { label: "Overdue", symbol: "!" },
  rejected: { label: "Rejected", symbol: "×" },
  pending: { label: "Pending", symbol: "·" }
};

const elements = {
  pageEyebrow: document.querySelector("#page-eyebrow"),
  heading: document.querySelector("#dashboard-heading"),
  subheading: document.querySelector("#dashboard-subheading"),
  groupName: document.querySelector("#group-name"),
  groupSummary: document.querySelector("#group-summary"),
  breadcrumbGroup: document.querySelector("#breadcrumb-group"),
  viewerName: document.querySelector("#viewer-name"),
  viewerRole: document.querySelector("#viewer-role"),
  periodLabel: document.querySelector("#period-label"),
  stateStatus: document.querySelector("#state-status"),
  memberSelectWrap: document.querySelector("#member-select-wrap"),
  memberSelect: document.querySelector("#member-select"),
  stateMonthTag: document.querySelector("#state-month-tag"),
  collectionPercent: document.querySelector("#collection-percent"),
  overviewCollected: document.querySelector("#overview-collected"),
  overviewPaid: document.querySelector("#overview-paid"),
  overviewReview: document.querySelector("#overview-review"),
  overviewOverdue: document.querySelector("#overview-overdue"),
  overviewNote: document.querySelector("#overview-note"),
  reviewCount: document.querySelector("#review-count"),
  reviewList: document.querySelector("#review-list"),
  overdueList: document.querySelector("#overdue-list"),
  auditList: document.querySelector("#audit-list"),
  memberPanel: document.querySelector("#member-panel"),
  memberStatementTitle: document.querySelector("#member-statement-title"),
  memberStatement: document.querySelector("#member-statement"),
  memberBubbles: document.querySelector("#member-bubbles"),
  ledgerGrid: document.querySelector("#ledger-grid"),
  ledgerSync: document.querySelector("#ledger-sync"),
  ledgerError: document.querySelector("#ledger-error"),
  ledgerFootnote: document.querySelector("#ledger-footnote")
};

let currentRole = "foreman";
let currentMemberId = window.CHITMIRROR_DEFAULT_MEMBER || "member-07";
let lastState = null;
let lastSource = "loading";
let requestPending = false;
let stopped = false;
let timer = null;
let stateRequestCount = 0;

function text(element, value) {
  if (element) element.textContent = value;
}

function html(element, value) {
  if (element) element.innerHTML = value;
}

function apiBase() {
  return (window.CHITMIRROR_API_BASE || "").replace(/\/$/, "");
}

function stateUrl() {
  const params = new URLSearchParams({ role: currentRole });
  if (currentRole === "member" && currentMemberId) params.set("member_id", currentMemberId);
  return `${apiBase()}/state?${params.toString()}`;
}

function renderMemberSelect(state) {
  const members = helpers.getMembers(state);
  if (!elements.memberSelect) return;
  if (members.length && !members.some(member => member.id === currentMemberId)) currentMemberId = members[0].id;
  elements.memberSelect.innerHTML = members
    .map(member => `<option value="${helpers.escapeHtml(member.id)}"${member.id === currentMemberId ? " selected" : ""}>${helpers.escapeHtml(member.name)}</option>`)
    .join("");
  elements.memberSelect.value = currentMemberId;
}

function renderContext(state) {
  const months = helpers.getMonths(state);
  const members = helpers.getMembers(state);
  const groupName = window.CHITMIRROR_GROUP_NAME || "Demo chit group";
  const isForeman = currentRole === "foreman";
  text(elements.groupName, groupName);
  text(elements.breadcrumbGroup, groupName);
  text(elements.groupSummary, members.length ? `${members.length} members · ${months.length} months` : "No members in shared state");
  text(elements.viewerName, isForeman ? "Foreman view" : "Member view");
  text(elements.viewerRole, isForeman ? "Group-wide demo role" : "Demo identity selector");
  text(elements.heading, isForeman ? "Foreman dashboard" : "Member dashboard");
  text(elements.subheading, isForeman
    ? "Collections, review queue and group payment health from shared state."
    : "Your statement, reminders and the shared group ledger from shared state.");
  text(elements.periodLabel, months.length ? `${months.length} months` : "No period");
  text(elements.stateMonthTag, months.length ? `${months.length} MONTHS` : "NO PERIOD");
  text(elements.ledgerFootnote, `State refreshes from the shared state contract (role: ${currentRole}). Only the shared state supplies payment status.`);
}

function renderKpis(state) {
  const kpis = helpers.deriveKpis(state);
  text(document.querySelector("[data-kpi='collected']"), kpis.collected);
  text(document.querySelector("[data-kpi='paid']"), `${kpis.paid} / ${kpis.totalMembers}`);
  text(document.querySelector("[data-kpi='review']"), String(kpis.needsReview));
  text(document.querySelector("[data-kpi='overdue']"), String(kpis.overdue));
  text(elements.collectionPercent, `${kpis.verifiedPercent}%`);
  if (elements.collectionPercent?.parentElement?.parentElement) {
    elements.collectionPercent.parentElement.parentElement.setAttribute("aria-label", `${kpis.verifiedPercent} percent of members verified`);
  }
  text(elements.overviewCollected, kpis.collected);
  text(elements.overviewPaid, `${kpis.paid} of ${kpis.totalMembers}`);
  text(elements.overviewReview, String(kpis.needsReview));
  text(elements.overviewOverdue, String(kpis.overdue));
}

function statusRow(item, state, type) {
  const name = helpers.memberLabel(state, item.member_id);
  const entry = helpers.entryFor(state, item.member_id, item.month);
  const amount = entry ? helpers.formatINR(entry.amount_paise) : "—";
  const reason = item.reason || LEDGER_STATUS[item.status]?.label || "No detail recorded";
  const actions = type === "review"
    ? `<span class="review-actions"><button type="button" data-review-id="${helpers.escapeHtml(item.item_id)}" data-review-decision="approve">Approve manually</button><button type="button" data-review-id="${helpers.escapeHtml(item.item_id)}" data-review-decision="reject">Reject</button></span>`
    : "";
  return `<div class="submission"><span class="file-icon">${type === "overdue" ? "⌛" : "▧"}</span><div class="submit-info"><b>${helpers.escapeHtml(name)}</b><small>Month ${helpers.escapeHtml(item.month)} · ${helpers.escapeHtml(reason)}</small></div><strong class="amount">${helpers.escapeHtml(amount)}</strong><span class="status ${type === "overdue" ? "rejected" : "needs-review"}"><i>!</i> ${type === "overdue" ? "Overdue" : "Needs review"}</span>${actions}</div>`;
}

function renderForemanPanels(state) {
  const flags = Array.isArray(state?.flags) ? state.flags : [];
  const overdue = Array.isArray(state?.overdue) ? state.overdue : [];
  const audit = Array.isArray(state?.audit_log) ? state.audit_log : [];
  text(elements.reviewCount, String(flags.length));
  html(elements.reviewList, flags.length
    ? flags.map(flag => statusRow(flag, state, "review")).join("")
    : '<p class="empty-note">No items need review.</p>');
  html(elements.overdueList, overdue.length
    ? overdue.map(item => statusRow(item, state, "overdue")).join("")
    : '<p class="empty-note">No overdue payments recorded.</p>');
  html(elements.auditList, audit.length
    ? audit.slice(-3).reverse().map(item => `<div class="activity-row"><span class="activity-dot green-dot"></span><span><b>${helpers.escapeHtml(item.action || "Action recorded")}</b><small>${helpers.escapeHtml(item.actor || "system")} · ${helpers.escapeHtml(item.reason || "No reason recorded")}</small></span></div>`).join("")
    : '<p class="empty-note">No audit events recorded.</p>');
}

function renderMemberPanel(state) {
  const member = state?.member || helpers.getMembers(state).find(item => item.id === currentMemberId) || null;
  const label = member ? member.name : "Selected member";
  text(elements.memberStatementTitle, `${label} · statement`);
  const statement = Array.isArray(state?.statement) ? state.statement : [];
  html(elements.memberStatement, statement.length
    ? statement.map(row => `<div class="statement-row"><b>Month ${helpers.escapeHtml(row.month)}</b><span>Instalment ${helpers.escapeHtml(helpers.formatINR(row.instalment_paise))}</span><span>Dividend ${helpers.escapeHtml(helpers.formatINR(row.dividend_paise))}</span><span class="status ${row.status === "verified" ? "verified" : "needs-review"}">${helpers.escapeHtml(row.status || "pending")}</span></div>`).join("")
    : '<p class="empty-note">No statement rows are available.</p>');
  const bubbles = helpers.getBubbles(state);
  html(elements.memberBubbles, bubbles.length
    ? bubbles.map(bubble => `<div class="bubble-row"><b>${helpers.escapeHtml(bubble.type || "Private note")}</b><span>${helpers.escapeHtml(bubble.text || bubble.reason || "No detail recorded")}</span></div>`).join("")
    : '<p class="empty-note">No reminders for this view.</p>');
}

function renderLedger(state) {
  if (!state || !Array.isArray(state.members) || !Array.isArray(state.months) || !Array.isArray(state.ledger)) {
    throw new Error("The shared state response does not match the ledger contract.");
  }
  const months = helpers.getMonths(state);
  const members = helpers.getMembers(state);
  const byMemberMonth = new Map(state.ledger.map(entry => [`${entry?.member_id}:${entry?.month}`, entry]));
  const monthHeaders = months.map(month => `<th scope="col">${month}</th>`).join("");
  const rows = members.map(member => {
    const cells = months.map(month => {
      const entry = byMemberMonth.get(`${member.id}:${month}`);
      const status = Object.hasOwn(LEDGER_STATUS, entry?.status) ? entry.status : "pending";
      const details = LEDGER_STATUS[status];
      const utr = entry?.utr || "—";
      const amount = entry ? helpers.formatINR(entry.amount_paise) : "No payment recorded";
      const tooltip = `${member.name} · Month ${month} · ${details.label} · UTR: ${utr} · ${amount}`;
      const testId = `ledger-cell-${member.id}-month-${month}`;
      return `<td><span class="ledger-cell ${status}" role="img" tabindex="0" data-status="${status}" data-testid="${helpers.escapeHtml(testId)}" aria-label="${helpers.escapeHtml(tooltip)}" title="${helpers.escapeHtml(tooltip)}">${details.symbol}</span></td>`;
    }).join("");
    return `<tr><th scope="row">${helpers.escapeHtml(member.name)}</th>${cells}</tr>`;
  }).join("");
  const memberLabel = members.length === 1 ? "member" : "members";
  const monthLabel = months.length === 1 ? "month" : "months";
  html(elements.ledgerGrid, `<table class="ledger-table" aria-label="Payment status for ${members.length} ${memberLabel} across ${months.length} ${monthLabel}"><thead><tr><th scope="col">Member</th>${monthHeaders}</tr></thead><tbody>${rows}</tbody></table>`);
  elements.ledgerGrid?.setAttribute("aria-busy", "false");
  if (elements.ledgerGrid) {
    elements.ledgerGrid.dataset.memberCount = String(members.length);
    elements.ledgerGrid.dataset.monthCount = String(months.length);
  }
}

function renderStatus(source, error) {
  const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const labels = {
    live: `Live state · updated ${time}`,
    fixture: `Shared fixture · updated ${time}${error ? " · live API unavailable" : ""}`,
    stale: `Stale state · retrying · ${time}`
  };
  const ledgerLabels = {
    live: `Live · updated ${time}`,
    fixture: `Fixture · updated ${time}`,
    stale: "Stale · retrying"
  };
  text(elements.stateStatus, labels[source] || labels.stale);
  if (elements.stateStatus) elements.stateStatus.dataset.source = source;
  text(elements.ledgerSync, ledgerLabels[source] || ledgerLabels.stale);
  text(elements.pageEyebrow, `GROUP OVERVIEW · ${source === "live" ? "LIVE STATE" : source === "fixture" ? "SHARED FIXTURE" : "STALE STATE"}`);
  if (source === "live" && !error) {
    if (elements.ledgerError) elements.ledgerError.hidden = true;
    text(elements.ledgerError, "");
  } else {
    const message = error
      ? `${source === "stale" ? "Showing the last valid state" : "Using the labelled shared fixture"} because the live state request failed. ${error.message}`
      : "Using the labelled shared fixture because GET /state is not connected.";
    text(elements.ledgerError, message);
    if (elements.ledgerError) elements.ledgerError.hidden = false;
  }
}

function renderAll(state, source, error) {
  renderMemberSelect(state);
  const view = helpers.forRole(state, currentRole, currentMemberId);
  renderContext(view);
  renderKpis(view);
  if (currentRole === "foreman") renderForemanPanels(view);
  else renderMemberPanel(view);
  renderLedger(view);
  renderStatus(source, error);
  lastState = state;
  lastSource = source;
}

function showFailure(error) {
  renderStatus("stale", error);
  if (!lastState) {
    html(elements.ledgerGrid, '<p class="ledger-placeholder">Waiting for shared state…</p>');
    elements.ledgerGrid?.setAttribute("aria-busy", "false");
    html(elements.reviewList, '<p class="empty-note">State unavailable.</p>');
    html(elements.overdueList, '<p class="empty-note">State unavailable.</p>');
    html(elements.auditList, '<p class="empty-note">State unavailable.</p>');
    html(elements.memberStatement, '<p class="empty-note">State unavailable.</p>');
    html(elements.memberBubbles, '<p class="empty-note">State unavailable.</p>');
  }
}

async function fetchLiveState() {
  const response = await fetch(stateUrl(), { headers: { Accept: "application/json" }, cache: "no-store" });
  if (!response.ok) throw new Error(`GET /state returned ${response.status}`);
  const state = await response.json();
  if (!state || typeof state !== "object" || !Array.isArray(state.members)) throw new Error("State response is missing members");
  return state;
}

async function fetchFixtureState() {
  const response = await fetch("./fixture-state.json", { headers: { Accept: "application/json" }, cache: "no-store" });
  if (!response.ok) throw new Error(`Fixture returned ${response.status}`);
  const state = await response.json();
  if (!state || typeof state !== "object" || !Array.isArray(state.members)) throw new Error("Fixture is missing members");
  return state;
}

async function refresh() {
  if (requestPending || stopped || document.hidden) return;
  requestPending = true;
  stateRequestCount += 1;
  let liveError = null;
  try {
    let state = null;
    let source = "live";
    try {
      state = await fetchLiveState();
    } catch (error) {
      liveError = error;
      state = await fetchFixtureState();
      source = "fixture";
    }
    renderAll(state, source, liveError);
  } catch (error) {
    showFailure(liveError || error);
  } finally {
    requestPending = false;
  }
}

function applyRole(role) {
  if (!["foreman", "member"].includes(role) || role === currentRole) return;
  currentRole = role;
  document.querySelectorAll("[data-role]").forEach(button => {
    const isActive = button.dataset.role === currentRole;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
  document.querySelectorAll("[data-role-panel]").forEach(panel => {
    panel.hidden = panel.dataset.rolePanel !== currentRole;
  });
  if (elements.memberSelectWrap) elements.memberSelectWrap.hidden = currentRole !== "member";
  if (demoLoadButton) demoLoadButton.hidden = currentRole !== "foreman";
  if (lastState) renderAll(lastState, lastSource);
  refresh();
}

function stop() {
  stopped = true;
  if (timer !== null) window.clearInterval(timer);
  timer = null;
}

document.querySelectorAll("[data-role]").forEach(button => {
  button.addEventListener("click", () => applyRole(button.dataset.role));
});
if (demoLoadButton) demoLoadButton.addEventListener("click", loadDemo);
elements.memberSelect?.addEventListener("change", event => {
  currentMemberId = event.target.value;
  if (lastState) renderAll(lastState, lastSource);
  refresh();
});
async function loadDemo() {
  if (currentRole !== "foreman" || !demoLoadButton || demoLoadButton.disabled) return;
  demoLoadButton.disabled = true;
  text(elements.stateStatus, "Loading synthetic four-month demo…");
  try {
    const response = await fetch(apiBase() + "/demo/load", {
      method: "POST",
      headers: {"Accept": "application/json", "Content-Type": "application/json"},
      body: JSON.stringify({actor: "foreman"})
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error && payload.error.message ? payload.error.message : "Demo load failed (" + response.status + ").");
    }
    if (!payload || payload.loaded !== true) throw new Error("The server did not confirm the demo load.");
    await refresh();
    text(elements.stateStatus, "Demo loaded. Four-month synthetic ledger is ready.");
  } catch (error) {
    text(elements.stateStatus, error.message || "Could not load the demo data.");
  } finally {
    demoLoadButton.disabled = false;
  }
}

async function reviewPayment(itemId, decision) {
  if (currentRole !== "foreman" || !itemId) return;
  const reason = window.prompt(decision === "approve" ? "Reason for manual approval:" : "Reason for rejection:");
  if (!reason || !reason.trim()) return;
  text(elements.stateStatus, "Recording foreman decision…");
  try {
    const response = await fetch(apiBase() + "/review", {
      method: "POST", headers: {"Accept":"application/json","Content-Type":"application/json"},
      body: JSON.stringify({actor:"foreman",item_id:itemId,decision,reason:reason.trim()})
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error?.message || "Review request failed.");
    text(elements.stateStatus, decision === "approve" ? "Manual approval recorded. This payment is not independently verified." : "Payment rejected and recorded.");
    await refresh();
  } catch (error) {
    text(elements.stateStatus, error.message || "Could not record review decision.");
  }
}

elements.reviewList?.addEventListener("click", event => {
  const button = event.target.closest("[data-review-decision]");
  if (!button || button.disabled) return;
  button.disabled = true;
  reviewPayment(button.dataset.reviewId, button.dataset.reviewDecision)
    .finally(() => { button.disabled = false; });
});

async function sendRemindersNow() {
  if (currentRole !== "foreman" || !sendRemindersButton || sendRemindersButton.disabled) return;
  sendRemindersButton.disabled = true;
  text(elements.stateStatus, "Sending private reminders…");
  try {
    const response = await fetch(apiBase() + "/reminders/send", {
      method: "POST", headers: {"Accept":"application/json","Content-Type":"application/json"},
      body: JSON.stringify({actor:"foreman"})
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error?.message || "Reminder request failed.");
    text(elements.stateStatus, "Reminders recorded for " + payload.sent + " member(s).");
    await refresh();
  } catch (error) {
    text(elements.stateStatus, error.message || "Could not send reminders.");
  } finally {
    sendRemindersButton.disabled = false;
  }
}

sendRemindersButton?.addEventListener("click", sendRemindersNow);
document.querySelector("#ledger-refresh")?.addEventListener("click", refresh);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
window.addEventListener("pagehide", stop);

refresh();
timer = window.setInterval(refresh, POLL_MS);

window.chitmirrorDashboard = {
  stop,
  refresh,
  applyRole,
  get pollMs() { return POLL_MS; },
  get role() { return currentRole; },
  get requestCount() { return stateRequestCount; },
  get source() { return lastSource; }
};
