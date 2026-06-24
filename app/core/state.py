"""Shared graph state and message helpers."""
from __future__ import annotations

from typing import Annotated, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ChatState(TypedDict):
    """The state object that flows through every node in the graph.

    - `messages` is automatically appended to (via the `add_messages` reducer),
      so each node only needs to return the *new* messages it produced.
    - `next` holds the supervisor's routing decision (name of the next agent).
    - `active_agent` tracks which specialist produced the latest reply, used
      by the API layer for display.
    - `turn_count` bounds the number of agent hops in a single user turn.
    """

    messages: Annotated[List[BaseMessage], add_messages]
    next: str
    active_agent: Optional[str]
    turn_count: int


def last_human_text(state: ChatState) -> str:
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage) and m.content:
            return str(m.content)
    return ""


def last_ai_text(state: ChatState) -> str:
    for m in reversed(state["messages"]):
        if isinstance(m, AIMessage) and m.content:
            return str(m.content)
    return ""
