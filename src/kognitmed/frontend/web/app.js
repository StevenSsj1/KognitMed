const CHAT_ENDPOINT = "/api/v1/orientador";
const THEME_KEY = "kognitmed.theme";
const LOCATION_KEY = "kognitmed.location";
const CHAT_STATE_KEY = "kognitmed.chat-state";

const welcomeMessage = {
  id: "welcome",
  role: "assistant",
  content: "Hola. Describe tu consulta: que sientes, desde cuando y si algo lo empeora.",
};

const elements = {
  app: document.querySelector("#app-shell"),
  closeSidebar: document.querySelector("#close-sidebar"),
  collapseSidebar: document.querySelector("#collapse-sidebar"),
  composer: document.querySelector("#composer"),
  composerStatus: document.querySelector("#composer-status"),
  composerStatusText: document.querySelector("#composer-status-text"),
  conversationTitle: document.querySelector("#conversation-title"),
  history: document.querySelector("#history"),
  input: document.querySelector("#message-input"),
  locationState: document.querySelector("#location-state"),
  messages: document.querySelector("#messages"),
  newChat: document.querySelector("#new-chat"),
  openSidebar: document.querySelector("#open-sidebar"),
  providerLabel: document.querySelector("#provider-label"),
  scrim: document.querySelector("#scrim"),
  scrollButton: document.querySelector("#scroll-button"),
  sendButton: document.querySelector("#send-button"),
  themeGlyph: document.querySelector("#theme-glyph"),
  themeToggle: document.querySelector("#theme-toggle"),
};

const state = loadState();

function createId() {
  return crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2, 10);
}

function createConversation() {
  return {
    id: createId(),
    apiConversationId: null,
    title: "Nueva conversacion",
    updatedAt: Date.now(),
    messages: [{ ...welcomeMessage }],
  };
}

function loadState() {
  try {
    const stored = JSON.parse(localStorage.getItem(CHAT_STATE_KEY) || "null");
    if (stored?.conversations?.length && stored.activeId) {
      return stored;
    }
  } catch {
    localStorage.removeItem(CHAT_STATE_KEY);
  }

  const conversation = createConversation();
  return {
    activeId: conversation.id,
    conversations: [conversation],
  };
}

function activeConversation() {
  return state.conversations.find((conversation) => conversation.id === state.activeId);
}

function persistState() {
  localStorage.setItem(CHAT_STATE_KEY, JSON.stringify(state));
}

function textPreview(conversation) {
  const message = [...conversation.messages].reverse().find((entry) => entry.role === "user");
  return message?.content || "Lista para iniciar";
}

function formatGroupLabel(updatedAt) {
  const now = new Date();
  const date = new Date(updatedAt);
  const sameDay = now.toDateString() === date.toDateString();
  return sameDay ? "Hoy" : "Anteriores";
}

function groupedConversations() {
  const groups = new Map();
  [...state.conversations]
    .sort((left, right) => right.updatedAt - left.updatedAt)
    .forEach((conversation) => {
      const label = formatGroupLabel(conversation.updatedAt);
      groups.set(label, [...(groups.get(label) || []), conversation]);
    });
  return groups;
}

function renderHistory() {
  elements.history.replaceChildren();

  groupedConversations().forEach((conversations, label) => {
    const section = document.createElement("section");
    section.className = "history-group";

    const heading = document.createElement("p");
    heading.className = "history-label";
    heading.textContent = label;
    section.append(heading);

    conversations.forEach((conversation) => {
      const row = document.createElement("div");
      row.className = "history-row";

      const button = document.createElement("button");
      button.type = "button";
      button.className = "history-button";
      button.setAttribute("aria-current", String(conversation.id === state.activeId));
      button.addEventListener("click", () => selectConversation(conversation.id));

      const title = document.createElement("span");
      title.className = "history-title";
      title.textContent = conversation.title;

      const preview = document.createElement("span");
      preview.className = "history-preview";
      preview.textContent = textPreview(conversation);

      button.append(title, preview);

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "history-delete";
      remove.title = "Eliminar conversacion";
      remove.setAttribute("aria-label", `Eliminar ${conversation.title}`);
      remove.addEventListener("click", () => deleteConversation(conversation.id, row));

      row.append(button, remove);
      section.append(row);
    });

    elements.history.append(section);
  });
}

function messageNode(message) {
  const item = document.createElement("li");
  item.className = `message ${message.role}`;
  item.dataset.messageId = message.id;

  const body = document.createElement("div");
  body.className = "message-body";

  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = message.role === "user" ? "TU" : "KM";

  const speaker = document.createElement("span");
  speaker.className = "speaker";
  speaker.textContent = message.role === "user" ? "Tu" : "KognitMed";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = message.content;
  body.append(avatar, speaker, bubble);

  if (message.role === "assistant" && !message.pending) {
    const actions = document.createElement("div");
    actions.className = "message-actions";

    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "copy-button";
    copy.title = "Copiar respuesta";
    copy.setAttribute("aria-label", "Copiar respuesta");
    copy.textContent = "Copiar";
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(message.content);
        copy.classList.add("copied");
        copy.title = "Respuesta copiada";
        window.setTimeout(() => {
          copy.classList.remove("copied");
          copy.title = "Copiar respuesta";
        }, 1200);
      } catch {
        copy.classList.add("copy-error");
      }
    });
    actions.append(copy);
    body.append(actions);
  }

  item.append(body);
  return item;
}

function renderMessages() {
  const conversation = activeConversation();
  if (!conversation) {
    return;
  }

  elements.messages.replaceChildren(...conversation.messages.map(messageNode));
  elements.conversationTitle.textContent = conversation.title;
  scrollToLatest();
}

function render() {
  renderHistory();
  renderMessages();
  persistState();
}

function selectConversation(conversationId) {
  state.activeId = conversationId;
  elements.app.classList.remove("sidebar-open");
  setStatus("Listo");
  render();
}

function startConversation() {
  const conversation = createConversation();
  state.conversations.unshift(conversation);
  state.activeId = conversation.id;
  elements.input.value = "";
  autoSizeInput();
  setStatus("Listo");
  render();
}

function deleteConversation(conversationId, row) {
  if (row && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    row.classList.add("is-removing");
    window.setTimeout(() => removeConversation(conversationId), 180);
    return;
  }

  removeConversation(conversationId);
}

function removeConversation(conversationId) {
  const removedActiveConversation = conversationId === state.activeId;
  state.conversations = state.conversations.filter((conversation) => conversation.id !== conversationId);

  if (state.conversations.length === 0) {
    const conversation = createConversation();
    state.conversations = [conversation];
    state.activeId = conversation.id;
  } else if (removedActiveConversation) {
    state.activeId = [...state.conversations].sort((left, right) => right.updatedAt - left.updatedAt)[0].id;
  }

  elements.input.value = "";
  autoSizeInput();
  setStatus("Conversacion eliminada");
  render();
}

function titleFromPrompt(prompt) {
  const compact = prompt.replace(/\s+/g, " ").trim();
  return compact.length > 42 ? `${compact.slice(0, 42)}...` : compact;
}

function setStatus(message, provider) {
  elements.composerStatusText.textContent = message;
  elements.composer.dataset.status = message === "Consultando..." ? "loading" : "ready";
  if (provider) {
    elements.providerLabel.textContent = `Proveedor ${provider}`;
  }
}

function addPendingMessage(conversation) {
  const pending = {
    id: createId(),
    role: "assistant",
    content: "",
    pending: true,
  };
  conversation.messages.push(pending);
  return pending.id;
}

function renderPendingMessage(messageId) {
  const node = elements.messages.querySelector(`[data-message-id="${messageId}"] .bubble`);
  if (!node) {
    return;
  }

  node.replaceChildren();
  const typing = document.createElement("span");
  typing.className = "typing";
  typing.setAttribute("aria-label", "Generando respuesta");
  typing.append(document.createElement("i"), document.createElement("i"), document.createElement("i"));
  node.append(typing);
}

async function submitMessage(event) {
  event.preventDefault();
  const conversation = activeConversation();
  const prompt = elements.input.value.trim();
  if (!conversation || !prompt || elements.sendButton.disabled) {
    return;
  }

  const userMessage = {
    id: createId(),
    role: "user",
    content: prompt,
  };

  conversation.messages.push(userMessage);
  conversation.updatedAt = Date.now();
  if (conversation.title === "Nueva conversacion") {
    conversation.title = titleFromPrompt(prompt);
  }

  const pendingId = addPendingMessage(conversation);
  elements.input.value = "";
  elements.sendButton.disabled = true;
  autoSizeInput();
  setStatus("Consultando...");
  render();
  renderPendingMessage(pendingId);

  const payload = { message: prompt };
  if (conversation.apiConversationId) {
    payload.conversation_id = conversation.apiConversationId;
  }

  try {
    const response = await fetch(CHAT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body?.error?.message || `HTTP ${response.status}`);
    }

    conversation.apiConversationId = body.conversation_id;
    const assistantReply = body.reply || body.response || "No se recibio respuesta del orientador.";
    conversation.messages = conversation.messages.map((message) =>
      message.id === pendingId
        ? {
            id: pendingId,
            role: "assistant",
            content: assistantReply,
          }
        : message,
    );
    setStatus("Listo", body.provider);
  } catch (error) {
    conversation.messages = conversation.messages.map((message) =>
      message.id === pendingId
        ? {
            id: pendingId,
            role: "assistant",
            content: `No pude obtener respuesta. ${error.message}`,
          }
        : message,
    );
    setStatus("Respuesta no disponible");
  } finally {
    elements.sendButton.disabled = false;
    conversation.updatedAt = Date.now();
    render();
    elements.input.focus();
  }
}

function autoSizeInput() {
  elements.input.style.height = "0";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 180)}px`;
}

function scrollToLatest() {
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function toggleScrollButton() {
  const remaining = elements.messages.scrollHeight - elements.messages.scrollTop - elements.messages.clientHeight;
  elements.scrollButton.classList.toggle("visible", remaining > 120);
}

function preferredTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "dark" || stored === "light") {
    return stored;
  }
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function setTheme(theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  elements.themeGlyph.innerHTML = theme === "dark" ? "&#9728;" : "&#9789;";
  localStorage.setItem(THEME_KEY, theme);
}

function toggleTheme() {
  setTheme(document.documentElement.classList.contains("dark") ? "light" : "dark");
}

function updateLocationState(kind, message) {
  elements.locationState.className = `location-state ${kind}`.trim();
  elements.locationState.textContent = message;
}

function storeLocation(position) {
  const location = {
    latitude: Number(position.coords.latitude.toFixed(6)),
    longitude: Number(position.coords.longitude.toFixed(6)),
    accuracy: Math.round(position.coords.accuracy),
    capturedAt: new Date().toISOString(),
  };
  localStorage.setItem(LOCATION_KEY, JSON.stringify(location));
  updateLocationState("ready", "Ubicacion guardada");
}

function requestLocationOnLoad() {
  if (!navigator.geolocation || !window.isSecureContext) {
    updateLocationState("error", "Ubicacion no disponible");
    return;
  }

  const stored = localStorage.getItem(LOCATION_KEY);
  if (stored) {
    updateLocationState("ready", "Ubicacion guardada");
  }

  navigator.geolocation.getCurrentPosition(
    storeLocation,
    () => updateLocationState(stored ? "ready" : "error", stored ? "Ubicacion guardada" : "Ubicacion pendiente"),
    {
      enableHighAccuracy: false,
      maximumAge: 300000,
      timeout: 10000,
    },
  );
}

elements.composer.addEventListener("submit", submitMessage);
elements.input.addEventListener("input", autoSizeInput);
elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.composer.requestSubmit();
  }
});
elements.newChat.addEventListener("click", startConversation);
elements.openSidebar.addEventListener("click", () => elements.app.classList.add("sidebar-open"));
elements.closeSidebar.addEventListener("click", () => elements.app.classList.remove("sidebar-open"));
elements.scrim.addEventListener("click", () => elements.app.classList.remove("sidebar-open"));
elements.collapseSidebar.addEventListener("click", () => elements.app.classList.toggle("sidebar-collapsed"));
elements.themeToggle.addEventListener("click", toggleTheme);
elements.scrollButton.addEventListener("click", scrollToLatest);
elements.messages.addEventListener("scroll", toggleScrollButton);

setTheme(preferredTheme());
autoSizeInput();
render();
toggleScrollButton();
requestLocationOnLoad();
