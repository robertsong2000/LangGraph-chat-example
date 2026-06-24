// ─────────────────────────────────────────────────────────────
//  LangGraph Multi-Agent Chat — frontend logic
//  Features: Enter-to-send (Shift+Enter newline), IME-safe,
//            EN/ZH language switching.
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

const AVATAR = {
  supervisor: { emoji: "🧭", cls: "sup" },
  coder:      { emoji: "👨‍💻", cls: "code" },
  researcher: { emoji: "🔬", cls: "res" },
  writer:     { emoji: "✍️", cls: "wri" },
  user:       { emoji: "🧑", cls: "sup" },
};

let threadId = null;
let busy = false;

// ---------- i18n boot ----------
applyI18n(getLang());

langBtn.addEventListener("click", () => {
  const next = getLang() === "zh" ? "en" : "zh";
  setLang(next);
  applyI18n(next);
  // Re-render dynamic status text in the new language.
  refreshStatusText();
  inputEl.focus();
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

// ---------- Helpers ----------
function scrollDown() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function highlightAgent(name) {
  teamItems.forEach((li) =>
    li.classList.toggle("active", li.dataset.agent === name));
}

// ---------- Markdown rendering for AI replies ----------
// User messages stay as plain text (safe). AI replies are parsed with marked
// so that **bold**, ### headings, lists, ```code blocks```, etc. render properly.
function renderMarkdown(text) {
  if (typeof marked === "undefined") return escapeHtml(text);
  // Don't allow raw HTML inside markdown; escape it first.
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
    bubble.textContent = content;   // user input: plain text, never HTML
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

function setBusy(state) {
  busy = state;
  sendBtn.disabled = state;
  inputEl.disabled = state;
}

// ---------- Auto-grow textarea + send-button enable ----------
inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
  sendBtn.disabled = busy || !inputEl.value.trim();
});

// ---------- Enter to send · Shift+Enter for newline (IME-safe) ----------
// `compositionstart`/`compositionend` fires while using CJK input methods.
// We track composing state so Enter inside the IME candidate box never sends.
let composing = false;
inputEl.addEventListener("compositionstart", () => { composing = true; });
inputEl.addEventListener("compositionend", () => { composing = false; });
// Enable the send button once composition finishes.
inputEl.addEventListener("compositionend", () => {
  sendBtn.disabled = busy || !inputEl.value.trim();
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  // Shift+Enter → newline (default behaviour, do nothing).
  if (e.shiftKey) return;
  // While the IME is composing (picking Chinese characters), let Enter
  // confirm the candidate instead of sending.
  if (composing) return;
  e.preventDefault();            // no newline
  if (!busy && inputEl.value.trim()) {
    composer.requestSubmit();    // trigger the submit handler
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
  if (threadId) fetch("/api/reset/" + threadId, { method: "POST" }).catch(() => {});
  threadId = null;
  threadEl.textContent = "—";
  messagesEl.innerHTML = "";
  messagesEl.appendChild(emptyState);
  highlightAgent("");
});

// ---------- Send ----------
composer.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = inputEl.value.trim();
  if (!text || busy) return;

  addMessage("user", text);
  inputEl.value = "";
  inputEl.style.height = "auto";

  // typing indicator
  const typing = addMessage("ai", "", "supervisor");
  typing.querySelector(".bubble").innerHTML =
    '<span class="typing"><span></span><span></span><span></span></span>';

  setBusy(true);

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

    // Render the routing trace (route events only, compact).
    const routeSteps = [];
    for (const traceItem of data.trace) {
      if (traceItem.event === "route") {
        routeSteps.push({ agent: "supervisor", label: t("routes") });
        routeSteps.push({ agent: traceItem.to });
      }
    }
    addTraceRow(routeSteps);

    // Render each agent message in order.
    for (const traceItem of data.trace) {
      if (traceItem.role === "assistant" && traceItem.content) {
        highlightAgent(traceItem.agent);
        addMessage("ai", traceItem.content, traceItem.agent);
        await new Promise((r) => setTimeout(r, 120)); // small reveal delay
      }
    }
    highlightAgent("");
  } catch (err) {
    typing.remove();
    addMessage("ai", "⚠️ " + err.message, "supervisor");
  } finally {
    setBusy(false);
    inputEl.focus();
  }
});

inputEl.focus();
