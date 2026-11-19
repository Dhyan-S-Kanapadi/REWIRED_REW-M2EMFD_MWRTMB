(function () {
  const senderSelect = document.querySelector("#sender");
  const conversation = document.querySelector("#conversation");
  const emptyState = document.querySelector("#empty-state");
  const loadingState = document.querySelector("#loading-state");
  const messageForm = document.querySelector("#message-form");
  const messageText = document.querySelector("#message-text");
  const imageInput = document.querySelector("#image-input");
  const imagePreview = document.querySelector("#image-preview");
  const previewImage = document.querySelector("#preview-image");
  const sendButton = document.querySelector("#send-button");
  const sendStatus = document.querySelector("#send-status");
  const connection = document.querySelector("#connection");
  const errorBanner = document.querySelector("#error-banner");
  const errorMessage = document.querySelector("#error-message");
  const retryState = document.querySelector("#retry-state");
  const objectUrls = new Set();
  let selectedImage = null;
  let previewUrl = null;
  let sending = false;
  let loading = false;

  function selectedSenderName() {
    const option = senderSelect.selectedOptions[0];
    return option ? option.textContent : "Foreman";
  }

  function updateEmptyState() {
    emptyState.hidden = conversation.querySelectorAll(".message").length > 0;
  }

  function updateSendButton() {
    sendButton.disabled = sending || (!messageText.value.trim() && !selectedImage);
  }

  function showError(message, canRetryState) {
    errorMessage.textContent = message;
    errorBanner.hidden = false;
    retryState.hidden = !canRetryState;
  }

  function clearError() {
    errorBanner.hidden = true;
    errorMessage.textContent = "";
    retryState.hidden = true;
  }

  function clearPreview(revokeUrl) {
    if (revokeUrl && previewUrl) {
      URL.revokeObjectURL(previewUrl);
      objectUrls.delete(previewUrl);
    }
    previewUrl = null;
    selectedImage = null;
    previewImage.removeAttribute("src");
    imagePreview.hidden = true;
    imageInput.value = "";
    updateSendButton();
  }

  function setLoading(value) {
    loading = value;
    loadingState.hidden = !loading;
    senderSelect.disabled = loading || sending;
    connection.textContent = loading ? "Loading conversation…" : connection.textContent;
  }

  function addTimestamp(container, date) {
    const timestamp = document.createElement("time");
    timestamp.dateTime = date.toISOString();
    timestamp.textContent = new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit"
    }).format(date);
    container.append(timestamp);
  }

  function appendMessage(kind, contents, date) {
    const message = document.createElement("article");
    message.className = `message message-${kind}`;
    const heading = document.createElement("div");
    heading.className = "message-heading";
    const sender = document.createElement("span");
    sender.className = "message-sender";
    sender.textContent = kind === "user" ? selectedSenderName() : "ChitMirror";
    heading.append(sender);
    addTimestamp(heading, date || new Date());
    message.append(heading, contents);
    conversation.append(message);
    updateEmptyState();
    conversation.scrollTop = conversation.scrollHeight;
  }

  function renderTextBubble(bubble) {
    const text = document.createElement("p");
    text.className = "bubble-text";
    text.textContent = bubble.text;
    return text;
  }

  function renderResultCard(bubble) {
    const card = document.createElement("section");
    card.className = `structured-card result-card status-${bubble.status}`;
    const labels = {
      verified: "Verified",
      duplicate: "Duplicate",
      wrong_amount: "Wrong amount",
      needs_review: "Needs review"
    };
    const title = document.createElement("h2");
    title.className = "card-title";
    title.textContent = "Payment result";
    const status = document.createElement("span");
    status.className = "status-pill";
    status.textContent = labels[bubble.status];
    const statusRow = document.createElement("div");
    statusRow.className = "result-status";
    statusRow.append(title, status);
    const details = document.createElement("dl");
    details.className = "result-details";
    const amount = typeof bubble.amount_paise === "number"
      ? new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(bubble.amount_paise / 100)
      : "Not provided";
    const rows = [
      ["Amount", amount],
      ["UTR", bubble.utr || "Not available"],
      ["Reason", bubble.reason]
    ];
    rows.forEach(function (row) {
      const term = document.createElement("dt");
      term.textContent = row[0];
      const value = document.createElement("dd");
      value.textContent = row[1];
      details.append(term, value);
    });
    const disclaimer = document.createElement("p");
    disclaimer.className = "card-disclaimer";
    disclaimer.textContent = "Status reported by the backend; this chat does not independently verify bank evidence.";
    card.append(statusRow, details, disclaimer);
    return card;
  }

  function renderReviewCard(bubble) {
    const card = document.createElement("section");
    card.className = "structured-card review-card";
    const title = document.createElement("h2");
    title.className = "card-title";
    title.textContent = "Review requested";
    const reason = document.createElement("p");
    reason.textContent = bubble.reason;
    const reference = document.createElement("p");
    reference.className = "card-reference";
    reference.textContent = `Reference: ${bubble.item_id}`;
    card.append(title, reason, reference);
    return card;
  }

  function renderReminderCard(bubble) {
    const card = document.createElement("section");
    card.className = "structured-card reminder-card";
    const title = document.createElement("h2");
    title.className = "card-title";
    title.textContent = "Payment reminder";
    const text = document.createElement("p");
    text.textContent = bubble.text;
    card.append(title, text);
    return card;
  }

  function renderBubble(bubble) {
    switch (bubble.type) {
      case "text":
        return renderTextBubble(bubble);
      case "result_card":
        return renderResultCard(bubble);
      case "review_request":
        return renderReviewCard(bubble);
      case "reminder":
        return renderReminderCard(bubble);
      default:
        throw new Error("The API returned an unsupported message type.");
    }
  }

  function populateMembers(state) {
    if (!Array.isArray(state.members)) {
      throw new Error("The API returned an invalid member list.");
    }
    const currentValue = senderSelect.value;
    senderSelect.replaceChildren(new Option("Foreman", "foreman"));
    state.members.forEach(function (member) {
      const option = new Option(`${member.name} (${member.id})`, member.id);
      senderSelect.add(option);
    });
    senderSelect.value = currentValue;
    if (senderSelect.value !== currentValue) {
      senderSelect.value = "foreman";
    }
  }

  async function loadState() {
    clearError();
    setLoading(true);
    connection.textContent = "Loading conversation…";
    try {
      const state = await window.ChitMirrorApi.getState(senderSelect.value);
      if (senderSelect.value === "foreman") {
        populateMembers(state);
      }
      if (!Array.isArray(state.private_bubbles)) {
        throw new Error("The API returned an invalid conversation state.");
      }
      connection.textContent = "Connected to the group API";
    } catch (error) {
      connection.textContent = "API unavailable";
      showError(error.message, true);
    } finally {
      setLoading(false);
    }
  }

  senderSelect.addEventListener("change", function () {
    conversation.querySelectorAll(".message").forEach(function (message) {
      message.remove();
    });
    updateEmptyState();
    loadState();
  });

  messageText.addEventListener("input", updateSendButton);

  imageInput.addEventListener("change", function () {
    const file = imageInput.files && imageInput.files[0];
    if (!file) {
      return;
    }
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      clearPreview(true);
      showError("Choose a PNG, JPEG, or WebP screenshot.", false);
      return;
    }
    clearError();
    clearPreview(true);
    selectedImage = file;
    previewUrl = URL.createObjectURL(file);
    objectUrls.add(previewUrl);
    previewImage.src = previewUrl;
    imagePreview.hidden = false;
    updateSendButton();
  });

  document.querySelector("#attach-button").addEventListener("click", function () {
    imageInput.click();
  });

  document.querySelector("#remove-image").addEventListener("click", function () {
    clearPreview(true);
  });

  retryState.addEventListener("click", loadState);

  messageForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    const text = messageText.value;
    if (sending || (!text.trim() && !selectedImage)) {
      return;
    }

    const sentImage = selectedImage;
    const sentPreviewUrl = previewUrl;
    sending = true;
    senderSelect.disabled = true;
    messageText.disabled = true;
    imageInput.disabled = true;
    sendStatus.textContent = "Sending…";
    sendButton.querySelector("span").textContent = "Sending";
    updateSendButton();
    clearError();

    try {
      const response = await window.ChitMirrorApi.sendMessage(senderSelect.value, text, sentImage);
      if (!response || !Array.isArray(response.bubbles)) {
        throw new Error("The API returned an invalid message response.");
      }
      const userContents = document.createElement("div");
      userContents.className = "user-message-content";
      if (text.trim()) {
        const paragraph = document.createElement("p");
        paragraph.className = "bubble-text";
        paragraph.textContent = text;
        userContents.append(paragraph);
      }
      if (sentImage && sentPreviewUrl) {
        const image = document.createElement("img");
        image.className = "sent-image";
        image.src = sentPreviewUrl;
        image.alt = "Screenshot shared in this conversation";
        userContents.append(image);
      }
      appendMessage("user", userContents, new Date());
      response.bubbles.forEach(function (bubble) {
        appendMessage("backend", renderBubble(bubble), new Date());
      });
      messageText.value = "";
      if (sentPreviewUrl) {
        previewUrl = null;
        selectedImage = null;
        previewImage.removeAttribute("src");
        imagePreview.hidden = true;
        imageInput.value = "";
      }
      updateSendButton();
    } catch (error) {
      showError(error.message, false);
    } finally {
      sending = false;
      senderSelect.disabled = loading;
      messageText.disabled = false;
      imageInput.disabled = false;
      sendStatus.textContent = "";
      sendButton.querySelector("span").textContent = "Send";
      updateSendButton();
    }
  });

  window.addEventListener("beforeunload", function () {
    objectUrls.forEach(function (url) {
      URL.revokeObjectURL(url);
    });
  });

  updateSendButton();
  loadState();
})();
