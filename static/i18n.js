// ─────────────────────────────────────────────────────────────
//  i18n dictionary — English (en) / 中文 (zh)
// ─────────────────────────────────────────────────────────────
const I18N = {
  en: {
    appTitle:       "LangGraph Chat",
    appTagline:     "Multi-agent orchestration",
    connecting:     "connecting…",
    liveLLM:        "Live LLM connected",
    mockMode:       "Mock mode (no API key)",
    offline:        "server offline",
    model:          "Model",
    teamTitle:      "The Team",
    supName:        "Supervisor",
    supDesc:        "routes & coordinates",
    coderName:      "Coder",
    coderDesc:      "writes & debugs code",
    resName:        "Researcher",
    resDesc:        "analyzes & compares",
    writerName:     "Writer",
    writerDesc:     "drafts & polishes",
    newChat:        "＋ New conversation",
    hint:           "Conversations persist across server restarts via the LangGraph checkpointer.",
    conversation:   "Conversation",
    thread:         "thread",
    exCode:         "Code task",
    exResearch:     "Research task",
    exWriting:      "Writing task",
    emptyTitle:     "Ask anything",
    emptyBody:      "The supervisor will route your request to the right specialist agent — watch the trace light up in real time.",
    inputPlaceholder: "Send a message…",
    send:           "Send",
    enterHint:      "Enter to send · Shift+Enter for newline · queue supported",
    routes:         "routes",
    queued:         "queued",   // pending tag shown on a message waiting its turn
    sessionsTitle:  "Sessions",
    noSessions:     "No sessions yet",
    deleteSession:  "Delete",
    confirmDelete:  "Delete this session?",
    newSession:     "New session",
    switchLang:     "中文",   // label shown when current lang is EN (click → zh)
  },
  zh: {
    appTitle:       "LangGraph 对话",
    appTagline:     "多智能体协作",
    connecting:     "连接中…",
    liveLLM:        "已连接真实模型",
    mockMode:       "模拟模式（无 API Key）",
    offline:        "服务离线",
    model:          "模型",
    teamTitle:      "智能体团队",
    supName:        "监督者",
    supDesc:        "路由与协调",
    coderName:      "程序员",
    coderDesc:      "编写与调试代码",
    resName:        "研究员",
    resDesc:        "分析与对比",
    writerName:     "作家",
    writerDesc:     "撰写与润色",
    newChat:        "＋ 新建对话",
    hint:           "对话通过 LangGraph 检查点持久化，重启服务后依然保留。",
    conversation:   "对话",
    thread:         "会话",
    exCode:         "代码任务",
    exResearch:     "研究任务",
    exWriting:      "写作任务",
    emptyTitle:     "随便问点什么",
    emptyBody:      "监督者会把你的请求路由给最合适的专家智能体——实时查看路由轨迹。",
    inputPlaceholder: "输入消息…",
    send:           "发送",
    enterHint:      "回车发送 · Shift+回车换行 · 支持排队",
    routes:         "路由",
    queued:         "排队中",   // pending tag shown on a message waiting its turn
    sessionsTitle:  "会话记录",
    noSessions:     "暂无会话",
    deleteSession:  "删除",
    confirmDelete:  "确定删除这个会话吗？",
    newSession:     "新会话",
    switchLang:     "EN",    // label shown when current lang is ZH (click → en)
  },
};

const LANG_KEY = "lg_chat_lang";

function getLang() {
  return localStorage.getItem(LANG_KEY) || "zh";   // default 中文
}

function setLang(lang) {
  localStorage.setItem(LANG_KEY, lang);
}

/** Apply the current language to every [data-i18n] element in the DOM. */
function applyI18n(lang) {
  const dict = I18N[lang] || I18N.en;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (dict[key] != null) el.textContent = dict[key];
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (dict[key] != null) el.placeholder = dict[key];
  });
  // The language toggle button shows the *other* language's label.
  const lbl = document.getElementById("langLabel");
  if (lbl) lbl.textContent = dict.switchLang;
  document.documentElement.lang = lang;
}

function t(key) {
  const dict = I18N[getLang()] || I18N.en;
  return dict[key] != null ? dict[key] : key;
}
