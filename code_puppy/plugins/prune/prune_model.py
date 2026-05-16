"""Data model and pydantic-ai introspection for /prune.

Kept separate from prune_menu.py so the TUI file stays focused on
prompt_toolkit wiring. Everything here is pure data-shape + parsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Set

# ── palette (matches pop_interactive's ipop_menu) ──────────────────────────

C_CURSOR = "bold fg:ansicyan"
C_USER = "fg:ansigreen"
C_ASSISTANT = "fg:ansiblue"
C_TOOL = "fg:ansiyellow"
C_WRITE = "fg:ansimagenta"
C_SHELL = "fg:ansired"
C_DIM = "fg:ansibrightblack"
C_HEADER = "dim cyan"
C_FOOTER_OK = "fg:ansigreen"
C_FOOTER_PREVIEW = "fg:ansiyellow"
C_CHECKED = "bold fg:ansired"
C_IMPLIED = "fg:ansibrightblack"
C_SYSTEM = "bold fg:ansicyan"

# ── tool-name → side-effect classification ─────────────────────────────────

_WRITE_TOOLS = {
    "edit_file",
    "create_file",
    "replace_in_file",
    "delete_snippet",
    "delete_file",
}
_SHELL_TOOLS = {"agent_run_shell_command"}
_BROWSER_PREFIX = "browser_"
_TERMINAL_PREFIX = "terminal_"

SIDE_EFFECT_ICONS = {"⚡", "✎", "🌐", "▶"}


def classify_tool(tool_name: str) -> str:
    """Return a short single-char icon hinting at the side-effect kind."""
    if tool_name in _WRITE_TOOLS:
        return "✎"
    if tool_name in _SHELL_TOOLS:
        return "⚡"
    if tool_name.startswith(_BROWSER_PREFIX):
        return "🌐"
    if tool_name.startswith(_TERMINAL_PREFIX):
        return "▶"
    return "·"


# ── data classes ───────────────────────────────────────────────────────────


@dataclass
class ToolCallInfo:
    """One tool call within a message."""

    tool_call_id: str
    name: str
    args_preview: str  # short single-line summary, for the list pane
    full_args: dict = field(default_factory=dict)  # full args, for detail pane
    icon: str = "·"
    has_return: bool = False


@dataclass
class MessageEntry:
    """One displayable message in the prune menu."""

    history_index: int
    role: str  # "system" | "user" | "assistant" | "tool-return" | "unknown"
    preview: str
    full_text: str
    tool_calls: List[ToolCallInfo] = field(default_factory=list)
    icon: str = " "
    is_pure_tool_return: bool = False
    tool_return_ids: List[str] = field(default_factory=list)
    # Thinking / chain-of-thought content from the model. These are
    # ``ThinkingPart`` instances that live inside a ``ModelResponse``
    # alongside the regular ``TextPart`` reply. They're stored separately
    # so the preview line stays focused on the user-facing answer while
    # the detail pane can still surface what the model was thinking.
    thinking_segments: List[str] = field(default_factory=list)
    # Context-window analysis. Filled in by annotate_context_window().
    # Both default to None when no estimator is available.
    tokens: Optional[int] = None
    in_context: Optional[bool] = None

    @property
    def role_color(self) -> str:
        if self.role == "system":
            return C_SYSTEM
        if self.role == "user":
            return C_USER
        if self.role == "assistant":
            return C_ASSISTANT
        if self.role == "tool-return":
            return C_TOOL
        return C_DIM


@dataclass
class Row:
    """One visible row in the TUI tree.

    Either a message header or an indented tool-call child.
    """

    kind: str  # "message" | "tool_call"
    message_idx: int  # index into MessageEntry list (not history_index)
    tool_call_id: Optional[str] = None  # only for tool_call rows


@dataclass
class PruneSelection:
    """Result of the menu — what the caller should remove.

    history_indices_to_drop: messages to remove entirely (along with all
        their tool calls and any ToolReturnParts that match them).
    tool_call_ids_to_drop: individual tool call IDs to surgically remove
        (their matching ToolReturnParts go too).
    """

    history_indices_to_drop: Set[int] = field(default_factory=set)
    tool_call_ids_to_drop: Set[str] = field(default_factory=set)

    @property
    def is_empty(self) -> bool:
        return not self.history_indices_to_drop and not self.tool_call_ids_to_drop


@dataclass
class ContextBudget:
    """Snapshot of context-window math at menu open time.

    ``used_tokens`` represents what would actually be sent on the next
    turn — i.e. the sum of in-context message tokens, NOT every message
    in history. Messages older than the truncation point are silently
    dropped by the model and accounted for separately in
    ``out_of_context_tokens`` so the budget percentage never exceeds 100%.

    All fields default to None when the agent or its estimator is
    unavailable — the menu degrades gracefully when this happens.
    """

    used_tokens: Optional[int] = None  # in-context message tokens (what fits)
    overhead_tokens: Optional[int] = None  # system prompt + tool defs
    context_length: Optional[int] = None  # model's max context size
    out_of_context_tokens: int = 0  # tokens from messages that won't be sent
    out_of_context_messages: int = 0  # count of those messages
    available: bool = False  # True if the rest of the fields are meaningful

    @property
    def total_used(self) -> Optional[int]:
        if self.used_tokens is None or self.overhead_tokens is None:
            return None
        return self.used_tokens + self.overhead_tokens

    @property
    def percent_used(self) -> Optional[float]:
        if not self.available or not self.context_length:
            return None
        total = self.total_used or 0
        return 100.0 * total / self.context_length


# ── string helpers ─────────────────────────────────────────────────────────


def short_str(value: Any, limit: int = 80) -> str:
    if value is None:
        return ""
    s = str(value).replace("\n", " ").replace("\r", " ").strip()
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def short_args(args: dict, limit: int = 80) -> str:
    if not args:
        return ""
    items: List[str] = []
    for k, v in list(args.items())[:4]:
        vs = short_str(v, limit=20)
        items.append(f"{k}={vs}")
    joined = ", ".join(items)
    if len(joined) > limit:
        return joined[: limit - 1] + "…"
    return joined


def _aggregate_icon(tool_calls: List[ToolCallInfo]) -> str:
    kinds = {tc.icon for tc in tool_calls}
    for kind in ("⚡", "✎", "🌐", "▶", "·"):
        if kind in kinds:
            return kind
    return " "


# ── pydantic-ai introspection ──────────────────────────────────────────────


def _extract_message(message: Any) -> Optional[MessageEntry]:
    """Inspect a pydantic-ai message and produce a MessageEntry, or None
    if it's the system prompt / something we shouldn't show."""
    try:
        from pydantic_ai.messages import (
            ModelRequest,
            ModelResponse,
            SystemPromptPart,
            TextPart,
            ToolCallPart,
            ToolReturnPart,
            UserPromptPart,
        )

        try:
            from pydantic_ai.messages import ThinkingPart  # type: ignore
        except Exception:  # pragma: no cover — older pydantic-ai
            ThinkingPart = None  # type: ignore[assignment]

        try:
            from pydantic_ai.messages import RetryPromptPart  # type: ignore
        except Exception:  # pragma: no cover — older pydantic-ai
            RetryPromptPart = None  # type: ignore[assignment]
    except Exception:
        return MessageEntry(
            history_index=-1,
            role="unknown",
            preview=short_str(message),
            full_text=str(message),
        )

    if isinstance(message, ModelRequest):
        parts = getattr(message, "parts", []) or []
        text_fragments: List[str] = []
        user_text_fragments: List[str] = []
        saw_user = False
        saw_tool_return = False
        saw_system = False
        tool_return_ids: List[str] = []

        for part in parts:
            if isinstance(part, SystemPromptPart):
                saw_system = True
                text_fragments.append(f"[system] {part.content}")
            elif isinstance(part, UserPromptPart):
                saw_user = True
                content = part.content
                if isinstance(content, list):
                    user_text = (
                        " ".join(str(item) for item in content if isinstance(item, str))
                        or "<non-text content>"
                    )
                else:
                    user_text = str(content)
                user_text_fragments.append(user_text)
                text_fragments.append(user_text)
            elif isinstance(part, ToolReturnPart):
                saw_tool_return = True
                tcid = getattr(part, "tool_call_id", None)
                if tcid:
                    tool_return_ids.append(tcid)
                # Keep the FULL content here so the detail pane can show
                # everything. The list pane builds its own short preview.
                content_str = str(part.content) if part.content is not None else ""
                text_fragments.append(f"[tool-return: {part.tool_name}] {content_str}")
            elif RetryPromptPart is not None and isinstance(part, RetryPromptPart):
                # pydantic-ai emits a RetryPromptPart when the model's tool
                # call args fail validation — it's a tool-side response
                # (carries tool_call_id + tool_name) telling the model
                # "your args were wrong, here's the validation error".
                # Treat it like ToolReturnPart so the parent tool call
                # registers as having a return, and surface it with a
                # distinctive label so users can spot wasted retry turns.
                saw_tool_return = True
                tcid = getattr(part, "tool_call_id", None)
                if tcid:
                    tool_return_ids.append(tcid)
                content_str = str(part.content) if part.content is not None else ""
                tool_name = getattr(part, "tool_name", "?")
                text_fragments.append(f"[retry-prompt: {tool_name}] {content_str}")

        if saw_system and not (saw_user or saw_tool_return):
            return None  # system-only prompt — never show, never prunable

        # Role precedence: system > user > tool-return. pydantic-ai bundles
        # the system prompt with the first user message into a single
        # ModelRequest, so we need to call out that bundle as "system" — it
        # is always in context and must never be toggled.
        if saw_system:
            role = "system"
        elif saw_user:
            role = "user"
        elif saw_tool_return:
            role = "tool-return"
        else:
            role = "unknown"

        text = "\n".join(text_fragments).strip() or "<empty request>"
        # When system content is bundled with user content, prefer the
        # user content for the preview line — that's what a human wants
        # to scan when triaging an old turn.
        if saw_system and user_text_fragments:
            preview_source = "\n".join(user_text_fragments)
        else:
            preview_source = text
        return MessageEntry(
            history_index=-1,
            role=role,
            preview=short_str(preview_source, limit=80),
            full_text=text,
            tool_calls=[],
            icon=" ",
            is_pure_tool_return=(role == "tool-return"),
            tool_return_ids=tool_return_ids,
        )

    if isinstance(message, ModelResponse):
        parts = getattr(message, "parts", []) or []
        text_fragments: List[str] = []
        thinking_segments: List[str] = []
        tool_calls: List[ToolCallInfo] = []
        for part in parts:
            if isinstance(part, TextPart):
                text_fragments.append(str(part.content))
            elif ThinkingPart is not None and isinstance(part, ThinkingPart):
                # Keep thinking content out of the preview line — it would
                # bury the user-facing answer in chain-of-thought noise.
                content = getattr(part, "content", None)
                if content:
                    thinking_segments.append(str(content))
            elif isinstance(part, ToolCallPart):
                try:
                    args_dict = part.args_as_dict()
                except Exception:
                    args_dict = {}
                tool_calls.append(
                    ToolCallInfo(
                        tool_call_id=getattr(part, "tool_call_id", "") or "",
                        name=part.tool_name,
                        args_preview=short_args(args_dict),
                        full_args=args_dict if isinstance(args_dict, dict) else {},
                        icon=classify_tool(part.tool_name),
                    )
                )

        text = "\n".join(text_fragments).strip()
        if not text and tool_calls:
            text = f"<{len(tool_calls)} tool call(s)>"
        elif not text:
            text = "<empty response>"

        # Compose the detail-pane body: response text first (what humans
        # care about), thinking content below in a clearly fenced section.
        if thinking_segments:
            thinking_block = "\n".join(thinking_segments).strip()
            full_text = f"{text}\n\n[thinking]\n{thinking_block}"
        else:
            full_text = text

        # Icon priority: tool-call kind wins (it tells the user what the
        # turn DID), thinking is the fallback so chain-of-thought-only
        # turns still get a visual marker in the list pane.
        if tool_calls:
            icon = _aggregate_icon(tool_calls)
        elif thinking_segments:
            icon = "🧠"
        else:
            icon = " "

        return MessageEntry(
            history_index=-1,
            role="assistant",
            preview=short_str(text, limit=80),
            full_text=full_text,
            tool_calls=tool_calls,
            icon=icon,
            thinking_segments=thinking_segments,
        )

    return MessageEntry(
        history_index=-1,
        role="unknown",
        preview=short_str(message),
        full_text=str(message),
    )


def _make_synthetic_system_entry(agent: Any) -> Optional[MessageEntry]:
    """Build a virtual ``system`` entry from the agent's instructions.

    Code Puppy sends the system prompt to pydantic-ai via the ``instructions``
    field — it never appears as a ``SystemPromptPart`` in message history.
    Without this helper the prune menu would render only user / assistant
    rows and leave the always-in-context system prompt invisible.

    The synthetic entry uses ``history_index = -1`` as a sentinel so it can
    never collide with a real history index and the prune logic skips it
    when computing drop targets. ``tokens`` stays ``None`` because the
    system prompt is already accounted for in the ``overhead`` calculation;
    counting it again would double-bill the budget.
    """
    if agent is None:
        return None
    try:
        system_prompt = agent.get_full_system_prompt()
    except Exception:
        return None
    if not system_prompt:
        return None
    text = str(system_prompt)
    return MessageEntry(
        history_index=-1,
        role="system",
        preview=short_str(text, limit=80),
        full_text=text,
        tool_calls=[],
        icon=" ",
        is_pure_tool_return=False,
        tool_return_ids=[],
        in_context=True,
    )


def build_message_entries(
    raw_history: List[Any], agent: Any = None
) -> List[MessageEntry]:
    """Turn pydantic-ai history into a list of MessageEntry, preserving order.

    Pure-system messages in raw history are filtered out (we synthesize
    our own system row from the agent's instructions instead).
    Tool-return-only messages stay in the list but are flagged so the menu
    can hide them from the top level and surface them via the parent tool
    calls instead.

    When ``agent`` is supplied and no message in ``raw_history`` already
    carries the system role, a virtual system entry is prepended so the
    user can see what's always in context.
    """
    return_ids: Set[str] = set()
    try:
        from pydantic_ai.messages import ModelRequest, ToolReturnPart

        try:
            from pydantic_ai.messages import RetryPromptPart  # type: ignore
        except Exception:  # pragma: no cover — older pydantic-ai
            RetryPromptPart = None  # type: ignore[assignment]

        # Both ToolReturnPart and RetryPromptPart count as "the tool side
        # responded" — they tie back to a parent ToolCallPart via
        # ``tool_call_id`` and mean the call has a matching reply.
        tool_reply_kinds: tuple = (ToolReturnPart,)
        if RetryPromptPart is not None:
            tool_reply_kinds = (ToolReturnPart, RetryPromptPart)

        for msg in raw_history:
            if isinstance(msg, ModelRequest):
                for part in getattr(msg, "parts", []) or []:
                    if isinstance(part, tool_reply_kinds):
                        tcid = getattr(part, "tool_call_id", None)
                        if tcid:
                            return_ids.add(tcid)
    except Exception:
        pass

    entries: List[MessageEntry] = []
    for hist_idx, msg in enumerate(raw_history):
        entry = _extract_message(msg)
        if entry is None:
            continue
        entry.history_index = hist_idx
        for tc in entry.tool_calls:
            tc.has_return = tc.tool_call_id in return_ids
        entries.append(entry)

    # If no real entry advertised role="system" (i.e. pydantic-ai isn't
    # storing a SystemPromptPart for this model), inject the agent's
    # instructions as a synthetic system row so it's always visible.
    if not any(e.role == "system" for e in entries):
        synthetic = _make_synthetic_system_entry(agent)
        if synthetic is not None:
            entries.insert(0, synthetic)

    return entries


def annotate_context_window(
    entries: List[MessageEntry],
    raw_history: List[Any],
    agent: Any,
) -> ContextBudget:
    """Mutate `entries` to set tokens + in_context, and return the budget.

    Walks the entries newest → oldest, accumulating per-message token
    estimates against ``context_length - overhead``. Each entry that fits
    inside the remaining budget is marked in_context=True; once we blow
    past the budget every older entry gets in_context=False.

    Fails open: if the agent doesn't expose the expected helpers, all
    entries get tokens=None / in_context=None and the returned budget
    reports available=False.
    """
    budget = ContextBudget()

    estimate = getattr(agent, "estimate_tokens_for_message", None)
    if not callable(estimate):
        return budget

    try:
        context_length = int(agent._get_model_context_length())
    except Exception:
        context_length = 0

    try:
        overhead = int(agent._estimate_context_overhead())
    except Exception:
        overhead = 0

    # Map history_index -> raw message so we can hand the original object
    # back to the estimator (entries don't carry the raw message).
    raw_by_idx = {i: msg for i, msg in enumerate(raw_history)}

    # Per-entry token count
    for entry in entries:
        raw = raw_by_idx.get(entry.history_index)
        if raw is None:
            entry.tokens = None
            continue
        try:
            entry.tokens = max(0, int(estimate(raw)))
        except Exception:
            entry.tokens = None
            continue

    # System messages (e.g. a system+user bundle at history[0]) are sent
    # on every turn — always in context. Reserve their tokens upfront so
    # the remaining budget is what non-system messages actually compete
    # for in the contiguous-tail walk below.
    system_tokens = 0
    for entry in entries:
        if entry.role == "system" and entry.tokens is not None:
            entry.in_context = True
            system_tokens += entry.tokens

    # Walk newest → oldest, marking in_context until the budget runs out.
    # A real LLM context window is a CONTIGUOUS tail: once we hit a message
    # that doesn't fit, every older message is also out, regardless of size.
    # Without the `overflowed` latch, small older messages would slip in
    # behind big ones that didn't fit, which doesn't match how truncation
    # actually works.
    available_budget = max(0, context_length - overhead - system_tokens)
    non_system_cumulative = 0
    out_of_context_total = 0
    out_of_context_count = 0
    overflowed = False
    for entry in reversed(entries):
        if entry.role == "system":
            continue  # already marked in_context=True above
        if entry.tokens is None or context_length <= 0:
            entry.in_context = None
            continue
        if not overflowed and non_system_cumulative + entry.tokens <= available_budget:
            entry.in_context = True
            non_system_cumulative += entry.tokens
        else:
            entry.in_context = False
            overflowed = True
            out_of_context_total += entry.tokens
            out_of_context_count += 1

    in_context_total = system_tokens + non_system_cumulative

    # ``used_tokens`` is what would actually be sent next turn, NOT the
    # full conversation total. Without this, sessions that overflow show
    # nonsense like "139% used" — the LLM silently drops older messages,
    # so they don't really count against the budget.
    budget.used_tokens = in_context_total
    budget.overhead_tokens = overhead
    budget.context_length = context_length if context_length > 0 else None
    budget.out_of_context_tokens = out_of_context_total
    budget.out_of_context_messages = out_of_context_count
    budget.available = context_length > 0
    return budget


__all__ = [
    "C_ASSISTANT",
    "C_CHECKED",
    "C_CURSOR",
    "C_DIM",
    "C_FOOTER_OK",
    "C_FOOTER_PREVIEW",
    "C_HEADER",
    "C_IMPLIED",
    "C_SHELL",
    "C_SYSTEM",
    "C_TOOL",
    "C_USER",
    "C_WRITE",
    "ContextBudget",
    "MessageEntry",
    "PruneSelection",
    "Row",
    "SIDE_EFFECT_ICONS",
    "ToolCallInfo",
    "annotate_context_window",
    "build_message_entries",
    "classify_tool",
    "short_args",
    "short_str",
]
