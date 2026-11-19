const connection = document.querySelector("#connection");
const senderPicker = document.querySelector("#sender");
const reviewQueue = document.querySelector("#review-queue");
const queueStatus = document.querySelector("#queue-status");
const reminderSection = document.querySelector("#reminder-section");
const reminderStatus = document.querySelector("#reminder-status");
const reminderFeed = document.querySelector("#reminder-feed");
const reminderCount = document.querySelector("#reminder-count");
const messageList = document.querySelector("#message-list");
const messageInput = document.querySelector("#message-input");
const hintsOutput = document.querySelector("#command-hints");
const notice = document.querySelector("#notice");
const composer = document.querySelector("#composer");
const sendButton = document.querySelector("#send-message");
const sendStatus = document.querySelector("#send-status");
const imageInput = document.querySelector("#payment-image");
const imagePreview = document.querySelector("#image-preview");
const previewImage = document.querySelector("#preview-image");
const imageName = document.querySelector("#image-name");
const removeImageButton = document.querySelector("#remove-screenshot");
let selectedImage = null;
let members = [];
function setSelectedImage(file) {
  if (!file) return;
  if (!["image/png", "image/jpeg"].includes(file.type)) { showNotice("Choose a PNG or JPG screenshot.", true); return; }
  if (file.size > 10 * 1024 * 1024) { showNotice("Screenshot must be 10 MiB or smaller.", true); return; }
  selectedImage = file;
  previewImage.src = URL.createObjectURL(file);
  imageName.textContent = file.name;
  imagePreview.hidden = false;
  removeImageButton.hidden = false;
  showNotice("", false);
}
function clearSelectedImage() {
  if (previewImage.src.startsWith("blob:")) URL.revokeObjectURL(previewImage.src);
  selectedImage = null; imageInput.value = ""; imagePreview.hidden = true;
  removeImageButton.hidden = true; imageName.textContent = ""; previewImage.removeAttribute("src");
}
document.querySelector("#attach-screenshot").addEventListener("click", () => imageInput.click());
imageInput.addEventListener("change", () => setSelectedImage(imageInput.files[0]));
removeImageButton.addEventListener("click", clearSelectedImage);
messageInput.addEventListener("paste", event => {
  const item = Array.from(event.clipboardData?.items || []).find(entry => entry.type.startsWith("image/"));
  if (item) { const file = item.getAsFile(); if (file) setSelectedImage(file); }
});
composer.addEventListener("dragover", event => { event.preventDefault(); });
composer.addEventListener("drop", event => {
  event.preventDefault();
  const file = Array.from(event.dataTransfer?.files || []).find(entry => entry.type.startsWith("image/"));
  if (file) setSelectedImage(file);
});

function showNotice(message, isError) {
  notice.textContent = message || "";
  notice.classList.toggle("error", Boolean(isError));
}

async function checkConnection() {
  try {
    const payload = await window.ChitMirrorApi.getHealth();
    if (!payload || payload.status !== "ok") throw new Error("Health check failed");
    connection.textContent = "Backend connected";
    connection.classList.add("connected");
  } catch {
    connection.textContent = "Backend unavailable — check the server and API URL.";
    connection.classList.add("failed");
  }
}

function addTimestamp(article, date) {
  const timestamp = document.createElement("time");
  timestamp.className = "bubble-time";
  timestamp.dateTime = date.toISOString();
  timestamp.textContent = new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
  article.append(timestamp);
}

function addTextBubble(label, text, kind, dateOrTestId) {
  const article = document.createElement("article");
  article.className = "bubble " + (kind || "server-bubble");
  article.dataset.message = "true";
  if (typeof dateOrTestId === "string") article.dataset.testid = dateOrTestId;
  const title = document.createElement("span");
  title.className = "bubble-label";
  title.textContent = label;
  const body = document.createElement("p");
  body.textContent = text;
  article.append(title, body);
  addTimestamp(article, dateOrTestId instanceof Date ? dateOrTestId : new Date());
  messageList.append(article);
  messageList.scrollTop = messageList.scrollHeight;
  return article;
}

function addReminderBubble(text, target) {
  const article = document.createElement("article");
  article.className = "bubble reminder-bubble";
  article.dataset.testid = "reminder-bubble";
  article.dataset.memberScoped = "true";
  const title = document.createElement("span");
  title.className = "bubble-label";
  title.textContent = "Private reminder";
  const stamp = document.createElement("time");
  const now = new Date();
  stamp.dateTime = now.toISOString();
  stamp.textContent = now.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
  const body = document.createElement("p");
  body.textContent = text || "";
  article.append(title, stamp, body);
  (target || messageList).append(article);
  return article;
}

function clearConversation() {
  Array.from(messageList.children).forEach(function(child, index) {
    if (index > 0) child.remove();
  });
  reminderFeed.replaceChildren();
  reminderCount.textContent = "";
  showNotice("", false);
}

function renderResultCard(bubble) {
  const article = document.createElement("article");
  article.className = "bubble result-bubble";
  article.dataset.message = "true";
  const heading = document.createElement("span");
  heading.className = "bubble-label";
  heading.textContent = "Payment result";
  const details = document.createElement("dl");
  details.className = "result-details";
  const amount = bubble.amount_paise == null
    ? "Not provided"
    : "₹" + (Number(bubble.amount_paise) / 100).toLocaleString("en-IN", {minimumFractionDigits: 2});
  [["Status", bubble.status], ["Amount", amount], ["UTR", bubble.utr || "Not available"], ["Reason", bubble.reason]].forEach(function (row) {
    if (row[1] == null || row[1] === "") return;
    const term = document.createElement("dt");
    term.textContent = row[0];
    const value = document.createElement("dd");
    value.textContent = String(row[1]);
    details.append(term, value);
  });
  article.append(heading, details);
  addTimestamp(article, new Date());
  messageList.append(article);
  messageList.scrollTop = messageList.scrollHeight;
}

function setSenderOptions() {
  const selected = senderPicker.value || "foreman";
  senderPicker.replaceChildren();
  const foreman = document.createElement("option");
  foreman.value = "foreman";
  foreman.textContent = "Foreman";
  senderPicker.append(foreman);
  members.forEach(function(member) {
    const option = document.createElement("option");
    option.value = member.id;
    option.textContent = member.name;
    senderPicker.append(option);
  });
  senderPicker.value = selected;
  if (!senderPicker.value) senderPicker.value = "foreman";
  reviewQueue.hidden = senderPicker.value !== "foreman";
  reminderSection.hidden = senderPicker.value === "foreman";
}

function renderReviewCard(item) {
  if (!item || typeof item.item_id !== "string" || !item.item_id.trim()) return;
  const existing = reviewQueue.querySelector('[data-item-id="' + CSS.escape(item.item_id) + '"]');
  if (existing) return;
  const member = members.find(function(candidate) { return candidate.id === item.member_id; });
  const article = document.createElement("article");
  article.className = "bubble review-bubble";
  article.dataset.itemId = item.item_id;

  const header = document.createElement("div");
  header.className = "review-card-heading";
  const title = document.createElement("span");
  title.className = "bubble-label";
  title.textContent = "Needs review";
  const badge = document.createElement("span");
  badge.className = "review-badge";
  badge.textContent = "Foreman action";
  header.append(title, badge);

  const details = document.createElement("p");
  details.className = "review-details";
  const detailParts = [];
  if (member) detailParts.push(member.name);
  if (Number.isInteger(Number(item.month))) detailParts.push("Month " + Number(item.month));
  details.textContent = detailParts.join(" · ");

  const reason = document.createElement("p");
  reason.className = "review-reason";
  reason.textContent = item.reason || "A payment was flagged for manual review.";

  const label = document.createElement("label");
  const inputId = "review-reason-" + item.item_id;
  label.htmlFor = inputId;
  label.textContent = "Reason for your decision";
  const textarea = document.createElement("textarea");
  textarea.id = inputId;
  textarea.dataset.testid = "review-reason-" + item.item_id;
  textarea.rows = 2;
  textarea.required = true;
  textarea.placeholder = "Explain the evidence you checked";
  textarea.setAttribute("aria-describedby", "review-error-" + item.item_id);

  const error = document.createElement("p");
  error.className = "field-error";
  error.id = "review-error-" + item.item_id;
  error.setAttribute("aria-live", "polite");

  const actions = document.createElement("div");
  actions.className = "review-actions";
  ["approve", "reject"].forEach(function(decision) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = decision === "approve" ? "approve-button" : "reject-button";
    button.dataset.testid = "review-" + decision + "-" + item.item_id;
    button.textContent = decision === "approve" ? "Approve" : "Reject";
    button.addEventListener("click", function() {
      submitReview(item.item_id, decision, textarea, error, article, actions);
    });
    actions.append(button);
  });

  article.append(header);
  if (details.textContent) article.append(details);
  article.append(reason, label, textarea, error, actions);
  reviewQueue.append(article);
}

async function submitReview(itemId, decision, textarea, error, article, actions) {
  if (senderPicker.value !== "foreman") {
    error.textContent = "Only the foreman can submit a review decision.";
    return;
  }
  const reason = textarea.value.trim();
  if (!reason) {
    error.textContent = "Enter a reason before approving or rejecting.";
    textarea.setAttribute("aria-invalid", "true");
    textarea.focus();
    return;
  }
  textarea.removeAttribute("aria-invalid");
  error.textContent = "";
  Array.from(actions.querySelectorAll("button")).forEach(function(button) { button.disabled = true; });
  try {
    const payload = await window.ChitMirrorApi.submitReview({item_id: itemId, decision: decision, reason: reason, actor: "foreman"});
    if (payload.item_id !== itemId || payload.decision !== decision) throw new Error("The server returned an unexpected review result.");
    article.remove();
    queueStatus.textContent = decision === "approve" ? "Review approved and recorded." : "Review rejected and recorded.";
    showNotice("Decision recorded by the server.", false);
    await loadReviewQueue();
  } catch (requestError) {
    Array.from(actions.querySelectorAll("button")).forEach(function(button) { button.disabled = false; });
    error.textContent = requestError.message || "Could not record this decision. Try again.";
  }
}

function renderBubble(bubble) {
  if (!bubble || typeof bubble !== "object") return;
  if (bubble.type === "reminder") {
    addReminderBubble(bubble.text);
    return;
  }
  if (bubble.type === "text") {
    const text = bubble.text || "";
    if (/^Dues for /.test(text)) {
      addTextBubble("Dues", text, "dues-bubble", "dues-result");
    } else if (/^Statement for /.test(text)) {
      addTextBubble("Statement", text, "statement-bubble", "statement-result");
    } else if (/^(No private reminders|Private reminders for)/.test(text)) {
      addTextBubble("Private reminders", text, "reminder-bubble", "reminder-header");
    } else {
      addTextBubble("ChitMirror", text, "server-bubble");
    }
    return;
  }
  if (bubble.type === "result_card") {
    renderResultCard(bubble);
    return;
  }
  if (bubble.type === "review_request") {
    renderReviewCard(bubble);
    addTextBubble("ChitMirror", "A payment was flagged for foreman review.", "server-bubble");
  }
}

async function loadReviewQueue() {
  queueStatus.textContent = "Loading review items…";
  try {
    const state = await window.ChitMirrorApi.getState("foreman");
    if (!state || !Array.isArray(state.members) || !Array.isArray(state.flags)) throw new Error("Shared state response is incomplete.");
    members = state.members;
    setSenderOptions();
    if (senderPicker.value === "foreman") {
      reviewQueue.replaceChildren();
      state.flags.forEach(renderReviewCard);
      queueStatus.textContent = state.flags.length ? state.flags.length + " item" + (state.flags.length === 1 ? "" : "s") + " need foreman review." : "No open review items.";
    } else {
      reviewQueue.replaceChildren();
      queueStatus.textContent = "Review actions are available to the foreman.";
    }
    return state;
  } catch (error) {
    queueStatus.textContent = "Review queue unavailable. " + (error.message || "Check the shared state endpoint.");
    return null;
  }
}

async function loadMemberContext() {
  const memberId = senderPicker.value;
  if (memberId === "foreman") {
    reminderSection.hidden = true;
    reminderFeed.replaceChildren();
    reminderStatus.textContent = "";
    reminderCount.textContent = "";
    return;
  }
  reminderSection.hidden = false;
  reminderFeed.replaceChildren();
  reminderCount.textContent = "";
  reminderStatus.textContent = "Loading private reminders…";
  try {
    const state = await window.ChitMirrorApi.getState("member", memberId);
    if (senderPicker.value !== memberId) return;
    if (!state || !Array.isArray(state.private_bubbles)) throw new Error("Shared state response is incomplete.");
    const bubbles = state.private_bubbles.filter(function(bubble) { return bubble && bubble.type === "reminder"; });
    bubbles.forEach(function(bubble) { addReminderBubble(bubble.text, reminderFeed); });
    reminderCount.textContent = bubbles.length ? bubbles.length + (bubbles.length === 1 ? " reminder" : " reminders") : "";
    reminderStatus.textContent = bubbles.length ? "" : "No private reminders for this sender.";
  } catch (error) {
    if (senderPicker.value !== memberId) return;
    reminderStatus.textContent = "Private reminders unavailable. " + (error.message || "Check the shared state endpoint.");
  }
}

function parseCommandHints(text) {
  const hints = [];
  const month = /\bmonth\s+(\d+)\b/i.exec(text);
  const name = /\bname\s*[:=]\s*([^,;\n]+)/i.exec(text);
  const discount = /\bdiscount\s*(?:₹|rs\.?\s*|inr\s*)?([\d,]+(?:\.\d{1,2})?)/i.exec(text);
  const memberCommand = /\b(dues?|statement|reminders?)\b/i.exec(text);
  if (memberCommand) hints.push("Selected-sender " + memberCommand[1].toLowerCase());
  if (month) hints.push("Month " + Number(month[1]));
  if (name && name[1].trim()) hints.push("Name " + name[1].trim());
  if (discount) hints.push("Discount ₹" + discount[1].replace(/,/g, ""));
  return hints;
}

function updateCommandHints() {
  const hints = parseCommandHints(messageInput.value);
  if (!hints.length) {
    hintsOutput.hidden = true;
    hintsOutput.textContent = "";
    return;
  }
  hintsOutput.hidden = false;
  hintsOutput.textContent = "Hints only — server validates: " + hints.join(" · ");
}

senderPicker.addEventListener("change", function() {
  clearConversation();
  setSenderOptions();
  updateCommandHints();
  loadMemberContext();
});
messageInput.addEventListener("input", updateCommandHints);
document.querySelector("#refresh-queue").addEventListener("click", loadReviewQueue);

composer.addEventListener("submit", async function(event) {
  event.preventDefault();
  if (sendButton.disabled) return;
  const text = messageInput.value.trim();
  if (!text && !selectedImage) {
    messageInput.focus();
    return;
  }
  const senderId = senderPicker.value;
  const senderLabel = senderPicker.selectedOptions[0] ? senderPicker.selectedOptions[0].textContent : "Foreman";
  const sentAt = new Date();
  const outgoingKind = senderId === "foreman" ? "outgoing-bubble foreman-bubble" : "outgoing-bubble member-bubble";
  sendButton.disabled = true;
  sendButton.setAttribute("aria-busy", "true");
  sendStatus.hidden = false;
  sendStatus.textContent = "Sending message…";
  showNotice("", false);
  try {
    const payload = await window.ChitMirrorApi.sendMessage(senderId, text, selectedImage);
    if (senderPicker.value !== senderId) return;
    addTextBubble(senderLabel, text, outgoingKind, sentAt);
    if (!payload.bubbles.length) {
      addTextBubble("ChitMirror", "No details are available for this command.", "server-bubble", "empty-result");
      showNotice("No details are available for this command.", false);
    }
    payload.bubbles.forEach(renderBubble);
    messageInput.value = "";
    clearSelectedImage();
    updateCommandHints();
    messageList.scrollTop = messageList.scrollHeight;
  } catch (error) {
    showNotice(error.message || "Message could not be sent. Try again.", true);
  } finally {
    sendButton.disabled = false;
    sendButton.removeAttribute("aria-busy");
    sendStatus.textContent = "";
    sendStatus.hidden = true;
  }
});

messageInput.addEventListener("keydown", function(event) {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    composer.requestSubmit();
  }
});

Array.from(messageList.querySelectorAll(".bubble")).forEach(function(article) {
  addTimestamp(article, new Date());
});

checkConnection();
loadReviewQueue().then(loadMemberContext);
