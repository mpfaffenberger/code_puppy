"""Masking-first continuity compaction engine."""

from __future__ import annotations

import dataclasses
import json
import math
import re
from typing import Any, Iterable

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    UserPromptPart,
)

from code_puppy.agents._history import (
    estimate_tokens_for_message,
    hash_message,
    prune_interrupted_tool_calls,
)
from code_puppy.agents.continuity_compaction.settings import (
    ContinuityCompactionSettings,
    load_continuity_compaction_settings,
)
from code_puppy.agents.continuity_compaction.storage import (
    DURABLE_MEMORY_MARKER,
    MASKED_OBSERVATION_MARKER,
    STRUCTURED_SUMMARY_MARKER,
    DurableState,
    archive_observation,
    cleanup_observation_archives,
    render_durable_state,
    render_masked_observation,
    write_durable_state,
)
from code_puppy.messaging import emit_warning
from code_puppy.summarization_agent import run_summarization_sync

_TOOL_CALL_KINDS = {"tool-call", "builtin-tool-call"}
_TOOL_RETURN_KINDS = {"tool-return", "builtin-tool-return"}
_PATH_RE = re.compile(
    r"(?:\.{0,2}/|/)?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*"
    r"\.(?:py|pyi|js|jsx|ts|tsx|json|toml|yaml|yml|md|txt|go|rs|java|c|cc|cpp|h|hpp|css|html)"
)
_SIGNAL_RE = re.compile(
    r"(error|failed|failure|exception|traceback|assertion|exit code|exit_code)",
    re.IGNORECASE,
)

_STRUCTURED_FALLBACK_INSTRUCTIONS = """Summarize only these already-masked historical observations.
Use this exact schema and do not speculate:

Goal
Hard Constraints
Verified Facts
Invalidated Hypotheses
Important Decisions
Validation Status
Active Files
Next Action
Archive References
"""


def compact_continuity(
    *,
    agent: Any,
    messages: list[ModelMessage],
    model_max: int,
    context_overhead: int,
    model_name: str | None,
    force: bool = False,
) -> tuple[list[ModelMessage], list[ModelMessage]]:
    """Run continuity compaction or return the input unchanged."""
    if not messages:
        return messages, []

    settings = load_continuity_compaction_settings(model_max)
    input_messages = messages
    original_messages = list(messages)
    messages = prune_interrupted_tool_calls(messages)
    current_tokens = _history_tokens(messages, model_name) + context_overhead
    predicted_growth = _predict_next_turn_growth(
        agent, messages, current_tokens, settings, model_name
    )

    if not force and current_tokens + predicted_growth < settings.soft_trigger:
        _set_previous_total(agent, current_tokens)
        return input_messages, []

    durable_state = _build_durable_state(messages)
    write_durable_state(agent, durable_state)
    messages = _inject_durable_memory(messages, durable_state)
    cleanup_observation_archives(agent, settings)

    keep_indices = _build_keep_indices(messages, settings, model_name)
    messages = _archive_and_mask(messages, keep_indices, agent, settings, model_name)
    compacted_tokens = _history_tokens(messages, model_name) + context_overhead

    if compacted_tokens > settings.target_after_compaction:
        keep_indices = _build_keep_indices(messages, settings, model_name)
        messages = _summarize_oldest_masked_band(
            messages, keep_indices, settings, model_name, context_overhead
        )
        compacted_tokens = _history_tokens(messages, model_name) + context_overhead

    if compacted_tokens > settings.emergency_trigger:
        messages = _emergency_trim(messages, settings, model_name)
        compacted_tokens = _history_tokens(messages, model_name) + context_overhead

    messages = prune_interrupted_tool_calls(messages)
    _set_previous_total(agent, compacted_tokens)
    result_hashes = {hash_message(message) for message in messages}
    dropped = [
        message
        for message in original_messages
        if hash_message(message) not in result_hashes
    ]
    return messages, dropped


def _history_tokens(messages: Iterable[ModelMessage], model_name: str | None) -> int:
    return sum(estimate_tokens_for_message(message, model_name) for message in messages)


def _get_stats(agent: Any) -> dict[str, Any]:
    if agent is None:
        return {}
    stats = getattr(agent, "_continuity_compaction_stats", None)
    if not isinstance(stats, dict):
        stats = {
            "previous_total_tokens": None,
            "turn_growth_history": [],
        }
        setattr(agent, "_continuity_compaction_stats", stats)
    return stats


def _set_previous_total(agent: Any, total_tokens: int) -> None:
    stats = _get_stats(agent)
    if stats is not None:
        stats["previous_total_tokens"] = total_tokens


def _predict_next_turn_growth(
    agent: Any,
    messages: list[ModelMessage],
    current_tokens: int,
    settings: ContinuityCompactionSettings,
    model_name: str | None,
) -> int:
    stats = _get_stats(agent)
    previous = stats.get("previous_total_tokens")
    if isinstance(previous, int):
        growth = max(0, current_tokens - previous)
        _append_bounded(stats["turn_growth_history"], growth, settings)

    turn_p95 = _p95(stats.get("turn_growth_history", []))
    assistant_avg = _average_recent_part_tokens(
        messages, {"text"}, settings, model_name
    )
    tool_avg = _average_recent_part_tokens(
        messages, _TOOL_RETURN_KINDS, settings, model_name
    )
    return max(settings.predicted_growth_floor, turn_p95, assistant_avg, tool_avg)


def _append_bounded(
    history: list[int], value: int, settings: ContinuityCompactionSettings
) -> None:
    history.append(value)
    del history[: max(0, len(history) - settings.growth_history_window)]


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[idx]


def _average_recent_part_tokens(
    messages: list[ModelMessage],
    part_kinds: set[str],
    settings: ContinuityCompactionSettings,
    model_name: str | None,
) -> int:
    counts: list[int] = []
    for message in messages[-settings.growth_history_window :]:
        for part in getattr(message, "parts", []) or []:
            if getattr(part, "part_kind", None) in part_kinds:
                counts.append(
                    estimate_tokens_for_message(_single_part(part), model_name)
                )
    if not counts:
        return 0
    return int(sum(counts) / len(counts))


def _single_part(part: Any) -> ModelMessage:
    if getattr(part, "part_kind", None) in {"text", "tool-call"}:
        return ModelResponse(parts=[part])
    return ModelRequest(parts=[part])


def _build_keep_indices(
    messages: list[ModelMessage],
    settings: ContinuityCompactionSettings,
    model_name: str | None,
) -> set[int]:
    keep = {0} if messages else set()
    latest_user_idx = _latest_user_index(messages)
    if latest_user_idx is not None:
        keep.add(latest_user_idx)

    running = 0
    for idx in range(len(messages) - 1, -1, -1):
        keep.add(idx)
        running += estimate_tokens_for_message(messages[idx], model_name)
        if running >= settings.recent_raw_floor:
            break
    return _expand_tool_pair_indices(messages, keep)


def _latest_user_index(messages: list[ModelMessage]) -> int | None:
    for idx in range(len(messages) - 1, -1, -1):
        for part in getattr(messages[idx], "parts", []) or []:
            if getattr(part, "part_kind", None) == "user-prompt":
                content = str(getattr(part, "content", "") or "")
                if not content.startswith(DURABLE_MEMORY_MARKER):
                    return idx
    return None


def _expand_tool_pair_indices(
    messages: list[ModelMessage], indices: set[int]
) -> set[int]:
    by_id: dict[str, set[int]] = {}
    for idx, message in enumerate(messages):
        for part in getattr(message, "parts", []) or []:
            tool_call_id = getattr(part, "tool_call_id", None)
            if tool_call_id:
                by_id.setdefault(str(tool_call_id), set()).add(idx)
    expanded = set(indices)
    for idx in list(indices):
        for part in getattr(messages[idx], "parts", []) or []:
            tool_call_id = getattr(part, "tool_call_id", None)
            if tool_call_id:
                expanded.update(by_id.get(str(tool_call_id), set()))
    return expanded


def _archive_and_mask(
    messages: list[ModelMessage],
    keep_indices: set[int],
    agent: Any,
    settings: ContinuityCompactionSettings,
    model_name: str | None,
) -> list[ModelMessage]:
    result: list[ModelMessage] = []
    for idx, message in enumerate(messages):
        if idx in keep_indices:
            result.append(message)
            continue
        new_parts = []
        changed = False
        for part in getattr(message, "parts", []) or []:
            if getattr(part, "part_kind", None) not in _TOOL_RETURN_KINDS:
                new_parts.append(part)
                continue
            content = _content_text(getattr(part, "content", ""))
            token_count = estimate_tokens_for_message(_single_part(part), model_name)
            if token_count < settings.mask_min_tokens:
                new_parts.append(part)
                continue
            record = archive_observation(
                agent=agent,
                tool_name=str(getattr(part, "tool_name", "") or "unknown"),
                tool_call_id=getattr(part, "tool_call_id", None),
                content=content,
                token_count=token_count,
                key_signal=_extract_key_signal(content),
                affected_files=_extract_paths(content),
                status=_status_from_text(content),
            )
            new_parts.append(
                dataclasses.replace(part, content=render_masked_observation(record))
            )
            changed = True
        result.append(
            dataclasses.replace(message, parts=new_parts) if changed else message
        )
    return result


def _summarize_oldest_masked_band(
    messages: list[ModelMessage],
    keep_indices: set[int],
    settings: ContinuityCompactionSettings,
    model_name: str | None,
    context_overhead: int,
) -> list[ModelMessage]:
    current = _history_tokens(messages, model_name) + context_overhead
    needed = max(1, current - settings.target_after_compaction)
    selected: list[int] = []
    selected_tokens = 0
    for idx, message in enumerate(messages):
        if idx in keep_indices or not _is_masked_message(message):
            continue
        pair_indices = _expand_tool_pair_indices(messages, {idx})
        if pair_indices & keep_indices:
            continue
        selected.append(idx)
        selected_tokens += estimate_tokens_for_message(message, model_name)
        if selected_tokens >= needed:
            break
    if not selected:
        return messages

    drop_indices = _expand_tool_pair_indices(messages, set(selected))
    drop_indices.discard(0)
    summary_input = _messages_to_text(messages[idx] for idx in sorted(drop_indices))
    try:
        summary_messages = run_summarization_sync(
            _STRUCTURED_FALLBACK_INSTRUCTIONS,
            message_history=[
                ModelRequest(parts=[UserPromptPart(content=summary_input)])
            ],
        )
        summary_text = _messages_to_text(summary_messages)
    except Exception as exc:
        emit_warning(
            f"Continuity compaction fallback summarization failed; using emergency trim. {exc}"
        )
        return _emergency_trim(messages, settings, model_name)

    summary = ModelRequest(
        parts=[
            UserPromptPart(
                content=f"{STRUCTURED_SUMMARY_MARKER}\n{summary_text.strip()}"
            )
        ]
    )
    first_drop = min(drop_indices)
    rebuilt: list[ModelMessage] = []
    inserted = False
    for idx, message in enumerate(messages):
        if idx in drop_indices:
            if idx == first_drop and not inserted:
                rebuilt.append(summary)
                inserted = True
            continue
        rebuilt.append(message)
    return rebuilt


def _emergency_trim(
    messages: list[ModelMessage],
    settings: ContinuityCompactionSettings,
    model_name: str | None,
) -> list[ModelMessage]:
    if len(messages) <= 1:
        return messages
    keep = {0}
    pinned_indices = (
        _durable_memory_index(messages),
        _latest_user_index(messages),
        _latest_signal_index(messages),
        len(messages) - 1,
    )
    keep.update(idx for idx in pinned_indices if idx is not None)
    keep = _expand_tool_pair_indices(messages, keep)

    running = sum(
        estimate_tokens_for_message(messages[idx], model_name) for idx in keep
    )
    for idx in range(len(messages) - 1, 0, -1):
        if idx in keep:
            continue
        msg_tokens = estimate_tokens_for_message(messages[idx], model_name)
        if running + msg_tokens > settings.target_after_compaction and len(keep) > 1:
            break
        keep.add(idx)
        running += msg_tokens

    keep = _expand_tool_pair_indices(messages, keep)
    return [message for idx, message in enumerate(messages) if idx in keep]


def _inject_durable_memory(
    messages: list[ModelMessage], state: DurableState
) -> list[ModelMessage]:
    continuity = ModelRequest(
        parts=[UserPromptPart(content=render_durable_state(state))]
    )
    cleaned = [message for message in messages if not _is_durable_memory(message)]
    if not cleaned:
        return [continuity]
    return [cleaned[0], continuity, *cleaned[1:]]


def _is_durable_memory(message: ModelMessage) -> bool:
    return any(
        str(getattr(part, "content", "") or "").startswith(DURABLE_MEMORY_MARKER)
        for part in getattr(message, "parts", []) or []
    )


def _durable_memory_index(messages: list[ModelMessage]) -> int | None:
    for idx, message in enumerate(messages):
        if _is_durable_memory(message):
            return idx
    return None


def _is_masked_message(message: ModelMessage) -> bool:
    return MASKED_OBSERVATION_MARKER in _messages_to_text([message])


def _build_durable_state(messages: list[ModelMessage]) -> DurableState:
    recent_text = _messages_to_text(messages[-20:])
    return DurableState(
        goal=_latest_user_text(messages)[:500],
        constraints=_extract_matching_lines(
            recent_text, ("must", "do not", "don't", "preserve", "without")
        ),
        accepted_decisions=_extract_matching_lines(
            recent_text, ("decided", "decision", "use ", "using ")
        ),
        invalidated_hypotheses=_extract_matching_lines(
            recent_text, ("not the", "isn't", "wasn't", "failed attempt", "dead end")
        ),
        validation_status=_extract_validation_status(messages),
        active_files=_extract_paths(recent_text)[:20],
        next_action=_latest_assistant_text(messages)[:500],
    )


def _latest_user_text(messages: list[ModelMessage]) -> str:
    idx = _latest_user_index(messages)
    if idx is None:
        return ""
    return _messages_to_text([messages[idx]])


def _latest_assistant_text(messages: list[ModelMessage]) -> str:
    for message in reversed(messages):
        if not isinstance(message, ModelResponse):
            continue
        text = _messages_to_text([message]).strip()
        if text:
            return text
    return ""


def _extract_validation_status(messages: list[ModelMessage]) -> dict[str, str]:
    for message in reversed(messages):
        text = _messages_to_text([message])
        if _SIGNAL_RE.search(text):
            return {
                "result": _status_from_text(text),
                "key_signal": _extract_key_signal(text),
            }
    return {}


def _latest_signal_index(messages: list[ModelMessage]) -> int | None:
    for idx in range(len(messages) - 1, -1, -1):
        if _is_durable_memory(messages[idx]):
            continue
        if _SIGNAL_RE.search(_messages_to_text([messages[idx]])):
            return idx
    return None


def _extract_matching_lines(text: str, needles: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    lowered_needles = tuple(needle.lower() for needle in needles)
    for raw_line in text.splitlines():
        line = raw_line.strip(" -\t")
        if not line:
            continue
        lowered = line.lower()
        if any(needle in lowered for needle in lowered_needles):
            found.append(line[:240])
        if len(found) >= 8:
            break
    return found


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, sort_keys=True, default=str)
    except TypeError:
        return str(content)


def _messages_to_text(messages: Iterable[Any]) -> str:
    chunks: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []) or []:
            if hasattr(part, "content"):
                chunks.append(_content_text(getattr(part, "content")))
            elif hasattr(part, "args"):
                chunks.append(_content_text(getattr(part, "args")))
    return "\n".join(chunk for chunk in chunks if chunk)


def _extract_paths(text: str) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for match in _PATH_RE.findall(text):
        if match not in seen:
            seen.add(match)
            paths.append(match)
    return paths


def _extract_key_signal(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line and _SIGNAL_RE.search(line):
            return line[:300]
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line:
            return line[:300]
    return "no textual signal"


def _status_from_text(text: str) -> str:
    return "failed" if _SIGNAL_RE.search(text) else "completed"
