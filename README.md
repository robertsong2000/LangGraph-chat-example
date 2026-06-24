# LangGraph Multi-Agent Chat 🌟

A multi-agent conversational web app built on **LangGraph**. A central
**supervisor** routes each user message to the best specialist — **Coder**,
**Researcher**, or **Writer** — then decides when the task is done. Every
conversation is persisted with a LangGraph **checkpointer**, so threads survive
across server restarts.

```
        ┌──────────────┐
   ┌───▶│  supervisor  │◀─────────────────────┐
   │    └──────┬───────┘                       │
   │           │ next = coder|researcher|writer │
   │  ┌────────┼────────┐                      │
   │  ▼        ▼        ▼                      │
   │ coder  researcher writer                  │
   │  │        │        │                      │
   │  └────────┴────────┴──────────────────────┘
   │            (hand control back to supervisor)
   ▼  next == "FINISH"  →  END
```

## Features

- **StateGraph orchestration** — supervisor + 3 specialists with conditional
  routing edges and a `MAX_TURNS` safety bound.
- **Persistent threads** — `MemorySaver` checkpointer keyed by `thread_id`.
  Reload a full conversation at any time.
- **Live agent trace** — the UI shows which agent the supervisor picked and the
  hand-off chain for each turn.
- **Zero-config mock mode** — runs immediately without an API key using a
  deterministic rule-based model, so you can explore the UI before plugging in a
  real LLM. Set `OPENAI_API_KEY` (and optionally `API_BASE` for GLM/compatible
  endpoints) to switch to a live model.
- **FastAPI backend** with health, chat, thread-replay, and reset endpoints.

## Quick start

```bash
# 1. Install dependencies (creates venv automatically)
./start.sh              # one command — runs in Mock mode if no key

# 2. Optional: use a real LLM (GLM-5.2)
cp .env.example .env    # then edit .env and paste your key
./start.sh
# → open http://localhost:8000
```

The header badge shows **Mock mode (no API key)** or **Live LLM connected** so
you always know which path is active.

## Configuration (env vars)

| Variable          | Default                  | Purpose                                            |
|-------------------|--------------------------|----------------------------------------------------|
| `MODEL_NAME`      | `openai/gpt-4o-mini`     | Model id. A `provider/` prefix is stripped for OpenAI. |
| `OPENAI_API_KEY`  | —                        | API key. Enables the real LLM; omit for mock mode. |
| `API_BASE`        | —                        | OpenAI-compatible base URL (GLM, Together, …).     |
| `API_KEY`         | —                        | Fallback key name if `OPENAI_API_KEY` is unset.    |
| `TEMPERATURE`     | `0.7`                    | Sampling temperature.                               |
| `HOST` / `PORT`   | `0.0.0.0` / `8000`       | Bind address.                                       |
| `SQLITE_PATH`     | `./chat_checkpoints.db`  | (Reserved for the optional SQLite checkpointer.)   |

## API

| Method | Path                  | Description                                  |
|--------|-----------------------|----------------------------------------------|
| GET    | `/`                   | Chat UI.                                     |
| GET    | `/api/health`         | Status, model, and llm mode.                 |
| POST   | `/api/chat`           | `{message, thread_id?}` → `{trace, final}`.  |
| GET    | `/api/threads/{id}`   | Replay a stored conversation.                |
| POST   | `/api/reset/{id}`     | Clear a thread's history.                    |

## Project structure

```
app/
├── core/
│   ├── config.py     # Settings (env-driven)
│   ├── llm.py        # LLM factory + MockLLM fallback
│   └── state.py      # ChatState TypedDict + message helpers
├── agents/
│   └── graph.py      # StateGraph: supervisor + specialists, compiled
└── api/
    └── server.py     # FastAPI app
templates/index.html  # Chat UI
static/{styles.css,app.js}
run.py                # Entry point
requirements.txt
```

## How it works

1. The user message is seeded into a persistent `ChatState`.
2. The **supervisor** node inspects the conversation and returns the next agent
   name (or `FINISH`).
3. A **conditional edge** routes to that specialist, which answers and hands
   control back to the supervisor.
4. The supervisor re-evaluates; once the task is addressed it returns `FINISH`
   and the graph terminates for that turn.
5. The server streams the execution trace so the UI can render the routing and
   each agent's reply.

## Extending

- **Add an agent** — add an entry to `build_team()` in `app/agents/graph.py`
  (name → persona). The graph wires it up automatically.
- **Swap checkpointer** — pass a `SqliteSaver` or `PostgresSaver` to
  `build_graph(checkpointer=...)` for cross-process persistence.
```
