(function () {
  const apiBase = String(window.CHITMIRROR_API_BASE || "").replace(/\/+$/, "");

  async function request(path, options) {
    let response;
    try {
      response = await fetch(apiBase + path, options);
    } catch {
      throw new Error("The API is unavailable. Check the connection and try again.");
    }

    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new Error("The API returned an unreadable response (" + response.status + ").");
    }

    if (!response.ok) {
      const message = payload && payload.error && payload.error.message;
      throw new Error(message || "The API request failed (" + response.status + ").");
    }
    return payload;
  }

  function getHealth() {
    return request("/health", {headers: {Accept: "application/json"}});
  }

  function getState(role, memberId) {
    const query = new URLSearchParams({role: role});
    if (memberId) query.set("member_id", memberId);
    return request("/state?" + query.toString(), {
      headers: {Accept: "application/json"},
      cache: "no-store",
    });
  }

  function sendMessage(sender, text, image) {
    const body = new FormData();
    body.append("sender", sender);
    body.append("text", text);
    if (image) body.append("image", image);
    return request("/message", {method: "POST", headers: {Accept: "application/json"}, body: body})
      .then(validateMessageResponse);
  }

  function exactKeys(value, expected) {
    const keys = Object.keys(value).sort();
    return keys.length === expected.length && keys.every(function(key, index) { return key === expected.slice().sort()[index]; });
  }

  function validBubble(bubble) {
    if (!bubble || typeof bubble !== "object" || Array.isArray(bubble)) return false;
    if (bubble.type === "text") return exactKeys(bubble, ["type", "text"]) && typeof bubble.text === "string";
    if (bubble.type === "reminder") return exactKeys(bubble, ["type", "text"]) && typeof bubble.text === "string" && Boolean(bubble.text.trim());
    if (bubble.type === "review_request") {
      return exactKeys(bubble, ["type", "item_id", "reason"])
        && typeof bubble.item_id === "string" && Boolean(bubble.item_id.trim())
        && typeof bubble.reason === "string" && Boolean(bubble.reason.trim());
    }
    if (bubble.type === "result_card") {
      return exactKeys(bubble, ["type", "status", "amount_paise", "utr", "reason"])
        && ["verified", "duplicate", "wrong_amount", "needs_review"].includes(bubble.status)
        && (bubble.amount_paise === null || (Number.isSafeInteger(bubble.amount_paise) && bubble.amount_paise >= 0))
        && (bubble.utr === null || (typeof bubble.utr === "string" && /^[0-9]{12}$/.test(bubble.utr)))
        && typeof bubble.reason === "string";
    }
    return false;
  }

  function validateMessageResponse(payload) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)
      || !exactKeys(payload, ["bubbles"]) || !Array.isArray(payload.bubbles)
      || !payload.bubbles.every(validBubble)) {
      throw new Error("The server returned a chat response that does not match the shared API contract.");
    }
    return payload;
  }

  function submitReview(review) {
    return request("/review", {
      method: "POST",
      headers: {Accept: "application/json", "Content-Type": "application/json"},
      body: JSON.stringify(review),
    });
  }

  window.ChitMirrorApi = Object.freeze({getHealth, getState, sendMessage, submitReview});
})();
