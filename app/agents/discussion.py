"""Round-table discussion graph.

Unlike the chat supervisor (which routes ONE user message to a single
specialist), the discussion graph runs a *multi-turn debate* between a
panel of experts that is **recruited for the specific topic**:

    user topic
        ↓
    recruit_panel(topic)  ← coordinator picks 2-3 most relevant roles
        ↓                     from the pool in ``roles.py``
    build_discussion_graph(panel_keys)
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

The roster is no longer hard-coded: asking about "福州美食" recruits a
美食家/历史学家, while "如何用 Rust 写 web 服务器" recruits 工程师/设计师.
Personas are injected only at node-prompt time (the real LLM is
persona-blind), so making the panel dynamic is safe.
"""
from __future__ import annotations

import json
import re
from typing import Annotated, List, Optional

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.agents.graph import _to_dict, _llm_text
from app.agents.roles import ALL_KEYS, get_role_meta, list_roles_for_llm
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


def _is_real_llm(llm) -> bool:
    """True if the LLM is a real model (not the MockLLM fallback)."""
    return getattr(llm, "name", "") != "mock"


# --------------------------------------------------------------------------- #
# Stage 1 — recruitment: the coordinator reads the topic and picks a panel.
# This happens BEFORE the debate graph is compiled, so only the recruited
# specialists become nodes in the graph.
# --------------------------------------------------------------------------- #
def recruit_panel(topic: str, max_size: int = 3) -> List[str]:
    """Return a list of role keys recruited for ``topic``.

    Real LLM: ask the coordinator to pick the most relevant roles.
    MockLLM: keyword-based heuristic so the demo works without an API key.
    """
    llm = get_llm("supervisor")
    if not _is_real_llm(llm):
        return _mock_recruit_panel(topic, max_size)

    system = (
        "You are the coordinator of a round-table discussion. Given a topic, "
        f"select the {max_size} specialist roles whose perspective would be "
        "MOST relevant and diverse for discussing it. Diversity of viewpoint "
        "matters — avoid picking roles that would say the same thing.\n\n"
        f"AVAILABLE ROLES:\n{list_roles_for_llm()}\n\n"
        f"Reply with ONLY a JSON array of exactly {max_size} role keys "
        '(strings), e.g. ["chef","historian","doctor"]. No explanation.'
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Topic to recruit for: {topic}"},
    ]
    try:
        raw = _llm_text(llm.invoke(messages)).strip()
        # Tolerate surrounding prose / code fences by extracting the first
        # JSON array found in the reply.
        match = re.search(r"\[.*?\]", raw, re.S)
        keys = json.loads(match.group(0) if match else raw)
        keys = [str(k).strip().strip('"').strip("'").lower() for k in keys]
        # Keep only valid pool keys, dedupe while preserving order.
        seen, valid = set(), []
        for k in keys:
            if k in ALL_KEYS and k not in seen:
                seen.add(k)
                valid.append(k)
        if valid:
            return valid[:max_size]
    except Exception as exc:  # noqa: BLE001 — fall back to heuristic below
        print(f"[discussion] recruit_panel LLM parse failed ({exc}); using heuristic")

    return _mock_recruit_panel(topic, max_size)


# Keyword → role-key mapping used by the mock fallback and as a safety net
# when the LLM reply is unparseable.
_TOPIC_KEYWORDS = [
    # (role key,      [keywords ...])
    ("chef",            ["美食", "菜", "料理", "烹饪", "口味", "food", "dish", "cuisine", "recipe"]),
    ("historian",       ["历史", "起源", "朝代", "文明", "古代", "history", "origin", "ancient"]),
    ("philosopher",     ["哲学", "意义", "本质", "存在", "道德", "philosophy", "meaning", "existential"]),
    ("scientist",       ["科学", "物理", "化学", "生物", "实验", "science", "physics", "biology"]),
    ("economist",       ["经济", "金融", "市场", "投资", "价格", "economy", "market", "finance", "invest"]),
    ("psychologist",    ["心理", "情绪", "焦虑", "压力", "动机", "psycholog", "emotion", "anxiety", "stress"]),
    ("engineer",        ["代码", "程序", "编程", "软件", "系统", "架构", "code", "program", "software", "rust", "python", "server"]),
    ("lawyer",          ["法律", "法规", "合同", "权利", "犯罪", "law", "legal", "contract", "rights"]),
    ("artist",          ["艺术", "美术", "绘画", "音乐", "设计", "art", "paint", "music"]),
    ("doctor",          ["医学", "健康", "疾病", "症状", "治疗", "医疗", "medical", "health", "disease", "symptom"]),
    ("educator",        ["教育", "学习", "教学", "学校", "学生", "education", "learn", "teach", "school"]),
    ("sociologist",     ["社会", "群体", "文化", "阶层", "社区", "societ", "social", "community", "culture"]),
    ("ethicist",        ["伦理", "对错", "善恶", "应该", "责任", "ethic", "moral"]),
    ("designer",        ["设计", "体验", "界面", "用户", "审美", "design", "ux", "ui", "user experience"]),
    ("entrepreneur",    ["创业", "商业", "公司", "产品", "startup", "business", "product", "venture"]),
    ("environmentalist",["环境", "气候", "污染", "可持续", "生态", "environ", "climate", "sustain", "ecolog"]),
    ("writer",          ["写作", "故事", "小说", "文案", "文字", "writ", "story", "novel", "narrative"]),
    ("strategist",      ["战略", "决策", "规划", "竞争", "取舍", "strateg", "decision", "plan", "competitive"]),
]


def _mock_recruit_panel(topic: str, max_size: int = 3) -> List[str]:
    """Keyword-scored fallback used when there is no real LLM."""
    lowered = topic.lower()
    scored = [
        (key, sum(lowered.count(kw.lower()) for kw in keywords))
        for key, keywords in _TOPIC_KEYWORDS
    ]
    # Descending by score; ties keep pool order (stable sort).
    scored.sort(key=lambda x: -x[1])
    matched = [k for k, s in scored if s > 0]
    # Top up to max_size with the next-best general roles so the debate has
    # enough voices even when only one keyword matched.
    fallback = ["philosopher", "scientist", "writer", "historian", "sociologist"]
    for k in fallback:
        if k not in matched:
            matched.append(k)
        if len(matched) >= max_size:
            break
    return matched[:max_size]


# --------------------------------------------------------------------------- #
# Stage 2 — node factories for the debate graph.
# --------------------------------------------------------------------------- #
def _make_discuss_specialist(name: str, persona: str):
    """A specialist that argues a viewpoint in the debate."""
    llm = get_llm(name)

    def node(state: DiscussionState) -> dict:
        topic = state.get("topic", "")
        # Has any specialist spoken yet? The coordinator never emits a
        # message, so the first specialist sees an empty transcript.
        has_prior = any(isinstance(m, AIMessage) for m in state["messages"])
        if has_prior:
            system = (
                f"You are {persona}. You are taking part in a round-table "
                f"discussion about: \"{topic}\".\n"
                "Other participants have already spoken (see the transcript "
                "below). Build on or respectfully challenge what they said. "
                "Give your professional perspective in 3-5 sentences. Do not "
                "repeat what was already said — add new insight."
            )
        else:
            system = (
                f"You are {persona}. You are OPENING a round-table discussion "
                f"about: \"{topic}\".\n"
                "You are the FIRST speaker — there is no prior discussion yet. "
                "Do NOT refer to anything others have said or pretend a "
                "conversation is already underway. State your own professional "
                "perspective on the topic from scratch, in 3-5 sentences."
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


def _make_coordinator(panel_keys: list[str]):
    """The coordinator picks which specialist speaks each round.

    ``panel_keys`` is the recruited roster (e.g. ``["chef","historian"]``);
    each key is resolved to a friendly Chinese name for the prompt so the
    coordinator can reason about relevance instead of opaque slugs.
    """
    llm = get_llm("supervisor")
    # "key (中文名)" lines, e.g. `chef (美食家)`.
    panel_labels = [
        f'{k} ({get_role_meta(k)["name"]})' for k in panel_keys
    ]

    def node(state: DiscussionState) -> dict:
        round_no = state.get("current_round", 0)
        max_rounds = state.get("max_rounds", 10)

        # All rounds done → go to summary.
        if round_no >= max_rounds:
            return {"next": DISCUSS_FINISH, "active_agent": COORDINATOR}

        # MockLLM has no real understanding — pick by round-robin so the
        # discussion still demonstrates the full flow without an API key.
        if not _is_real_llm(llm):
            pick = panel_keys[round_no % len(panel_keys)]
        else:
            # Real LLM: choose the most relevant specialist for this round.
            member_list = ", ".join(f'"{l}"' for l in panel_labels)
            system = (
                f"You are the coordinator of a round-table discussion about: "
                f"\"{state.get('topic', '')}\".\n"
                f"Round {round_no + 1} of {max_rounds}. "
                f"Given the discussion so far, choose the ONE specialist whose "
                f"perspective would add the most value next.\n"
                f"OPTIONS (use the key before the parenthesis): {member_list}\n"
                "Output ONLY the specialist key. No explanation."
            )
            messages = [{"role": "system", "content": system}] + [
                _to_dict(m) for m in state["messages"]
            ]
            decision = _llm_text(llm.invoke(messages)).strip().strip('"').strip("'").lower()
            # Accept the key if it appears in the reply; fall back to round-robin.
            pick = next((k for k in panel_keys if k.lower() in decision), None)
            if pick is None:
                pick = panel_keys[round_no % len(panel_keys)]

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
        # Build a friendly speaker list using role names from the pool.
        speaker_keys = []
        for m in state["messages"]:
            if isinstance(m, AIMessage) and getattr(m, "name", None) not in (None, COORDINATOR):
                if m.name not in speaker_keys:
                    speaker_keys.append(m.name)
        speaker_names = ", ".join(get_role_meta(k)["name"] for k in speaker_keys)

        # MockLLM: produce a deterministic summary.
        if not _is_real_llm(llm):
            reply = (
                f"📋 讨论总结：围绕「{topic}」，"
                f"{speaker_names or '各位专家'} 经过多轮讨论，"
                "从不同专业视角交换了观点，达成以下共识："
                "应综合各方优势，在可行性与多样性之间取得平衡。"
            )
        else:
            system = (
                f"You are the coordinator. The round-table discussion about "
                f"\"{topic}\" has concluded, with input from: {speaker_names}.\n"
                "Synthesise the key points raised by all participants into a "
                "clear, structured summary. Highlight areas of agreement and "
                "any remaining trade-offs."
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


# --------------------------------------------------------------------------- #
# Stage 3 — compile a debate graph for a recruited panel.
# --------------------------------------------------------------------------- #
def build_discussion_graph(panel_keys: list[str], checkpointer=None):
    """Compile a round-table StateGraph containing ONLY the recruited roles.

    ``panel_keys`` must be valid keys from ``roles.ALL_KEYS`` (e.g.
    ``["chef","historian"]``). The returned compiled graph routes:

        entry → coordinator → specialist ⇄ coordinator → summarizer → END
    """
    if not panel_keys:
        panel_keys = ["philosopher", "scientist", "writer"]

    graph = StateGraph(DiscussionState)
    graph.add_node(COORDINATOR, _make_coordinator(panel_keys))
    for key in panel_keys:
        meta = get_role_meta(key)
        graph.add_node(key, _make_discuss_specialist(key, meta["persona"]))
    graph.add_node(SUMMARIZER, _make_summarizer())

    graph.set_entry_point(COORDINATOR)

    # Coordinator routes to one of the recruited specialists or to the summary.
    graph.add_conditional_edges(
        COORDINATOR,
        lambda state: state["next"],
        {k: k for k in panel_keys} | {DISCUSS_FINISH: SUMMARIZER},
    )
    # Every specialist returns to the coordinator, bumping the round.
    for key in panel_keys:
        graph.add_edge(key, COORDINATOR)
    # Summarizer is the end of the discussion.
    graph.add_edge(SUMMARIZER, END)

    return graph.compile(checkpointer=checkpointer)


# Shared in-memory checkpointer (same store as chat, but threads use a
# `disc_` prefix in the API layer to keep namespaces separate).
from app.agents.graph import memory as _shared_memory

# Cache of compiled graphs keyed by the sorted panel, so identical panels
# reuse one compiled graph instead of rebuilding on every request.
_graph_cache: dict[tuple, object] = {}


def get_discussion_graph(panel_keys: list[str]):
    """Return a compiled discussion graph for ``panel_keys``, cached."""
    cache_key = tuple(sorted(panel_keys))
    graph = _graph_cache.get(cache_key)
    if graph is None:
        graph = build_discussion_graph(panel_keys, checkpointer=_shared_memory)
        _graph_cache[cache_key] = graph
    return graph
