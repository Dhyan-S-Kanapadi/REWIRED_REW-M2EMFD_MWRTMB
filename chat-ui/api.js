(function () {
  const apiBase = String(window.CHITMIRROR_API_BASE || "").replace(/\/+$/, "");

  async function request(path, options) {
    const response = await fetch(`${apiBase}${path}`, options);
    let payload;

    try {
      payload = await response.json();
    } catch {
      throw new Error(`The API returned an unreadable response (${response.status}).`);
    }

    if (!response.ok) {
      const message = payload && payload.error && payload.error.message;
      throw new Error(message || `The API request failed (${response.status}).`);
    }

    return payload;
  }

  function getState(sender) {
    const query = new URLSearchParams();
    query.set("role", sender === "foreman" ? "foreman" : "member");
    if (sender !== "foreman") {
      query.set("member_id", sender);
    }
    return request(`/state?${query.toString()}`, { method: "GET" });
  }

  function sendMessage(sender, text, image) {
    const body = new FormData();
    body.append("sender", sender);
    body.append("text", text);
    if (image) {
      body.append("image", image);
    }
    return request("/message", { method: "POST", body });
  }

  window.ChitMirrorApi = Object.freeze({ getState, sendMessage });
})();
