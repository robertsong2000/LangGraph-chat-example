"""Round-table discussion graph.

Unlike the chat supervisor (which routes ONE user message to a single
specialist), the discussion graph runs a *multi-turn debate*:

    user topic + N rounds
        ↓
    ┌─ coordinator ────────────────────────────────────┐
    │  picks the best specialist for the current round  │  round 0..N-1
    └───────────┬──────────────────────────────────────┘
                ↓
    ┌─ specialist ─────────────────────────────────────┐
    │  contributes a viewpoint on the topic             │
    └───────────┬──────────────────────────────────────┘
                ↓  back to coordinator
       round < N → pick next specialist
       round == N → summarizer
                         ↓
                ┌─ summarizer ─────────────────────────┐
                │  coordinator synthesises all speakers │
                └───────────────────────────────────────┘
                         ↓
                       END

Reuses the same LLM factory, personas and checkpointer as the chat graph,
so there is a single source of truth for agent behaviour.
"""
from __future__ import annotations

from typing import Annotated, List, Optional

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.agents.graph import build_team, _to_dict, _llm_text
from app.core.llm import get_llm


COORDINATOR = "coordinator"
SUMMARIZER = "summarizer"
DISCUSS_FINISH = "summarize"


class DiscussionState(TypedDict):
    """State for the round-table discussion.

    - `messages`: full debate transcript (appended via add_messages reducer).
    - `topic`: the subject under discussion.
    - `max_rounds`: target number of speaking turns.
    - `current_round`: how many specialist turns have happened so far.
    - `next`: coordinator's pick for this round, or "summarize".
    - `active_agent`: who spoke last (for the API layer).
    """

    messages: Annotated[List[BaseMessage], add_messages]
    topic: str
    max_rounds: int
    current_round: int
    next: str
    active_agent: Optional[str]


def _make_discuss_specialist(name: str, persona: str):
    """A specialist that argues a viewpoint in the debate."""
    llm = get_llm(name)

    def node(state: DiscussionState) -> dict:
        topic = state.get("topic", "")
        system = (
            f"You are {persona}. You are taking part in a round-table discussion "
            f"about: \"{topic}\".\n"
            "Build on or respectfully challenge what others have said so far. "
            "Give your professional perspective in 3-5 sentences. Do not repeat "
            "what was already said — add new insight."
        )
        messages = [{"role": "system", "content": system}] + [
            _to_dict(m) for m in state["messages"]
        ]
        reply = _llm_text(llm.invoke(messages))
        return {
            "messages": [AIMessage(content=reply, name=name)],
            "active_agent": name,
            "next": COORDINATOR,
        }

    node.__name__ = name
    return node


def _make_coordinator(team: list[str]):
    """The coordinator picks which specialist speaks each round."""
    llm = get_llm("supervisor")

    def node(state: DiscussionState) -> dict:
        round_no = state.get("current_round", 0)
        max_rounds = state.get("max_rounds", 10)

        # All rounds done → go to summary.
        if round_no >= max_rounds:
            return {"next": DISCUSS_FINISH, "active_agent": COORDINATOR}

        # MockLLM has no real understanding — pick by round-robin so the
        # discussion still demonstrates the full flow without an API key.
        if not _is_real_llm(llm):
            pick = team[round_no % len(team)]
        else:
            # Real LLM: choose the most relevant specialist for this round.
            member_list = ", ".join(f'"{m}"' for m in team)
            system = (
                f"You are the coordinator of a round-table discussion about: "
                f"\"{state.get('topic', '')}\".\n"
                f"Round {round_no + 1} of {max_rounds}. "
                f"Given the discussion so far, choose the ONE specialist whose "
                f"perspective would add the most value next.\n"
                f"OPTIONS: {member_list}\n"
                "Output ONLY the specialist name. No explanation."
            )
            messages = [{"role": "system", "content": system}] + [
                _to_dict(m) for m in state["messages"]
            ]
            decision = _llm_text(llm.invoke(messages)).strip().strip('"').strip().lower()
            pick = next((m for m in team if m.lower() == decision), team[0])

        # Increment the round counter so the next pass knows how far we are.
        return {
            "next": pick,
            "active_agent": COORDINATOR,
            "current_round": round_no + 1,
        }

    node.__name__ = COORDINATOR
    return node


def _make_summarizer():
    """The coordinator synthesises the whole debate at the end."""
    llm = get_llm("supervisor")

    def node(state: DiscussionState) -> dict:
        topic = state.get("topic", "")
        # MockLLM: produce a deterministic summary.
        if not _is_real_llm(llm):
            speakers = sorted({getattr(m, "name", "?") for m in state["messages"]
                               if isinstance(m, AIMessage)})
            reply = (
                f"📋 讨论总结：围绕「{topic}」，"
                f"{', '.join(speakers)} 等专家经过多轮讨论，"
                "从技术、研究和表达等角度交换了观点，达成以下共识："
                "应综合各方优势，在可行性与表达力之间取得平衡。"
            )
        else:
            system = (
                f"You are the coordinator. The round-table discussion about "
                f"\"{topic}\" has concluded. Synthesise the key points raised "
                f"by all participants into a clear, structured summary. "
                f"Highlight areas of agreement and any remaining trade-offs."
            )
            messages = [{"role": "system", "content": system}] + [
                _to_dict(m) for m in state["messages"]
            ]
            reply = _llm_text(llm.invoke(messages))
        return {
            "messages": [AIMessage(content=reply, name=COORDINATOR)],
            "active_agent": COORDINATOR,
            "next": END,
        }

    node.__name__ = SUMMARIZER
    return node


def _is_real_llm(llm) -> bool:
    """True if the LLM is a real model (not the MockLLM fallback)."""
    return getattr(llm, "name", "") != "mock"


def build_discussion_graph(checkpointer=None):
    """Compile the round-table discussion StateGraph."""
    team_map = build_team()
    member_names = list(team_map.keys())

    graph = StateGraph(DiscussionState)
    graph.add_node(COORDINATOR, _make_coordinator(member_names))
    for name, persona in team_map.items():
        graph.add_node(name, _make_discuss_specialist(name, persona))
    graph.add_node(SUMMARIZER, _make_summarizer())

    graph.set_entry_point(COORDINATOR)

    # Coordinator routes to a specialist or to the summarizer.
    graph.add_conditional_edges(
        COORDINATOR,
        lambda state: state["next"],
        {n: n for n in member_names} | {DISCUSS_FINISH: SUMMARIZER},
    )
    # Every specialist returns to the coordinator, bumping the round.
    for name in member_names:
        graph.add_edge(name, COORDINATOR)
    # Summarizer is the end of the discussion.
    graph.add_edge(SUMMARIZER, END)

    compiled = graph.compile(checkpointer=checkpointer)

    # Wrap specialist nodes to increment the round counter on each pass.
    return compiled


# Shared in-memory checkpointer (same store as chat, but threads use a
# `disc_` prefix in the API layer to keep namespaces separate).
from app.agents.graph import memory as _shared_memory

discussion_graph = build_discussion_graph(checkpointer=_shared_memory)
