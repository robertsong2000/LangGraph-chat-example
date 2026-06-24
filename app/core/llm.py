"""LLM factory.

Tries ChatOpenAI first (works against OpenAI or any OpenAI-compatible endpoint,
including Zhipu/GLM). If no API key is present and `use_mock_if_no_key` is set,
falls back to a deterministic local MockLLM so the app still works end-to-end.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Optional

from .config import settings


class BaseLLM:
    """Minimal LLM interface used by all agents."""

    name: str = "base"

    def invoke(self, messages: list[dict]) -> str:
        raise NotImplementedError

    # streaming hook — default just yields the full result
    def stream(self, messages: list[dict]) -> Iterable[str]:
        yield self.invoke(messages)


def _build_openai_llm(temperature: Optional[float] = None) -> Any:
    """Build a ChatOpenAI-compatible LLM."""
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": settings.model_name,
        "temperature": settings.temperature if temperature is None else temperature,
    }
    # If model_name looks like a provider-prefixed name (e.g. "openai/gpt-4o-mini")
    # strip the provider prefix for ChatOpenAI, which only wants the bare model.
    if "/" in kwargs["model"]:
        kwargs["model"] = kwargs["model"].split("/", 1)[1]

    if settings.api_key:
        kwargs["api_key"] = settings.api_key
    if settings.api_base:
        kwargs["base_url"] = settings.api_base
    return ChatOpenAI(**kwargs)


# --------------------------------------------------------------------------- #
# Mock LLM — keeps the app fully functional without an API key.
# --------------------------------------------------------------------------- #
class MockLLM(BaseLLM):
    """Rule-based fake model used when no API key is configured.

    It inspects the last user message and produces a context-aware canned
    response, so the supervisor routing and agent switching still demonstrate
    meaningful behaviour.
    """

    name = "mock"

    _CODE_KEYWORDS = (
        "code", "function", "bug", "python", "javascript", "rust", "sql",
        "algorithm", "compile", "error", "stack trace", "refactor", "api",
    )
    _RESEARCH_KEYWORDS = (
        "research", "compare", "search", "find out", "study", "paper",
        "difference between", "what is", "explain", "investigate", "analysis",
    )
    _WRITE_KEYWORDS = (
        "write", "draft", "essay", "email", "blog", "article", "story",
        "summary", "summarize", "translate", "poem", "tweet",
    )

    def __init__(self, agent_name: str = "supervisor"):
        self.agent_name = agent_name

    def invoke(self, messages: list[dict]) -> str:
        role = self.agent_name
        if role == "supervisor":
            return self._route(messages)
        text = self._last_human(messages)
        return self._specialist(text, role)

    def stream(self, messages: list[dict]):
        full = self.invoke(messages)
        # stream word by word for a nicer UX
        for tok in full.split():
            yield tok + " "

    # -- routing logic ----------------------------------------------------- #
    def _last_human(self, messages: list[dict]) -> str:
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                return str(m["content"]).lower()
        return ""

    def _route(self, messages: list[dict]) -> str:
        # If a specialist already answered the latest user turn, finish.
        # We detect this by checking whether the most recent message is an
        # assistant reply that came AFTER the latest user message.
        for m in reversed(messages):
            if m.get("role") == "user":
                break  # latest user msg found, no assistant after it
            if m.get("role") == "assistant":
                return "finish"  # a specialist has already replied → done

        text = self._last_human(messages)
        scores = {
            "coder": sum(text.count(k) for k in self._CODE_KEYWORDS),
            "researcher": sum(text.count(k) for k in self._RESEARCH_KEYWORDS),
            "writer": sum(text.count(k) for k in self._WRITE_KEYWORDS),
        }
        best = max(scores, key=scores.get) if any(scores.values()) else "writer"
        return best

    def _specialist(self, text: str, role: str) -> str:
        persona = {
            "coder": ("👨‍💻 Coder",
             "Here's an implementation outline for your request:\n"
             "  1. Define the data model / interfaces first.\n"
             "  2. Implement the core function with clear error handling.\n"
             "  3. Add a small test to lock in the behaviour.\n"
             "Want me to turn this into a full code sample?"),
            "researcher": ("🔬 Researcher",
             "Based on a structured comparison:\n"
             "  • Option A — strong on performance, weaker on tooling.\n"
             "  • Option B — mature ecosystem, slower iteration.\n"
             "  • Option C — best for rapid prototyping.\n"
             "I'd recommend Option A for production workloads."),
            "writer": ("✍️ Writer",
             "Here's a polished draft for you:\n\n"
             "> Your idea, expressed clearly and with a confident tone.\n\n"
             "I can tighten the phrasing, adjust the length, or change the "
             "register (formal / casual / persuasive) on request."),
        }.get(role, ("Assistant", "Here's my take on that."))
        name, body = persona
        return f"{name}: {body}"


# --------------------------------------------------------------------------- #
# Public factory
# --------------------------------------------------------------------------- #
def get_llm(agent_name: str = "supervisor", temperature: Optional[float] = None):
    """Return an LLM instance for the given agent.

    Falls back to MockLLM when no API key is configured.
    """
    if settings.can_use_real_llm:
        try:
            return _build_openai_llm(temperature)
        except Exception as exc:  # pragma: no cover - dependency issues
            print(f"[llm] Failed to build real LLM ({exc}); using mock.")
            return MockLLM(agent_name)
    return MockLLM(agent_name)
