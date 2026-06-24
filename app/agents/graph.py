"""Multi-agent orchestration built on LangGraph's StateGraph.

Layout
------
        ┌──────────────┐
   ┌───▶│  supervisor  │◀─────────────────────┐
   │    └──────┬───────┘                       │
   │           │ next = coder|researcher|...   │
   │  ┌────────┼────────┬──────────┐           │
   │  ▼        ▼        ▼          ▼           │
   │ coder  researcher writer  (finishes)      │
   │  │        │        │                      │
   │  └────────┴────────┴──────────────────────┘
   │            (hand control back to supervisor)
   │
   ▼  next == "FINISH"  →  END

Each specialist answers then returns control to the supervisor, which decides
whether the task is complete (`FINISH`) or another agent is needed.
"""
from __future__ import annotations

from typing import Callable, Dict

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.core.llm import get_llm
from app.core.state import ChatState, last_human_text


FINISH = "FINISH"
SUPERVISOR = "supervisor"
MAX_TURNS = 6  # safety bound on agent hops per user message


# --------------------------------------------------------------------------- #
# Agent node factories
# --------------------------------------------------------------------------- #
def _make_specialist(name: str, persona: str) -> Callable[[ChatState], Dict]:
    """Return a graph node for a specialist agent."""
    llm = get_llm(name)

    def node(state: ChatState) -> Dict:
        prompt = (
            f"You are {persona}. Answer the user's latest message directly, "
            f"concisely and helpfully. Stay in your lane of expertise."
        )
        messages = [{"role": "system", "content": prompt}] + [
            _to_dict(m) for m in state["messages"]
        ]
        reply = llm.invoke(messages)
        # Specialist done → hand control back to supervisor.
        return {
            "messages": [AIMessage(content=_llm_text(reply), name=name)],
            "active_agent": name,
            "next": SUPERVISOR,
            "turn_count": state.get("turn_count", 0) + 1,
        }

    node.__name__ = name
    return node


def _to_dict(message) -> dict:
    """Convert a LangChain message to a plain {role, content} dict."""
    role_map = {"human": "user", "ai": "assistant", "system": "system"}
    role = role_map.get(message.type, "user")
    return {"role": role, "content": str(message.content)}


def _llm_text(result) -> str:
    """Normalise an LLM call result to a plain string.

    Real LLMs return a LangChain `AIMessage` (with a `.content` attribute),
    while the MockLLM returns a bare string. This helper makes every agent node
    agnostic to which one is active.
    """
    if hasattr(result, "content"):
        return str(result.content)
    return str(result)


# --------------------------------------------------------------------------- #
# Supervisor node
# --------------------------------------------------------------------------- #
def _supervisor_node_factory(team: list[str]) -> Callable[[ChatState], Dict]:
    llm = get_llm(SUPERVISOR)

    def supervisor(state: ChatState) -> Dict:
        # Safety: stop after too many hops.
        if state.get("turn_count", 0) >= MAX_TURNS:
            return {"next": FINISH}

        messages = state["messages"]

        # Deterministic FINISH: if a specialist has already answered the latest
        # user turn, the task is addressed. We detect this by checking whether
        # an AI message appears AFTER the last human message. This avoids
        # relying on the LLM (a reasoning model) to judge "is it done", which
        # is unreliable and risks infinite loops.
        last_human_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].type == "human":
                last_human_idx = i
                break
        has_reply_after = any(
            m.type == "ai" and i > last_human_idx
            for i, m in enumerate(messages)
        ) if last_human_idx >= 0 else False
        if has_reply_after:
            return {"next": FINISH, "active_agent": SUPERVISOR}

        # Phase 1 — no reply yet: ask the LLM which specialist should answer.
        member_list = ", ".join(f'"{m}"' for m in team)
        system = (
            "You are a supervisor routing a user message to one specialist.\n\n"
            f"AVAILABLE SPECIALISTS: {member_list}\n\n"
            "Choose exactly ONE specialist best suited to answer the user's "
            "latest message:\n"
            "  - coder: programming, debugging, algorithms, technical questions\n"
            "  - researcher: comparison, analysis, investigation, factual questions\n"
            "  - writer: writing, drafting, summarizing, creative content, greetings\n"
            "\n"
            "Output ONLY the specialist name. No explanation, no quotes, "
            "no punctuation."
        )
        llm_messages = [{"role": "system", "content": system}] + [
            _to_dict(m) for m in messages
        ]
        decision = _llm_text(llm.invoke(llm_messages)).strip().strip('"').strip()
        # Normalise: map case-insensitive match to canonical tokens.
        lower = decision.lower()
        if lower in [m.lower() for m in team]:
            decision = next(m for m in team if m.lower() == lower)
        else:
            # Unrecognised output → default to writer (a safe generalist).
            decision = "writer"
        return {"next": decision, "active_agent": SUPERVISOR}

    return supervisor


# --------------------------------------------------------------------------- #
# Graph builder
# --------------------------------------------------------------------------- #
def build_team() -> Dict[str, Callable]:
    """Map agent names to their persona prompts."""
    return {
        "coder": (
            "the Coder 👨‍💻, an expert software engineer. "
            "You write clean, correct, well-tested code and explain trade-offs."
        ),
        "researcher": (
            "the Researcher 🔬, a meticulous analyst. "
            "You compare options, weigh evidence and give structured conclusions."
        ),
        "writer": (
            "the Writer ✍️, a skilled communicator. "
            "You draft clear, engaging prose tailored to the audience."
        ),
    }


def build_graph(team: Dict[str, Callable] | None = None,
                checkpointer=None):
    """Compile the multi-agent StateGraph."""
    team = team or build_team()
    member_names = list(team.keys())

    graph = StateGraph(ChatState)
    graph.add_node(SUPERVISOR, _supervisor_node_factory(member_names))
    for name, persona in team.items():
        graph.add_node(name, _make_specialist(name, persona))

    graph.set_entry_point(SUPERVISOR)

    # Supervisor routes to a specialist or ends.
    graph.add_conditional_edges(
        SUPERVISOR,
        lambda state: state["next"],
        {n: n for n in member_names} | {FINISH: END},
    )

    # Every specialist returns to the supervisor for re-evaluation.
    for name in member_names:
        graph.add_edge(name, SUPERVISOR)

    return graph.compile(checkpointer=checkpointer)


# A single in-memory checkpointer shared across requests/threads.
memory = MemorySaver()
app_graph = build_graph(checkpointer=memory)
