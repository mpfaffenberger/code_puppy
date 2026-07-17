"""Pure helpers for message history hashing, token estimation, and pruning.

Extracted from the original ``BaseAgent`` god-class. Everything in here is a
free function with no hidden state. Call sites pass messages (and, where
needed, already-resolved strings / tool dicts) in explicitly.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
from typing import Any, Dict, List, Optional, Set

import pydantic
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage


def stringify_part(part: Any) -> str:
    """Return a stable, timestamp-free string representation of a message part.

    Used for both hashing and token estimation. Ignoring timestamps means two
    otherwise-identical parts emitted at different times collapse to the same
    string, which is exactly what we want for dedup.
    """
    attributes: List[str] = [part.__class__.__name__]

    if hasattr(part, "role") and part.role:
        attributes.append(f"role={part.role}")
    if hasattr(part, "instructions") and part.instructions:
        attributes.append(f"instructions={part.instructions}")

    if hasattr(part, "tool_call_id") and part.tool_call_id:
        attributes.append(f"tool_call_id={part.tool_call_id}")
    if hasattr(part, "tool_name") and part.tool_name:
        attributes.append(f"tool_name={part.tool_name}")

    content = getattr(part, "content", None)
    if content is None:
        attributes.append("content=None")
    elif isinstance(content, str):
        attributes.append(f"content={content}")
    elif isinstance(content, pydantic.BaseModel):
        attributes.append(f"content={json.dumps(content.model_dump(), sort_keys=True)}")
    elif isinstance(content, dict):
        attributes.append(f"content={json.dumps(content, sort_keys=True)}")
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                attributes.append(f"content={item}")
            elif isinstance(item, BinaryContent):
                attributes.append(f"BinaryContent={hash(item.data)}")
    else:
        attributes.append(f"content={repr(content)}")

    return "|".join(attributes)


def hash_message(message: Any) -> int:
    """Stable hash for a ``ModelMessage`` that ignores timestamps."""
    role = getattr(message, "role", None)
    instructions = getattr(message, "instructions", None)
    header_bits: List[str] = []
    if role:
        header_bits.append(f"role={role}")
    if instructions:
        header_bits.append(f"instructions={instructions}")

    part_strings = [stringify_part(part) for part in getattr(message, "parts", [])]
    canonical = "||".join(header_bits + part_strings)
    return hash(canonical)


def estimate_tokens(text: str) -> int:
    """Dirt-simple tiktoken replacement: ``max(1, floor(len(text) / 2.5))``."""
    return max(1, math.floor(len(text) / 2.5))


# Models whose tokenizer the char/2.5 heuristic systematically *under*counts.
# Bump these by a calibration factor so context-usage math stops lying to us.
# Substring match is case-insensitive; both naming orders are accepted because
# vendor naming is a coin flip.
_TOKEN_MULTIPLIER_RULES: tuple[tuple[tuple[str, ...], float], ...] = (
    (("opus-4-7", "4-7-opus"), 1.35),
)


def model_token_multiplier(model_name: Optional[str]) -> float:
    """Per-model fudge factor for our char-based token estimator.

    Returns 1.0 when ``model_name`` is falsy or doesn't match any rule.
    """
    if not model_name:
        return 1.0
    lowered = model_name.lower()
    for needles, factor in _TOKEN_MULTIPLIER_RULES:
        if any(needle in lowered for needle in needles):
            return factor
    return 1.0


def _apply_multiplier(raw_tokens: int, model_name: Optional[str]) -> int:
    multiplier = model_token_multiplier(model_name)
    if multiplier == 1.0:
        return raw_tokens
    return max(1, math.floor(raw_tokens * multiplier))


def estimate_tokens_for_message(
    message: ModelMessage,
    model_name: Optional[str] = None,
) -> int:
    """Estimate the number of tokens in a single model message.

    When ``model_name`` is provided, the raw count is scaled by
    :func:`model_token_multiplier` to compensate for tokenizers that don't
    play nicely with our char/2.5 heuristic.
    """
    total = 0
    for part in getattr(message, "parts", []) or []:
        part_str = stringify_part(part)
        if part_str:
            total += estimate_tokens(part_str)
    return _apply_multiplier(max(1, total), model_name)


def _extract_tool_description(tool_obj: Any) -> str:
    """Pull the human-readable description off a tool, regardless of shape.

    Handles both pydantic-ai ``Tool`` objects (``.description`` /
    ``.function_schema.description``) and bare callables (``__doc__``).
    """
    desc = getattr(tool_obj, "description", None)
    if desc:
        return desc
    fs = getattr(tool_obj, "function_schema", None)
    if fs is not None:
        fs_desc = getattr(fs, "description", None)
        if fs_desc:
            return fs_desc
    doc = getattr(tool_obj, "__doc__", None) or ""
    # Skip the generic class-level docstring pydantic-ai's Tool exposes.
    if doc and doc.strip().lower() == "a tool function for an agent.":
        return ""
    return doc or ""


def _extract_tool_json_schema(tool_obj: Any) -> Optional[dict]:
    """Pull the JSON schema off a tool, regardless of shape."""
    fs = getattr(tool_obj, "function_schema", None)
    if fs is not None:
        schema = getattr(fs, "json_schema", None)
        if isinstance(schema, dict):
            return schema
    schema = getattr(tool_obj, "schema", None)
    if isinstance(schema, dict):
        return schema
    return None


def _estimate_mcp_tool_tokens(mcp_servers: Optional[List[Any]]) -> int:
    """Count tokens contributed by MCP toolsets' tool definitions.

    Reads each server's ``_cached_tools`` (populated by pydantic-ai after the
    first ``list_tools()`` call). Servers that haven't been queried yet show
    up as zero — so the badge is conservative until the first turn, then
    snaps to the real number. We deliberately don't trigger ``list_tools()``
    here: this function must stay sync + side-effect-free.

    Each ``mcp_types.Tool`` contributes its (prefixed) name, description, and
    JSON input schema — the same three things pydantic-ai serializes into
    the request payload.
    """
    if not mcp_servers:
        return 0

    total = 0
    for server in mcp_servers:
        cached = getattr(server, "_cached_tools", None)
        if not cached:
            continue
        prefix = getattr(server, "tool_prefix", None) or ""
        for mcp_tool in cached:
            name = getattr(mcp_tool, "name", "") or ""
            full_name = f"{prefix}_{name}" if prefix else name
            if full_name:
                total += estimate_tokens(full_name)
            description = getattr(mcp_tool, "description", "") or ""
            if description:
                total += estimate_tokens(description)
            schema = getattr(mcp_tool, "inputSchema", None)
            if schema:
                try:
                    total += estimate_tokens(json.dumps(schema, sort_keys=True))
                except (TypeError, ValueError):
                    # Schema isn't JSON-serializable for some reason — fall
                    # back to repr so we at least account for *something*.
                    total += estimate_tokens(repr(schema))
    return total


def estimate_context_overhead(
    system_prompt: str,
    pydantic_tools: Optional[Dict[str, Any]],
    model_name: Optional[str] = None,
    mcp_servers: Optional[List[Any]] = None,
) -> int:
    """Estimate fixed token overhead for the system prompt + tool definitions.

    The caller is responsible for resolving the system prompt for the active
    model (e.g. via ``prepare_prompt_for_model``).

    Args:
        system_prompt: The already-resolved instruction/system prompt string.
        pydantic_tools: A dict of ``{tool_name: tool_obj}``. ``tool_obj`` may be
            a pydantic-ai ``Tool`` (has ``.description`` + ``.function_schema``)
            or a bare callable (legacy shape — falls back to ``__doc__`` /
            ``__annotations__``).
        mcp_servers: Optional list of pydantic-ai MCP server toolsets. Each
            server's ``_cached_tools`` (populated lazily by pydantic-ai) is
            inspected for tool name/description/schema overhead.

    Returns:
        Estimated total token overhead.
    """
    total = 0
    if system_prompt:
        total += estimate_tokens(system_prompt)

    if pydantic_tools:
        for tool_name, tool_obj in pydantic_tools.items():
            total += estimate_tokens(tool_name)

            description = _extract_tool_description(tool_obj)
            if description:
                total += estimate_tokens(description)

            schema = _extract_tool_json_schema(tool_obj)
            if schema is not None:
                total += estimate_tokens(json.dumps(schema))
            else:
                annotations = getattr(tool_obj, "__annotations__", None)
                if annotations:
                    total += estimate_tokens(str(annotations))

    total += _estimate_mcp_tool_tokens(mcp_servers)

    return _apply_multiplier(total, model_name)


# Pydantic-AI has FOUR part kinds that carry a tool_call_id:
#   * tool-call            -> ToolCallPart            (regular tool call)
#   * tool-return          -> ToolReturnPart          (regular tool response)
#   * builtin-tool-call    -> BuiltinToolCallPart     (claude extended-thinking, etc.)
#   * builtin-tool-return  -> BuiltinToolReturnPart   (builtin tool response)
#   * retry-prompt         -> RetryPromptPart         (assistant told to retry; acts as a response)
#
# Treating only `tool-call` / `tool-return` (and ignoring the others) caused
# subtle bugs: e.g. builtin tool calls on Claude Opus were counted as pending
# forever, deferring summarization on every turn.
_TOOL_CALL_PART_KINDS: frozenset[str] = frozenset({"tool-call", "builtin-tool-call"})
_TOOL_RETURN_PART_KINDS: frozenset[str] = frozenset(
    {"tool-return", "builtin-tool-return", "retry-prompt"}
)


def _classify_tool_part(part: object) -> str | None:
    """Return ``"call"``, ``"return"``, or ``None`` for a message part.

    ``None`` means the part doesn't participate in tool_call_id pairing
    (either no id, or an unrelated part kind).
    """
    if getattr(part, "tool_call_id", None) is None:
        return None
    pk = getattr(part, "part_kind", None)
    if pk in _TOOL_CALL_PART_KINDS:
        return "call"
    if pk in _TOOL_RETURN_PART_KINDS:
        return "return"
    return None


def prune_interrupted_tool_calls(
    messages: List[ModelMessage],
) -> List[ModelMessage]:
    """Drop messages participating in mismatched tool_call/tool_return pairs.

    A mismatched ``tool_call_id`` is one that appears only as a call or only
    as a return. The model will reject such histories ("tool_use ids found
    without tool_result blocks"), so we strip them out while preserving order.
    """
    if not messages:
        return messages

    tool_call_ids: Set[str] = set()
    tool_return_ids: Set[str] = set()

    for msg in messages:
        for part in getattr(msg, "parts", []) or []:
            kind = _classify_tool_part(part)
            if kind == "call":
                tool_call_ids.add(part.tool_call_id)
            elif kind == "return":
                tool_return_ids.add(part.tool_call_id)

    mismatched = tool_call_ids.symmetric_difference(tool_return_ids)
    if not mismatched:
        return messages

    pruned: List[ModelMessage] = []
    for msg in messages:
        if any(
            getattr(part, "tool_call_id", None) in mismatched
            for part in getattr(msg, "parts", []) or []
        ):
            continue
        pruned.append(msg)
    return pruned


def has_pending_tool_calls(messages: List[ModelMessage]) -> bool:
    """Return True if any tool call is still waiting for its response.

    Recognizes both regular (``tool-call`` / ``tool-return``) and builtin
    (``builtin-tool-call`` / ``builtin-tool-return``) pairings, plus
    ``retry-prompt`` as a valid response form.
    """
    if not messages:
        return False

    tool_call_ids: Set[str] = set()
    tool_return_ids: Set[str] = set()

    for msg in messages:
        for part in getattr(msg, "parts", []) or []:
            kind = _classify_tool_part(part)
            if kind == "call":
                tool_call_ids.add(part.tool_call_id)
            elif kind == "return":
                tool_return_ids.add(part.tool_call_id)

    return bool(tool_call_ids - tool_return_ids)


def filter_huge_messages(
    messages: List[ModelMessage],
    model_name: Optional[str] = None,
) -> List[ModelMessage]:
    """Drop individual messages above a 50k-token budget, then prune orphans."""
    filtered = [
        m for m in messages if estimate_tokens_for_message(m, model_name) < 50000
    ]
    return prune_interrupted_tool_calls(filtered)


# Tool-result clearing: once a tool result is deep in history, the agent has
# already extracted what it needed — the raw payload is dead weight. We replace
# the bulky content with a short stub, keeping the call/return pair intact so
# the history stays valid and the model still knows the tool ran.
_CLEARED_PREFIX = "[tool result cleared"
_CLEARABLE_RETURN_KINDS: frozenset[str] = frozenset(
    {"tool-return", "builtin-tool-return"}
)


def _replace_part_content(part: Any, content: str) -> Any:
    """Return ``part`` with ``content`` swapped, tolerating immutable shapes."""
    try:
        return dataclasses.replace(part, content=content)
    except TypeError:
        try:
            part.content = content
        except (AttributeError, TypeError):
            pass
        return part


def clear_stale_tool_results(
    messages: List[ModelMessage],
    *,
    keep_recent: int = 4,
    min_tokens: int = 1500,
    model_name: Optional[str] = None,
) -> tuple[List[ModelMessage], int]:
    """Replace large, old tool-return payloads with compact stubs.

    The most recent ``keep_recent`` tool results are preserved verbatim (the
    model needs fresh examples of tool behavior). Older returns whose payload
    exceeds ``min_tokens`` are stubbed. Call/return pairing and ordering are
    preserved, and already-stubbed results are skipped, so this is idempotent
    and safe to run on every history-processor cycle.

    Returns ``(new_messages, num_cleared)``.
    """
    if not messages or keep_recent < 0:
        return messages, 0

    locations: List[tuple[int, int]] = []
    for mi, msg in enumerate(messages):
        for pi, part in enumerate(getattr(msg, "parts", []) or []):
            if getattr(part, "part_kind", None) in _CLEARABLE_RETURN_KINDS and getattr(
                part, "tool_call_id", None
            ):
                locations.append((mi, pi))

    if len(locations) <= keep_recent:
        return messages, 0

    protected = set(locations[-keep_recent:]) if keep_recent else set()
    targets_by_msg: Dict[int, Set[int]] = {}
    for loc in locations:
        if loc in protected:
            continue
        targets_by_msg.setdefault(loc[0], set()).add(loc[1])

    new_messages = list(messages)
    cleared = 0
    for mi, part_idxs in targets_by_msg.items():
        parts = list(getattr(messages[mi], "parts", []) or [])
        changed = False
        for pi in part_idxs:
            part = parts[pi]
            content = getattr(part, "content", None)
            if isinstance(content, str) and content.startswith(_CLEARED_PREFIX):
                continue
            tokens = estimate_tokens(stringify_part(part))
            if tokens < min_tokens:
                continue
            tool_name = getattr(part, "tool_name", None) or "tool"
            stub = (
                f"{_CLEARED_PREFIX} to save context — {tool_name} output "
                f"(~{tokens} tokens) removed from history. Re-run the tool if you "
                "need it again.]"
            )
            parts[pi] = _replace_part_content(part, stub)
            changed = True
            cleared += 1
        if changed:
            try:
                new_messages[mi] = dataclasses.replace(messages[mi], parts=parts)
            except TypeError:
                try:
                    messages[mi].parts = parts
                except (AttributeError, TypeError):
                    pass
    return new_messages, cleared


# Anthropic's API requires tool_use IDs to match this pattern.
# Other providers (Kimi, etc.) may generate IDs with dots, colons, etc.
# that violate this constraint. When switching models mid-conversation,
# those dirty IDs persist in the message history and cause 400 errors.
_ANTHROPIC_TOOL_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
# Character-level replacement: swap any character NOT in the allowed set.
_BAD_TOOL_ID_CHAR_RE = re.compile(r"[^a-zA-Z0-9_-]")
# LiteLLM smuggles Vertex/Gemini thoughtSignature blobs as
# `<id>__thought__<base64-payload>` at the end of tool_call_id.
_LITELLM_THOUGHT_RE = re.compile(r"__thought__[A-Za-z0-9+/=]+$")


def sanitize_tool_call_ids(
    messages: List[ModelMessage],
) -> List[ModelMessage]:
    """Replace tool_call_ids that don't match Anthropic's required pattern.

    Anthropic's API enforces ``^[a-zA-Z0-9_-]+$`` on ``tool_use.id`` fields.
    Other providers (Kimi via Firepass, etc.) may generate IDs containing
    dots, colons, or other characters. When switching from such a provider
    to Claude mid-conversation, the stale IDs in the message history cause
    a 400 rejection.

    This function walks all message parts and replaces any non-conforming
    ``tool_call_id`` with a sanitized version. A deterministic mapping
    ensures tool-call ↔ tool-return pairs stay linked.

    This is safe to run on every history-processor cycle; IDs that already
    match the pattern pass through unchanged.
    """
    # Collect all non-conforming IDs and build a deterministic mapping.
    bad_ids: Dict[str, str] = {}
    for msg in messages:
        for part in getattr(msg, "parts", []) or []:
            tcid = getattr(part, "tool_call_id", None)
            # Gemini's native API puts thoughtSignature on FunctionCall as a
            # separate field. The OpenAI-compat schema has no such field, so
            # LiteLLM smuggles it into tool_call_id: `<id>__thought__<base64>`.
            # Gemini requires this to round-trip intact — even the `_<6digit>`
            # collision-guard suffix below corrupts it and causes a 400 on the
            # next tool turn. The collision guard isn't needed here anyway: the
            # embedded signature makes each id globally unique. _LITELLM_THOUGHT_RE
            # matches the exact suffix so only genuine carrier ids are exempted.
            if tcid and _LITELLM_THOUGHT_RE.search(tcid):
                continue
            if tcid and not _ANTHROPIC_TOOL_ID_RE.match(tcid):
                if tcid not in bad_ids:
                    # Replace non-matching chars with '_' and append a short
                    # hash suffix to avoid collisions from different dirty IDs
                    # that sanitize to the same string.
                    sanitized_base = _BAD_TOOL_ID_CHAR_RE.sub("_", tcid)
                    collision_guard = format(abs(hash(tcid)) % (10**6), "06d")
                    candidate = f"{sanitized_base}_{collision_guard}"
                    # Belt-and-suspenders: ensure the candidate itself conforms.
                    if not _ANTHROPIC_TOOL_ID_RE.match(candidate):
                        candidate = f"tc_{collision_guard}"
                    bad_ids[tcid] = candidate

    if not bad_ids:
        return messages

    # Rebuild messages with sanitized IDs.
    sanitized: List[ModelMessage] = []
    for msg in messages:
        parts = list(getattr(msg, "parts", []) or [])
        needs_rebuild = False
        new_parts: List[Any] = []
        for part in parts:
            tcid = getattr(part, "tool_call_id", None)
            if tcid and tcid in bad_ids:
                needs_rebuild = True
                try:
                    new_parts.append(
                        dataclasses.replace(part, tool_call_id=bad_ids[tcid])
                    )
                except TypeError:
                    # If dataclasses.replace fails (frozen, __slots__, etc.),
                    # fall back to setattr.
                    try:
                        part.tool_call_id = bad_ids[tcid]  # type: ignore[misc]
                        new_parts.append(part)
                    except (AttributeError, TypeError):
                        # Truly immutable — skip this part's ID fix.
                        new_parts.append(part)
            else:
                new_parts.append(part)
        if needs_rebuild:
            try:
                sanitized.append(dataclasses.replace(msg, parts=new_parts))
            except TypeError:
                # If message replacement fails, try mutating in place.
                try:
                    msg.parts = new_parts  # type: ignore[misc]
                    sanitized.append(msg)
                except (AttributeError, TypeError):
                    sanitized.append(msg)
        else:
            sanitized.append(msg)

    return sanitized
