"""Data model and pydantic-ai introspection for /prune.

Kept separate from prune_menu.py so the TUI file stays focused on
prompt_toolkit wiring. Everything here is pure data-shape + parsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Set

# ── palette ────────────────────────────────────────────────────────────────
# Style strings for prompt_toolkit's formatted-text tuples. Centralised here
# so prune_menu.py and prune_render.py reference one source of truth.

C_CURSOR = "bold fg:ansicyan"
C_USER = "fg:ansigreen"
C_ASSISTANT = "fg:ansiblue"
C_TOOL = "fg:ansiyellow"
C_WRITE = "fg:ansimagenta"
C_SHELL = "fg:ansired"
C_DIM = "fg:ansibrightblack"
C_HEADER = "dim cyan"
C_FOOTER_OK = "fg:ansigreen"
C_FOOTER_WARN = "fg:ansiyellow"
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
    def is_pure_tool_return(self) -> bool:
        """True for messages whose only content is tool returns.

        These tag along with their parent tool-calling message and are
        never shown as standalone rows in the menu.
        """
        return self.role == "tool-return"

    @property
    def is_locked(self) -> bool:
        """True when this entry carries a ``SystemPromptPart`` and so
        must never be pruned.

        ``build_message_entries`` tags any request containing a
        ``SystemPromptPart`` with ``role == "system"``, which covers
        both a standalone system message and pydantic-ai's bundled
        ``SystemPromptPart + UserPromptPart`` request.
        """
        return self.role == "system"

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
    """One visible row in the TUI list — always a whole-message header.

    Thin named wrapper around ``message_idx`` so call sites read as
    ``row.message_idx`` rather than a bare int that needs context. The
    menu operates on whole entries only; individual tool calls within a
    message are not separately selectable.
    """

    message_idx: int  # index into MessageEntry list (not history_index)


@dataclass
class PruneSelection:
    """Result of the menu — what the caller should remove.

    Only whole messages can be selected. Their tool calls (and the
    matching tool returns elsewhere in history) come along for the ride
    via cascade logic in ``_perform_prune``.
    """

    history_indices_to_drop: Set[int] = field(default_factory=set)

    @property
    def is_empty(self) -> bool:
        return not self.history_indices_to_drop


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

        return MessageEntry(
            history_index=-1,
            role="assistant",
            preview=short_str(text, limit=80),
            full_text=full_text,
            tool_calls=tool_calls,
            thinking_segments=thinking_segments,
        )

    return MessageEntry(
        history_index=-1,
        role="unknown",
        preview=short_str(message),
        full_text=str(message),
    )


def build_message_entries(raw_history: List[Any]) -> List[MessageEntry]:
    """Turn pydantic-ai history into a list of MessageEntry, preserving order.

    Pure-system messages in raw history are filtered out. Tool-return-only
    messages stay in the list but are flagged so the menu can hide them
    from the top level and surface them via the parent tool calls instead.

    The sys row (when shown) comes exclusively from real history (e.g. a
    ``SystemPromptPart`` bundled in ``history[0]``); no synthetic sys row
    is ever injected. This avoids duplicate-at-index-1 issues with
    transports that fold the system prompt into the first user message
    (e.g. claude-code OAuth).
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

    # Walk newest → oldest, marking in_context until the budget runs
    # out. The context window is a CONTIGUOUS tail: the ``overflowed``
    # latch ensures that once any message fails to fit, every older
    # message is also marked out-of-context, regardless of its size.
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

    # ``used_tokens`` reflects only the in-context tail (what would
    # actually be sent next turn); messages that overflowed are
    # reported separately via ``out_of_context_tokens`` so the budget
    # percentage stays bounded at 100%.
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
    "C_FOOTER_WARN",
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
