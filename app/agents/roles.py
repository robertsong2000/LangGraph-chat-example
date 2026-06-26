"""Role pool for the round-table discussion.

A single source of truth for the specialist personas available to the
discussion coordinator.  Each entry carries four fields:

    key     stable identifier used as the graph-node name / SSE `agent`
    name    human-friendly Chinese label (also surfaced to the frontend)
    emoji   avatar glyph
    persona English persona description injected into the LLM system prompt

The coordinator (``recruit_panel``) picks a small subset of these for any
given topic, so asking about "福州美食" recruits a 美食家/历史学家 instead
of a hard-coded engineer.
"""

from __future__ import annotations

from typing import Dict, List

# (key, Chinese name, emoji, English persona injected into the LLM prompt)
_ROLES: List[tuple] = [
    ("historian",       "历史学家", "📜", "a historian who traces origins, chronology and the cultural forces that shaped things"),
    ("philosopher",     "哲学家",   "🦉", "a philosopher who interrogates essence, meaning and first principles"),
    ("scientist",       "科学家",   "🔬", "a scientist who reasons from evidence, mechanism and falsifiable claims"),
    ("chef",            "美食家",   "🍳", "a food critic and chef who judges flavour, technique and culinary tradition"),
    ("economist",       "经济学家", "💰", "an economist who weighs cost, incentive, scarcity and trade-offs"),
    ("psychologist",    "心理学家", "🧠", "a psychologist who explains motivation, emotion and behaviour"),
    ("engineer",        "工程师",   "⚙️", "a software engineer focused on implementation, correctness and engineering trade-offs"),
    ("lawyer",          "法学家",   "⚖️", "a legal scholar attentive to rules, rights, precedent and boundaries"),
    ("artist",          "艺术家",   "🎨", "an artist who values aesthetics, expression and craft"),
    ("doctor",          "医学家",   "🩺", "a medical expert concerned with health, physiology and well-being"),
    ("educator",        "教育家",   "📚", "an educator who thinks about learning, pedagogy and growth"),
    ("sociologist",     "社会学家", "👥", "a sociologist who analyses groups, institutions and social structure"),
    ("ethicist",        "伦理学家", "🧭", "an ethicist who weighs right and wrong, values and moral trade-offs"),
    ("designer",        "设计师",   "📐", "a designer focused on user experience, form and clarity"),
    ("entrepreneur",    "创业者",   "🚀", "an entrepreneur who spots opportunity and obsesses over execution"),
    ("environmentalist","环保学者", "🌱", "an environmentalist who considers ecology, sustainability and long-term impact"),
    ("writer",          "作家",     "✍️", "a writer who values narrative, empathy and precise language"),
    ("strategist",      "战略顾问", "♟️", "a strategist who frames trade-offs and long-term paths to a goal"),
]

# Lookup tables derived from the list above.
BY_KEY: Dict[str, dict] = {r[0]: {"key": r[0], "name": r[1], "emoji": r[2], "persona": r[3]} for r in _ROLES}
ALL_KEYS: List[str] = [r[0] for r in _ROLES]


def get_role_meta(key: str) -> dict:
    """Return ``{key, name, emoji, persona}`` for a role, or a generic
    fallback if ``key`` is not in the pool (shouldn't happen, but keeps
    rendering safe)."""
    return BY_KEY.get(
        key,
        {"key": key, "name": key, "emoji": "🎯", "persona": f"an expert on {key}"},
    )


def list_roles_for_llm() -> str:
    """Render the pool as a numbered list the coordinator can pick from."""
    return "\n".join(f"{i}. {r[0]} ({r[1]}): {r[3]}" for i, r in enumerate(_ROLES, 1))


def list_roles_for_client() -> List[dict]:
    """Return the lightweight ``[{key,name,emoji}]`` list for the SSE
    ``panel`` event / frontend banner."""
    return [{"key": r[0], "name": r[1], "emoji": r[2]} for r in _ROLES]
