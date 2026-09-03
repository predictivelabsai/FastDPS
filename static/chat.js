(() => {
  const q = (selector) => document.querySelector(selector);

  window.toggleNav = () => document.body.classList.toggle("nav-open");
  window.toggleArtifact = () => document.body.classList.toggle("artifact-open");

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  }

  function addMessage(role, content) {
    const messages = q("#messages");
    if (!messages) return;
    const welcome = messages.querySelector(".chat-welcome");
    if (welcome) welcome.remove();
    const message = node("div", `message ${role}`);
    message.append(node("span", "message-author", role === "user" ? "You" : "FastDPS"));
    message.append(node("p", "message-copy", content));
    messages.append(message);
    messages.scrollTop = messages.scrollHeight;
  }

  function renderArtifact(data) {
    const pane = q("#artifact-pane");
    if (!pane) return;
    pane.replaceChildren();
    const close = node("button", "artifact-close", "×");
    close.type = "button";
    close.addEventListener("click", window.toggleArtifact);
    pane.append(close, node("p", "eyebrow", data.kind === "confirmation" ? "CONFIRMATION REQUIRED" : "RESULTS"), node("h2", "", data.title || "Result"));
    if (data.summary) pane.append(node("p", "artifact-summary", data.summary));

    if (Array.isArray(data.items)) {
      const list = node("div", "artifact-list");
      data.items.forEach((item) => {
        const card = node("div", "artifact-card");
        card.append(node("strong", "", item.title || item.supplier_name || item.action || item.name || item.reference || "Record"));
        card.append(node("span", "muted", item.reference || item.dps_reference || item.entity_type || item.status || ""));
        if (item.status) card.append(node("span", `status ${String(item.status).replaceAll("_", "-")}`, String(item.status).replaceAll("_", " ")));
        list.append(card);
      });
      pane.append(list);
    }

    if (data.kind === "confirmation" && data.action_id) {
      const note = node("p", "muted", "Your current permissions will be checked again when you confirm.");
      const button = node("button", "button full", "Confirm action");
      button.type = "button";
      button.addEventListener("click", async () => {
        button.disabled = true;
        button.textContent = "Confirming…";
        const response = await fetch(data.confirm_url, {method: "POST", headers: {"X-CSRF-Token": window.FASTDPS_CSRF || ""}});
        const result = await response.json();
        if (!response.ok) {
          button.textContent = result.error || "Could not confirm";
          button.disabled = false;
          return;
        }
        button.textContent = "Action completed";
        button.classList.add("confirmed");
        addMessage("assistant", `Completed ${String(result.action).replaceAll(".", " ")}.`);
      });
      pane.append(note, button);
    }
    document.body.classList.add("artifact-open");
    const toggle = q("#artifact-toggle");
    if (toggle) toggle.classList.add("has-results");
  }

  function parseEvent(block) {
    let event = "message";
    const data = [];
    block.split("\n").forEach((line) => {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trim());
    });
    if (!data.length) return;
    const payload = JSON.parse(data.join("\n"));
    if (event === "session") {
      const sid = q("#chat-sid");
      if (sid) sid.value = payload.id;
    } else if (event === "artifact") {
      renderArtifact(payload);
    } else if (event === "message") {
      addMessage("assistant", payload.text || "");
    } else if (event === "error") {
      addMessage("assistant", payload.message || "Something went wrong.");
    }
  }

  const form = q("#chat-form");
  if (form) {
    const input = q("#chat-input");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = input.value.trim();
      if (!message) return;
      addMessage("user", message);
      input.value = "";
      const button = form.querySelector("button");
      button.disabled = true;
      try {
        const payload = new FormData(form);
        payload.set("message", message);
        const response = await fetch("/api/chat/stream", {method: "POST", headers: {"X-CSRF-Token": window.FASTDPS_CSRF || ""}, body: payload});
        if (!response.ok || !response.body) throw new Error("The assistant could not start.");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const {value, done} = await reader.read();
          buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() || "";
          blocks.filter(Boolean).forEach(parseEvent);
          if (done) break;
        }
        if (buffer.trim()) parseEvent(buffer);
      } catch (error) {
        addMessage("assistant", error.message || "Something went wrong.");
      } finally {
        button.disabled = false;
        input.focus();
      }
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });
  }

  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = q("#chat-input");
      if (!input || !form) return;
      input.value = button.dataset.prompt;
      form.requestSubmit();
    });
  });
})();
