"""Pure helpers for message history hashing, token estimation, and pruning.

Extracted from the original ``BaseAgent`` god-class. Everything in here is a
free function with no hidden state. Call sites pass messages (and, where
needed, already-resolved strings / tool dicts) in explicitly.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from typing import Any, Dict, List, Optional, Set

import pydantic
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage


def _digest(text: str) -> str:
    """Deterministic 16-hex-char digest of ``text``.

    First 16 hex chars (64 bits) of SHA-256 over the utf-8 encoding — stable
    across processes and Python versions, unlike the PYTHONHASHSEED-salted
    builtin ``hash()``. 64 bits is plenty for dedup-set collision resistance.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _digest_bytes(data: bytes) -> str:
    """Deterministic 16-hex-char digest of raw bytes (BinaryContent data)."""
    return hashlib.sha256(data).hexdigest()[:16]


def stringify_part(part: Any) -> str:
    """Return a stable, timestamp-free string representation of a message part.

    Used for both hashing and token estimation. Ignoring timestamps means two
    otherwise-identical parts emitted at different times collapse to the same
    string, which is exactly what we want for dedup.

    Keyed on the part's ``part_kind`` (a stable dataclass field string like
    ``"user-prompt"`` / ``"tool-call"``) rather than the class name, so hashes
    survive pydantic-ai class renames across versions. ``__class__.__name__``
    is only a fallback for objects lacking ``part_kind``.
    """
    kind = getattr(part, "part_kind", None) or part.__class__.__name__
    attributes: List[str] = [kind]

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
                attributes.append(f"BinaryContent={_digest_bytes(item.data)}")
    else:
        attributes.append(f"content={repr(content)}")

    return "|".join(attributes)


def hash_message(message: Any) -> str:
    """Stable content-based hash for a ``ModelMessage``; ignores timestamps.

    Returns the first 16 hex chars of SHA-256 over the canonical string (see
    :func:`_digest`), so hashes are deterministic across processes and
    resilient to pydantic-ai class renames (parts are keyed on ``part_kind``).
    """
    role = getattr(message, "role", None)
    instructions = getattr(message, "instructions", None)
    header_bits: List[str] = []
    if role:
        header_bits.append(f"role={role}")
    if instructions:
        header_bits.append(f"instructions={instructions}")

    part_strings = [stringify_part(part) for part in getattr(message, "parts", [])]
    canonical = "||".join(header_bits + part_strings)
    return _digest(canonical)


def estimate_tokens(text: str) -> int:
    """Dirt-simple tiktoken replacement: ``max(1, floor(len(text) / 2.5))``."""
    return max(1, math.floor(len(text) / 2.5))


# Models whose tokenizer the char/2.5 heuristic systematically *under*counts;
# bump by a calibration factor. Case-insensitive substring match — vendor
# naming order is a coin flip.
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

    Reads each toolset's cached tool definitions (populated by pydantic-ai
    after the first ``list_tools()`` call) via
    ``mcp_.toolset_utils.iter_cached_tool_defs``. Servers that haven't been
    queried yet show up as zero — so the badge is conservative until the
    first turn, then snaps to the real number. We deliberately don't trigger
    ``list_tools()`` here: this function must stay sync + side-effect-free.

    Each tool contributes its (prefixed) name, description, and JSON input
    schema — the same three things pydantic-ai serializes into the request
    payload.
    """
    if not mcp_servers:
        return 0

    from code_puppy.mcp_.toolset_utils import iter_cached_tool_defs

    total = 0
    for server in mcp_servers:
        for full_name, description, schema in iter_cached_tool_defs(server):
            if full_name:
                total += estimate_tokens(full_name)
            if description:
                total += estimate_tokens(description)
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
            toolset's cached tool definitions (populated lazily by
            pydantic-ai) are inspected for tool name/description/schema
            overhead.

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


# Pydantic-AI has FIVE part kinds carrying a tool_call_id that participate in
# call/return pairing: tool-call/-return, builtin-tool-call/-return (claude
# extended-thinking), and retry-prompt (acts as a response). Counting only
# tool-call/-return caused bugs: e.g. builtin calls on Claude Opus stayed
# "pending" forever, deferring summarization.
#
# v2.31.0 vocabulary audit: the only new part kinds are
# 'tool-availability-delta' (carries an *optional* tool_call_id but is an
# additive tool-reveal marker, NOT a call or return — must stay unpaired so
# pruning never drops it) and 'speech' (realtime audio, no tool_call_id).
# Neither joins these sets.
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


def _collect_tool_ids(messages: List[ModelMessage]) -> tuple[Set[str], Set[str]]:
    """Return (call_ids, return_ids) across all message parts."""
    tool_call_ids: Set[str] = set()
    tool_return_ids: Set[str] = set()

    for msg in messages:
        for part in getattr(msg, "parts", []) or []:
            kind = _classify_tool_part(part)

            if kind == "call":
                tool_call_ids.add(part.tool_call_id)

            elif kind == "return":
                tool_return_ids.add(part.tool_call_id)

    return tool_call_ids, tool_return_ids


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

    tool_call_ids, tool_return_ids = _collect_tool_ids(messages)

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

    tool_call_ids, tool_return_ids = _collect_tool_ids(messages)
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


# Anthropic requires tool_use IDs to match this pattern; other providers
# (Kimi, etc.) may emit IDs with dots/colons that violate it. Those dirty IDs
# persist through mid-conversation model switches and cause 400 errors.
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
            # Gemini puts thoughtSignature on FunctionCall; the OpenAI-compat
            # schema has no such field, so LiteLLM smuggles it into tool_call_id
            # as `<id>__thought__<base64>`. It must round-trip intact — even the
            # collision-guard suffix corrupts it (400 next turn), and it's
            # unneeded anyway (the signature makes ids globally unique).
            # _LITELLM_THOUGHT_RE matches the exact suffix to exempt carriers.
            if tcid and _LITELLM_THOUGHT_RE.search(tcid):
                continue
            if tcid and not _ANTHROPIC_TOOL_ID_RE.match(tcid):
                if tcid not in bad_ids:
                    # Replace non-matching chars with '_' plus a short hash
                    # suffix to avoid collisions between IDs that sanitize alike.
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
