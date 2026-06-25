"""FastAPI server exposing the multi-agent graph to a web UI.

Endpoints
---------
GET  /                   — chat page
GET  /api/health         — liveness probe
POST /api/chat           — non-streaming chat (returns full trace)
GET  /api/threads/{id}   — replay a saved conversation
POST /api/reset/{id}     — clear a thread's history
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.agents import app_graph, FINISH, SUPERVISOR
from app.core.config import settings

app = FastAPI(title="LangGraph Multi-Agent Chat")
app.mount("/static", StaticFiles(directory="static"), name="static")


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _new_thread_id() -> str:
    return uuid.uuid4().hex[:12]


def _trace_from_stream(stream: Any) -> list[dict]:
    """Walk the LangGraph stream and pull out agent messages + routing steps."""
    trace: list[dict] = []
    for chunk in stream:
        # chunk maps node-name -> state-delta
        for node_name, state_delta in chunk.items():
            new_msgs = state_delta.get("messages", []) if state_delta else []
            for msg in new_msgs:
                role = "assistant" if isinstance(msg, AIMessage) else "user"
                trace.append({
                    "agent": getattr(msg, "name", None) or node_name,
                    "role": role,
                    "content": str(msg.content),
                    "node": node_name,
                })
            nxt = state_delta.get("next") if state_delta else None
            if nxt and nxt != FINISH:
                trace.append({"event": "route", "to": nxt})
    return trace


# --------------------------------------------------------------------------- #
# Routes — pages
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
async def index():
    with open("templates/index.html", encoding="utf-8") as fh:
        return HTMLResponse(fh.read())


@app.get("/architecture", response_class=HTMLResponse)
async def architecture():
    with open("templates/architecture.html", encoding="utf-8") as fh:
        return HTMLResponse(fh.read())


# --------------------------------------------------------------------------- #
# Routes — API
# --------------------------------------------------------------------------- #
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": settings.model_name,
        "llm_mode": "real" if settings.can_use_real_llm else "mock",
        "agents": settings.enabled_agents,
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Run one user turn and return the full trace + final answer."""
    thread_id = req.thread_id or _new_thread_id()
    config = {"configurable": {"thread_id": thread_id}}

    # Seed the message into the persisted state, then stream execution.
    inputs = {
        "messages": [HumanMessage(content=req.message)],
        "active_agent": None,
        "next": SUPERVISOR,
        "turn_count": 0,
    }
    stream = app_graph.stream(inputs, config=config, stream_mode="updates")
    trace = _trace_from_stream(stream)

    # Pull the final assistant message out of the persisted state.
    snapshot = app_graph.get_state(config)
    final = ""
    if snapshot and snapshot.values.get("messages"):
        last = snapshot.values["messages"][-1]
        if isinstance(last, AIMessage):
            final = str(last.content)

    return JSONResponse({
        "thread_id": thread_id,
        "trace": trace,
        "final": final,
        "llm_mode": "real" if settings.can_use_real_llm else "mock",
    })


@app.get("/api/threads/{thread_id}")
async def get_thread(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = app_graph.get_state(config)
    if not snapshot:
        raise HTTPException(404, "thread not found")
    msgs = []
    for m in snapshot.values.get("messages", []):
        msgs.append({
            "role": "assistant" if isinstance(m, AIMessage) else "user",
            "agent": getattr(m, "name", None),
            "content": str(m.content),
        })
    return {"thread_id": thread_id, "messages": msgs}


@app.post("/api/reset/{thread_id}")
async def reset_thread(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    try:
        app_graph.update_state(config, {"messages": [],
                                        "next": SUPERVISOR,
                                        "turn_count": 0})
    except Exception:  # pragma: no cover
        pass
    return {"thread_id": thread_id, "status": "reset"}


@app.delete("/api/threads/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete a thread's persisted state from the checkpointer."""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        # MemorySaver stores channels in a dict keyed by thread config.
        # Clearing the messages/next/turn_count empties the visible state.
        app_graph.update_state(config, {"messages": [],
                                        "next": SUPERVISOR,
                                        "turn_count": 0,
                                        "active_agent": None})
    except Exception:
        pass
    return {"thread_id": thread_id, "status": "deleted"}
