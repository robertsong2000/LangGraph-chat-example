// ─────────────────────────────────────────────────────────────
//  LangGraph Multi-Agent Chat — frontend logic
//  Features: message queue (send while busy → pending → processed),
//            Enter-to-send (Shift+Enter newline), IME-safe,
//            EN/ZH language switching, markdown rendering.
// ─────────────────────────────────────────────────────────────

// ---------- Element refs ----------
const $ = (sel) => document.querySelector(sel);
const messagesEl = $("#messages");
const inputEl    = $("#input");
const sendBtn    = $("#sendBtn");
const composer   = $("#composer");
const threadEl   = $("#threadId");
const modeDot    = $("#modeDot");
const modeText   = $("#modeText");
const modelText  = $("#modelText");
const emptyState = $("#emptyState");
const teamItems  = document.querySelectorAll(".team-list li");
const langBtn    = $("#langBtn");
const themeBtn   = $("#themeBtn");
const sessionListEl = $("#sessionList");

// Avatar + Chinese-name registry. Keys mirror the backend role pool
// (app/agents/roles.py) so a recruited specialist always renders with its
// own emoji and a stable colour. Roles not listed here (e.g. chat mode's
// coder/researcher/writer) fall back to a hash-assigned colour below.
const AVATAR = {
  // fixed chat-mode roles
  supervisor: { emoji: "🧭", cls: "sup" },
  coder:      { emoji: "👨‍💻", cls: "code" },
  researcher: { emoji: "🔬", cls: "res" },
  writer:     { emoji: "✍️", cls: "wri" },
  user:       { emoji: "🧑", cls: "sup" },
  // discussion role pool
  historian:       { emoji: "📜", name: "历史学家" },
  philosopher:     { emoji: "🦉", name: "哲学家" },
  scientist:       { emoji: "🔬", name: "科学家" },
  chef:            { emoji: "🍳", name: "美食家" },
  economist:       { emoji: "💰", name: "经济学家" },
  psychologist:    { emoji: "🧠", name: "心理学家" },
  engineer:        { emoji: "⚙️", name: "工程师" },
  lawyer:          { emoji: "⚖️", name: "法学家" },
  artist:          { emoji: "🎨", name: "艺术家" },
  doctor:          { emoji: "🩺", name: "医学家" },
  educator:        { emoji: "📚", name: "教育家" },
  sociologist:     { emoji: "👥", name: "社会学家" },
  ethicist:        { emoji: "🧭", name: "伦理学家" },
  designer:        { emoji: "📐", name: "设计师" },
  entrepreneur:    { emoji: "🚀", name: "创业者" },
  environmentalist:{ emoji: "🌱", name: "环保学者" },
  strategist:      { emoji: "♟️", name: "战略顾问" },
};

// Stable colour buckets for roles without an explicit `.cls`. Each unknown
// role name is hashed to one of these, so even an ad-hoc role gets a
// consistent avatar colour instead of falling back to the supervisor grey.
const FALLBACK_COLORS = ["c0","c1","c2","c3","c4","c5","c6","c7"];

function avatarFor(agent) {
  const av = AVATAR[agent];
  if (av) {
    return { emoji: av.emoji, cls: av.cls || ("role " + _hashColor(agent)) };
  }
  // Unknown role → supervisor emoji but a hash-derived colour.
  return { emoji: "🎯", cls: "role " + _hashColor(agent) };
}

// Friendly display label: the Chinese name from the pool, or the raw agent
// string if it isn't a known role (e.g. "coordinator"/"summarizer").
function labelFor(agent) {
  return (AVATAR[agent] && AVATAR[agent].name) || agent;
}

function _hashColor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return FALLBACK_COLORS[Math.abs(h) % FALLBACK_COLORS.length];
}

let threadId = null;
let processing = false;   // is a request currently in-flight?
const queue = [];         // pending user messages awaiting their turn

// ─────────────────────────────────────────────────────────────
//  Session store (localStorage)
//  Each session: { id, title, createdAt, updatedAt }
//  Messages themselves stay on the server (checkpointer); we only
//  persist lightweight metadata here for the sidebar list.
// ─────────────────────────────────────────────────────────────
const SESSIONS_KEY = "lg_chat_sessions";

// Generate a thread id matching the server's format (uuid hex, 12 chars).
function makeThreadId() {
  // crypto.randomUUID is available in modern browsers; fall back if needed.
  if (window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID().replace(/-/g, "").slice(0, 12);
  }
  return Math.random().toString(16).slice(2, 14);
}

function loadSessions() {
  try { return JSON.parse(localStorage.getItem(SESSIONS_KEY) || "[]"); }
  catch { return []; }
}
function saveSessions(list) {
  localStorage.setItem(SESSIONS_KEY, JSON.stringify(list));
}
function findSession(id) {
  return loadSessions().find((s) => s.id === id);
}
function upsertSession(id, title) {
  const list = loadSessions();
  let s = list.find((x) => x.id === id);
  const now = Date.now();
  const placeholder = t("newSession");
  if (!s) {
    s = { id, title: title || placeholder, createdAt: now, updatedAt: now };
    list.unshift(s);
  } else {
    // Only overwrite the title with a real one (not the placeholder).
    if (title && title !== placeholder) s.title = title;
    s.updatedAt = now;
    // move to top
    list.splice(list.indexOf(s), 1);
    list.unshift(s);
  }
  saveSessions(list);
}
function deleteSession(id) {
  const list = loadSessions().filter((s) => s.id !== id);
  saveSessions(list);
}

function renderSessionList() {
  const list = loadSessions();
  sessionListEl.innerHTML = "";
  if (list.length === 0) {
    const li = document.createElement("li");
    li.className = "session-empty";
    li.textContent = t("noSessions");
    sessionListEl.appendChild(li);
    return;
  }
  list.forEach((s) => {
    const li = document.createElement("li");
    li.className = "session-item" + (s.id === threadId ? " active" : "");
    li.dataset.id = s.id;
    li.innerHTML =
      '<span class="s-icon">💬</span>' +
      '<span class="s-title"></span>' +
      '<button class="s-del" title="' + t("deleteSession") + '">✕</button>';
    li.querySelector(".s-title").textContent = s.title;
    // click to switch session
    li.addEventListener("click", (e) => {
      if (e.target.closest(".s-del")) return;   // delete handled separately
      switchSession(s.id);
    });
    // delete button
    li.querySelector(".s-del").addEventListener("click", (e) => {
      e.stopPropagation();
      removeSession(s.id);
    });
    sessionListEl.appendChild(li);
  });
}

async function switchSession(id) {
  // Cancel any in-flight / queued work first.
  queue.length = 0;
  processing = false;
  threadId = id;
  threadEl.textContent = id;
  // Load messages from server checkpointer.
  messagesEl.innerHTML = "";
  try {
    const r = await fetch("/api/threads/" + id);
    const data = await r.json();
    for (const m of data.messages) {
      if (m.role === "assistant") addMessage("ai", m.content, m.agent);
      else addMessage("user", m.content, "user");
    }
  } catch {
    // thread may have been cleared on the server — show empty state
  }
  if (messagesEl.children.length === 0) messagesEl.appendChild(emptyState);
  renderSessionList();
  inputEl.focus();
}

function removeSession(id) {
  if (!confirm(t("confirmDelete"))) return;
  // Best-effort server-side cleanup.
  fetch("/api/threads/" + id, { method: "DELETE" }).catch(() => {});
  deleteSession(id);
  // If we deleted the active session, start fresh.
  if (id === threadId) {
    threadId = null;
    threadEl.textContent = "—";
    queue.length = 0;
    processing = false;
    messagesEl.innerHTML = "";
    messagesEl.appendChild(emptyState);
  }
  renderSessionList();
}

// ---------- i18n boot ----------
applyI18n(getLang());

langBtn.addEventListener("click", () => {
  const next = getLang() === "zh" ? "en" : "zh";
  setLang(next);
  applyI18n(next);
  refreshStatusText();
  inputEl.focus();
});

// ---------- theme toggle ----------
themeBtn.addEventListener("click", toggleTheme);
// React to OS theme changes if the user hasn't picked manually.
window.matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => {
  if (!localStorage.getItem(THEME_KEY)) applyTheme(getTheme());
});

// ---------- Boot: health check ----------
async function boot() {
  try {
    const r = await fetch("/api/health");
    const d = await r.json();
    window.__health = d;
    refreshStatusText();
    modelText.textContent = d.model;
  } catch {
    window.__health = null;
    modeText.textContent = t("offline");
  }
}

function refreshStatusText() {
  const d = window.__health;
  if (!d) { modeText.textContent = t("offline"); return; }
  modeText.textContent = d.llm_mode === "real" ? t("liveLLM") : t("mockMode");
  modeDot.className = "dot " + d.llm_mode;
}
boot();
renderSessionList();   // populate sidebar session list on load

// ---------- Helpers ----------
function scrollDown() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function highlightAgent(name) {
  teamItems.forEach((li) =>
    li.classList.toggle("active", li.dataset.agent === name));
}

function updateSendBtn() {
  // Send button only reflects whether there's text; it is never disabled
  // because a request is in-flight — that's the whole point of the queue.
  sendBtn.disabled = !inputEl.value.trim();
}

// ---------- Markdown rendering for AI replies ----------
function renderMarkdown(text) {
  if (typeof marked === "undefined") return escapeHtml(text);
  marked.setOptions({ breaks: true, gfm: true });
  return marked.parse(text);
}

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function addMessage(role, content, agent) {
  if (emptyState) emptyState.remove();
  const wrap = document.createElement("div");
  wrap.className = "msg " + (role === "user" ? "user" : "ai");

  const av = AVATAR[agent] || AVATAR[role];
  wrap.innerHTML = `
    <div class="b-avatar avatar ${av.cls}">${av.emoji}</div>
    <div>
      ${role === "ai" ? `<div class="name ${agent || ""}">${agent || "assistant"}</div>` : ""}
      <div class="bubble"></div>
    </div>`;
  const bubble = wrap.querySelector(".bubble");
  if (role === "ai") {
    bubble.innerHTML = renderMarkdown(content);
  } else {
    bubble.textContent = content;
  }
  messagesEl.appendChild(wrap);
  scrollDown();
  return wrap;
}

function addTraceRow(items) {
  if (!items.length) return;
  const row = document.createElement("div");
  row.className = "trace";
  items.forEach((it, i) => {
    if (i > 0) {
      const a = document.createElement("span");
      a.className = "arrow";
      a.textContent = "→";
      row.appendChild(a);
    }
    const p = document.createElement("span");
    p.className = "pill";
    const av = AVATAR[it.agent] || AVATAR.supervisor;
    const label = it.label || t("routes");
    p.innerHTML = `<span>${av.emoji}</span> ${label}`;
    row.appendChild(p);
  });
  messagesEl.appendChild(row);
  scrollDown();
  return row;
}

// ---------- Auto-grow textarea + send-button enable ----------
inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
  updateSendBtn();
});

// ---------- Enter to send · Shift+Enter for newline (IME-safe) ----------
let composing = false;
inputEl.addEventListener("compositionstart", () => { composing = true; });
inputEl.addEventListener("compositionend", () => {
  composing = false;
  updateSendBtn();
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  if (e.shiftKey) return;            // Shift+Enter → newline
  if (composing) return;             // IME composing → confirm candidate
  e.preventDefault();
  if (inputEl.value.trim()) {
    composer.requestSubmit();
  }
});

// ---------- Example chips ----------
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    inputEl.value = chip.dataset.prompt;
    inputEl.dispatchEvent(new Event("input"));
    inputEl.focus();
  });
});

// ---------- New conversation ----------
$("#newChatBtn").addEventListener("click", () => {
  // Don't reset the current thread — just start a fresh blank view.
  // The old session stays in the sidebar list and on the server.
  queue.length = 0;
  processing = false;
  messagesEl.innerHTML = "";
  messagesEl.appendChild(emptyState);
  highlightAgent("");

  // Pre-create a session so it shows up in the sidebar immediately.
  // We generate the thread_id client-side (same format as the server);
  // the server will reuse it because we send thread_id with each request.
  const newId = makeThreadId();
  threadId = newId;
  threadEl.textContent = newId;
  upsertSession(newId, t("newSession"));
  renderSessionList();
  updateSendBtn();
  inputEl.focus();
});

// ─────────────────────────────────────────────────────────────
//  Message queue
//  Users can send while a request is in-flight. Each new message is
//  shown immediately as a "pending" bubble, then processed strictly in
//  order (FIFO) so the same conversation thread stays coherent.
// ─────────────────────────────────────────────────────────────
function enqueueMessage(text) {
  // Show the user's message right away, flagged as pending until its turn.
  const pendingWrap = addMessage("user", text, "user");
  pendingWrap.classList.add("pending");
  pendingWrap.querySelector(".bubble").insertAdjacentHTML(
    "beforeend",
    '<span class="pending-tag">' + t("queued") + "</span>"
  );
  queue.push({ text, el: pendingWrap });
  processQueue();
}

async function processQueue() {
  // Only one request at a time → preserves conversation order on the server.
  if (processing) return;
  const item = queue.shift();
  if (!item) return;
  processing = true;

  const { text, el: pendingWrap } = item;
  // This message is now being served: drop the pending tag.
  pendingWrap.classList.remove("pending");
  const tag = pendingWrap.querySelector(".pending-tag");
  if (tag) tag.remove();

  // Typing indicator while the agents work.
  const typing = addMessage("ai", "", "supervisor");
  typing.querySelector(".bubble").innerHTML =
    '<span class="typing"><span></span><span></span><span></span></span>';

  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, thread_id: threadId }),
    });
    const data = await r.json();
    typing.remove();

    threadId = data.thread_id;
    threadEl.textContent = threadId;

    // Persist/update this session in localStorage.
    // Title = first user message in the session (truncated), unless a real
    // (non-placeholder) title already exists.
    const existing = findSession(threadId);
    const placeholder = t("newSession");
    const hasRealTitle = existing && existing.title && existing.title !== placeholder;
    const title = hasRealTitle ? existing.title : text.slice(0, 30);
    upsertSession(threadId, title);
    renderSessionList();

    const routeSteps = [];
    for (const traceItem of data.trace) {
      if (traceItem.event === "route") {
        routeSteps.push({ agent: "supervisor", label: t("routes") });
        routeSteps.push({ agent: traceItem.to });
      }
    }
    addTraceRow(routeSteps);

    for (const traceItem of data.trace) {
      if (traceItem.role === "assistant" && traceItem.content) {
        highlightAgent(traceItem.agent);
        addMessage("ai", traceItem.content, traceItem.agent);
        await new Promise((r) => setTimeout(r, 120));
      }
    }
    highlightAgent("");
  } catch (err) {
    typing.remove();
    addMessage("ai", "⚠️ " + err.message, "supervisor");
  } finally {
    processing = false;
    // If more messages piled up while we were busy, serve the next one.
    if (queue.length > 0) processQueue();
    inputEl.focus();
  }
}

// ---------- Send (form submit) ----------
composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = inputEl.value.trim();
  if (!text) return;

  inputEl.value = "";
  inputEl.style.height = "auto";
  updateSendBtn();

  // Always enqueue — never block. processQueue handles serialization.
  enqueueMessage(text);
});

updateSendBtn();
inputEl.focus();

// ═══════════════════════════════════════════════════════════
//  ROUND-TABLE DISCUSSION MODE
// ═══════════════════════════════════════════════════════════
const tabChat       = $("#tabChat");
const tabDiscuss    = $("#tabDiscuss");
const viewChat      = $("#viewChat");
const viewDiscuss   = $("#viewDiscuss");
const discussControls = $("#discussControls");
const discussTopic  = $("#discussTopic");
const discussRounds = $("#discussRounds");
const discussStart  = $("#discussStart");
const discussMessages = $("#discussMessages");
const discussEmpty  = $("#discussEmpty");
let discussBusy = false;
const discussStop   = $("#discussStop");
// AbortController for the active discussion stream, so the user can
// terminate a long discussion before all rounds finish.
let discussController = null;

// ---------- Tab switching ----------
function switchMode(mode) {
  const isChat = mode === "chat";
  tabChat.classList.toggle("active", isChat);
  tabDiscuss.classList.toggle("active", !isChat);
  viewChat.classList.toggle("active", isChat);
  viewDiscuss.classList.toggle("active", !isChat);
}
tabChat.addEventListener("click", () => switchMode("chat"));
tabDiscuss.addEventListener("click", () => switchMode("discuss"));

// ---------- Discussion rendering helpers ----------
function discussScrollDown() {
  discussMessages.scrollTop = discussMessages.scrollHeight;
}

function addRoundDivider(round) {
  const div = document.createElement("div");
  div.className = "round-divider";
  div.innerHTML = '<span>' + t("round") + ' ' + round + '</span>';
  discussMessages.appendChild(div);
  discussScrollDown();
}

function addPanelBanner(roles) {
  if (!roles || !roles.length) return;
  const div = document.createElement("div");
  div.className = "panel-banner";
  const chips = roles.map(r =>
    '<span class="panel-chip">' + (r.emoji || "") + " " + (r.name || r.key) + "</span>"
  ).join("");
  div.innerHTML =
    '<span class="panel-title">' + t("panelTitle") + "</span>" + chips;
  discussMessages.appendChild(div);
  discussScrollDown();
}

function addDiscussMessage(agent, content, isSummary) {
  if (discussEmpty) discussEmpty.remove();
  const wrap = document.createElement("div");
  wrap.className = "msg ai" + (isSummary ? " summary-msg" : "");
  const av = avatarFor(agent);
  wrap.innerHTML =
    '<div class="b-avatar avatar ' + av.cls + '">' + av.emoji + '</div>' +
    '<div>' +
      '<div class="name">' +
        (isSummary ? "📋 " : "") + (isSummary ? t("coordinator") : labelFor(agent)) +
      '</div>' +
      '<div class="bubble"></div>' +
    '</div>';
  wrap.querySelector(".bubble").innerHTML = renderMarkdown(content);
  discussMessages.appendChild(wrap);
  discussScrollDown();
}

// ---------- Discussion runner (streaming via SSE) ----------
discussStart.addEventListener("click", async () => {
  const topic = discussTopic.value.trim();
  const rounds = parseInt(discussRounds.value, 10) || 10;
  if (!topic || discussBusy) return;

  discussBusy = true;
  discussStart.disabled = true;
  discussStart.hidden = true;
  discussStop.hidden = false;
  discussTopic.disabled = true;
  // Create a fresh controller for this discussion so we can abort it.
  discussController = new AbortController();

  // Clear previous discussion in the view.
  discussMessages.innerHTML = "";

  // Typing indicator shown until the first turn arrives.
  const typing = document.createElement("div");
  typing.className = "msg ai";
  typing.innerHTML =
    '<div class="b-avatar avatar sup">🧭</div>' +
    '<div><div class="name supervisor">' + t("coordinator") + '</div>' +
    '<div class="bubble"><span class="typing"><span></span><span></span><span></span></span></div></div>';
  discussMessages.appendChild(typing);
  discussScrollDown();

  let lastRound = 0;
  let firstTurn = true;

  try {
    const resp = await fetch("/api/discuss", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, rounds }),
      signal: discussController.signal,
    });

    // Read the SSE stream incrementally.
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by a blank line; process each complete one.
      let idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const line = raw.replace(/^data:\s*/, "").trim();
        if (!line) continue;

        let evt;
        try { evt = JSON.parse(line); } catch { continue; }

        // Drop the typing indicator once real content starts arriving.
        if (firstTurn && evt.type === "turn") {
          typing.remove();
          firstTurn = false;
        }

        // Announce the recruited panel as a banner before the turns.
        if (evt.type === "panel" && evt.roles) {
          addPanelBanner(evt.roles);
        }

        if (evt.type === "turn") {
          const isSummary = evt.round === "summary";
          // Insert a round divider when the round number changes.
          if (!isSummary && evt.round !== lastRound) {
            lastRound = evt.round;
            addRoundDivider(lastRound);
          } else if (isSummary) {
            addRoundDivider("✦");
          }
          addDiscussMessage(evt.agent, evt.content, isSummary);
        }
      }
    }
    // Clean up if no turns ever arrived.
    if (firstTurn) typing.remove();
  } catch (err) {
    typing.remove();
    if (err.name === "AbortError") {
      // User pressed Stop — show a friendly note instead of an error.
      addDiscussMessage("supervisor", "⏹ " + t("stopped"), false);
    } else {
      addDiscussMessage("supervisor", "⚠️ " + err.message, false);
    }
  } finally {
    discussBusy = false;
    discussStart.disabled = false;
    discussStart.hidden = false;
    discussStop.hidden = true;
    discussTopic.disabled = false;
    discussController = null;
  }
});

// Stop button: abort the active discussion stream.
discussStop.addEventListener("click", () => {
  if (discussController) discussController.abort();
});

// Enter key in topic input triggers start.
discussTopic.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    discussStart.click();
  }
});
