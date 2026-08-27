"""Pure helpers for message history hashing, token estimation, and pruning.

Extracted from the original ``BaseAgent`` god-class. Everything in here is a
free function with no hidden state. Call sites pass messages (and, where
needed, already-resolved strings / tool dicts) in explicitly.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import math
import re
from typing import Any, Dict, List, Optional, Set

import pydantic
from pydantic_ai import BinaryContent
from pydantic_ai.messages import (
    INTERRUPTED_TOOL_RETURN_CONTENT,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolReturnPart,
)


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
                # ImageUrl / DocumentUrl / anything pydantic-ai adds later.
                # Without this arm such items contribute nothing, so two
                # messages pointing at different URLs hash identically.
                attributes.append(f"content={repr(item)}")
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


# Vision models bill images by area, not by the handful of characters our
# digest happens to occupy. Anthropic documents roughly (width * height) / 750
# tokens and OpenAI's tile math lands in the same ballpark, so use that.
_IMAGE_PIXELS_PER_TOKEN = 750

# Charged when dimensions can't be read: a corrupt or unsupported image, or a
# non-image attachment such as a PDF whose real cost isn't visible from here.
# Deliberately generous, because undercounting is the failure that silently
# skips compaction and ends the run on a provider 400.
_BINARY_CONTENT_FALLBACK_TOKENS = 1500


def _image_dimensions(data: bytes) -> Optional[tuple[int, int]]:
    """``(width, height)`` of an encoded image, or None if it can't be read.

    ``Image.open`` parses only the header; pixel data is loaded lazily and we
    never touch it, so this stays cheap enough for the estimation path.
    """
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            return img.size
    except Exception:
        return None


def estimate_binary_content_tokens(item: Any) -> int:
    """Token charge for a single ``BinaryContent`` attachment.

    ``stringify_part`` deliberately reduces binary data to a short digest so
    hashes stay stable and cheap, which means the digest string tells us
    nothing about what the image actually costs. Estimate that here instead.
    """
    media_type = getattr(item, "media_type", "") or ""
    data = getattr(item, "data", b"") or b""
    if media_type.startswith("image/"):
        dimensions = _image_dimensions(data)
        if dimensions is not None:
            width, height = dimensions
            return max(1, (width * height) // _IMAGE_PIXELS_PER_TOKEN)
    return _BINARY_CONTENT_FALLBACK_TOKENS


def _binary_tokens_in_part(part: Any) -> int:
    """Total binary-attachment token charge for one message part."""
    content = getattr(part, "content", None)
    if not isinstance(content, list):
        return 0
    return sum(
        estimate_binary_content_tokens(item)
        for item in content
        if isinstance(item, BinaryContent)
    )


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
        total += _binary_tokens_in_part(part)
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
# extended-thinking / provider-executed), and retry-prompt (acts as a response
# only when it is tool-bound — a nameless retry is validation feedback, not a
# result). ``_classify_tool_part`` and these sets describe that full vocabulary
# for consumers that want every id-bearing part. The repair and
# pending-detection logic instead uses the narrower ``_is_repairable_*``
# predicates below, which exclude builtin parts.
#
# v2.31.0 vocabulary audit: the only new part kinds are
# 'tool-availability-delta' (carries an *optional* tool_call_id but is an
# additive tool-reveal marker, NOT a call or return — must stay unpaired so
# pruning never drops it) and 'speech' (realtime audio, no tool_call_id).
# Neither joins these sets.
_TOOL_CALL_PART_KINDS: frozenset[str] = frozenset({"tool-call", "builtin-tool-call"})
_TOOL_RETURN_PART_KINDS: frozenset[str] = frozenset(
    {"tool-return", "builtin-tool-return"}
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
    if pk == "retry-prompt":
        # Nameless retries are validation / "please return text" feedback,
        # not a tool result (mirrors pydantic-ai's `_is_tool_result_part`).
        return "return" if getattr(part, "tool_name", None) is not None else None
    if pk in _TOOL_RETURN_PART_KINDS:
        return "return"
    return None


# Repair and pending-detection pair ONLY regular (locally-executed) tool parts.
# Builtin/native calls and returns are left alone, mirroring pydantic-ai:
# provider-executed results are self-contained and can even arrive in a later
# provider turn, so a "missing" builtin return is not a defect to synthesize or
# drop — and counting one keeps a history "pending" forever.
def _is_repairable_call(part: object) -> bool:
    """A regular ``tool-call`` awaiting a local ``tool-return``."""
    return (
        getattr(part, "part_kind", None) == "tool-call"
        and getattr(part, "tool_call_id", None) is not None
    )


def _is_repairable_return(part: object) -> bool:
    """A regular tool result (or tool-bound retry) that answers a local call."""
    if getattr(part, "tool_call_id", None) is None:
        return False
    pk = getattr(part, "part_kind", None)
    if pk == "tool-return":
        return True
    if pk == "retry-prompt":
        # A nameless retry is validation feedback, not a tool result.
        return getattr(part, "tool_name", None) is not None
    return False


def _insert_tool_returns(
    request: ModelMessage, returns: List[ToolReturnPart]
) -> ModelMessage:
    """Return ``request`` with ``returns`` spliced in after its tool returns."""
    parts = list(getattr(request, "parts", []) or [])
    insert_at = 0
    for position, part in enumerate(parts):
        if _is_repairable_return(part):
            insert_at = position + 1
    parts[insert_at:insert_at] = returns
    return dataclasses.replace(request, parts=parts)


def _collect_tool_ids(messages: List[ModelMessage]) -> tuple[Set[str], Set[str]]:
    """Return (tool_call_ids, tool_return_ids) across all message parts."""
    tool_call_ids: Set[str] = set()
    tool_return_ids: Set[str] = set()

    for msg in messages:
        for part in getattr(msg, "parts", []) or []:
            if _is_repairable_call(part):
                tool_call_ids.add(part.tool_call_id)

            elif _is_repairable_return(part):
                tool_return_ids.add(part.tool_call_id)

    return tool_call_ids, tool_return_ids


def prune_interrupted_tool_calls(
    messages: List[ModelMessage],
) -> List[ModelMessage]:
    """Repair histories whose tool calls and returns do not pair up.

    A ``tool_call_id`` that appears only as a call or only as a return would
    make providers reject the request ("tool_use ids found without
    tool_result blocks"). The repair works at part granularity, mirroring
    pydantic-ai's request-time pass, so completed sibling calls in the same
    assistant turn survive an interrupted one:

    - a dangling tool call (no matching return) is closed out with a
      synthesized ``ToolReturnPart`` inserted into the following request —
      or a trailing request when none follows — so the model sees that the
      call was interrupted instead of losing the whole turn;
    - an orphaned return (no matching call) drops only that part, keeping
      the rest of its message. A request emptied of every part this way is
      dropped wherever it sits — a kept trailing empty request would make the
      wire history end on the assistant turn, which providers reject.

    Builtin (provider-executed) tool calls are left alone: their results
    arrive from the provider in a later turn, so a missing return is not a
    defect, and pydantic-ai's own repair ignores them for the same reason.

    Returns the input unchanged when every call and return already pair up.
    """
    if not messages:
        return messages

    tool_call_ids, tool_return_ids = _collect_tool_ids(messages)

    dangling_calls = tool_call_ids - tool_return_ids
    orphaned_returns = tool_return_ids - tool_call_ids
    if not dangling_calls and not orphaned_returns:
        return messages

    def _is_dangling_call(part: object) -> bool:
        return _is_repairable_call(part) and part.tool_call_id in dangling_calls

    pruned: List[ModelMessage] = []
    synthesized: List[ToolReturnPart] = []

    for index, msg in enumerate(messages):
        if isinstance(msg, ModelResponse):
            if synthesized:
                # The previous response's dangling calls are followed by
                # another response, so their returns need a request of
                # their own in between.
                pruned.append(ModelRequest(parts=synthesized))
                synthesized = []

            for part in getattr(msg, "parts", []) or []:
                if _is_dangling_call(part):
                    synthesized.append(
                        ToolReturnPart(
                            tool_name=part.tool_name,
                            content=INTERRUPTED_TOOL_RETURN_CONTENT,
                            tool_call_id=part.tool_call_id,
                            # Inherit the repaired response's timestamp so
                            # repeated pruning is deterministic.
                            timestamp=msg.timestamp,
                            outcome="interrupted",
                        )
                    )

            pruned.append(msg)
            continue

        if synthesized:
            msg = _insert_tool_returns(msg, synthesized)
            synthesized = []

        original_parts = list(getattr(msg, "parts", []) or [])

        kept_parts = [
            part
            for part in original_parts
            if not (
                _is_repairable_return(part) and part.tool_call_id in orphaned_returns
            )
        ]

        if len(kept_parts) != len(original_parts):
            if not kept_parts:
                # A request emptied of every part carries nothing — drop it
                # wherever it sits, tail included. Provider mappers skip a
                # zero-part request, so a kept trailing empty request would end
                # the wire history on the assistant turn (prefill), which
                # Anthropic/Bedrock reject, and would slip past
                # make_history_processor's trailing-ModelResponse trim.
                continue
            msg = dataclasses.replace(msg, parts=kept_parts)

        pruned.append(msg)

    if synthesized:
        pruned.append(ModelRequest(parts=synthesized))
    return pruned


def has_pending_tool_calls(messages: List[ModelMessage]) -> bool:
    """Return True if any regular tool call is still waiting for its response.

    Recognizes regular (``tool-call`` / ``tool-return``) pairing plus
    ``retry-prompt`` as a valid response form. Builtin/native tool parts are
    excluded (see ``_is_repairable_call`` / ``_is_repairable_return``): a
    provider-executed call whose return is still to come must not read as
    "pending" and defer compaction forever.
    """
    if not messages:
        return False

    tool_call_ids, tool_return_ids = _collect_tool_ids(messages)
    return bool(tool_call_ids - tool_return_ids)


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
