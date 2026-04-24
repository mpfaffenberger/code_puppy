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
    ArchiveSignal,
    DurableState,
    TaskMemory,
    archive_observation,
    archive_signal_from_record,
    build_archive_index,
    cleanup_observation_archives,
    read_durable_state,
    render_durable_state,
    render_masked_observation,
    search_archive_index,
    write_durable_state,
)
from code_puppy.agents.continuity_compaction.task_detection import (
    SemanticMemoryState,
    resolve_semantic_task_state as _legacy_resolve_semantic_task_state,
    resolve_semantic_memory_state,
)
from code_puppy.config import get_continuity_compaction_semantic_task_detection
from code_puppy.messaging import emit_info, emit_success, emit_warning

_TOOL_CALL_KINDS = {"tool-call", "builtin-tool-call"}
_TOOL_RETURN_KINDS = {"tool-return", "builtin-tool-return"}
_MESSAGE_GROUP = "token_context_status"
_TASK_LEDGER_LIMIT = 16
_TASK_TEXT_LIMIT = 320
_TARGET_RUNWAY_TURNS = 4
_TARGET_BAND_BELOW_RATIO = 0.05
_TARGET_BAND_ABOVE_RATIO = 0.10
resolve_semantic_task_state = _legacy_resolve_semantic_task_state
_PATH_RE = re.compile(
    r"(?:\.{0,2}/|/)?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*"
    r"\.(?:py|pyi|js|jsx|ts|tsx|json|toml|yaml|yml|md|txt|go|rs|java|c|cc|cpp|h|hpp|css|html)"
)
_SIGNAL_RE = re.compile(
    r"(error|failed|failure|exception|traceback|assertion|exit code|exit_code)",
    re.IGNORECASE,
)
_TASK_START_RE = re.compile(
    r"\b("
    r"new task|switch(?:ing)? tasks?|different task|separate task|"
    r"now (?:let'?s|we need|i want|i need)|"
    r"let'?s (?:build|create|implement|add|fix|investigate|rework|rename|"
    r"configure|set up|do|make)|"
    r"please (?:build|create|implement|add|fix|investigate|rework|rename|"
    r"configure|set up|make)|"
    r"can you (?:please )?(?:build|create|implement|add|fix|investigate|"
    r"rework|rename|configure|set up|make)|"
    r"i (?:want|would like|need) (?:you to|to)|"
    r"we need to"
    r")\b",
    re.IGNORECASE,
)


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

    if not _should_compact(
        force=force,
        current_tokens=current_tokens,
        predicted_growth=predicted_growth,
        settings=settings,
    ):
        _set_previous_total(agent, current_tokens)
        return input_messages, []

    settings = dataclasses.replace(
        settings,
        target_after_compaction=_effective_target_after_compaction(
            settings, predicted_growth
        ),
    )
    _emit_compaction_start(
        current_tokens=current_tokens,
        predicted_growth=predicted_growth,
        settings=settings,
        model_max=model_max,
        force=force,
    )

    cleanup_observation_archives(agent, settings)
    keep_indices = _build_keep_indices(messages, settings, model_name)
    messages, masked_count = _archive_and_mask(
        messages, keep_indices, agent, settings, model_name
    )
    archive_index = build_archive_index(agent)
    durable_state = _build_durable_state(agent, messages, settings, archive_index)
    write_durable_state(agent, durable_state)
    messages = _inject_durable_memory(messages, durable_state)
    compacted_tokens = _history_tokens(messages, model_name) + context_overhead

    summarized_count = 0
    if compacted_tokens > settings.target_after_compaction:
        keep_indices = _build_keep_indices(messages, settings, model_name)
        messages, summarized_count = _summarize_oldest_masked_band(
            messages, keep_indices, settings, model_name, context_overhead
        )
        compacted_tokens = _history_tokens(messages, model_name) + context_overhead

    target_trimmed_count = 0
    emergency_trimmed_count = 0
    if compacted_tokens > settings.target_after_compaction:
        before_trim_len = len(messages)
        emergency_trim = compacted_tokens > settings.emergency_trigger
        messages = _trim_to_target(messages, settings, model_name)
        trimmed_count = max(0, before_trim_len - len(messages))
        if emergency_trim:
            emergency_trimmed_count = trimmed_count
        else:
            target_trimmed_count = trimmed_count
        compacted_tokens = _history_tokens(messages, model_name) + context_overhead

    messages = prune_interrupted_tool_calls(messages)
    _set_previous_total(agent, compacted_tokens)
    result_hashes = {hash_message(message) for message in messages}
    dropped = [
        message
        for message in original_messages
        if hash_message(message) not in result_hashes
    ]
    _emit_compaction_complete(
        before_tokens=current_tokens,
        after_tokens=compacted_tokens,
        model_max=model_max,
        before_messages=len(original_messages),
        after_messages=len(messages),
        masked_count=masked_count,
        summarized_count=summarized_count,
        target_trimmed_count=target_trimmed_count,
        emergency_trimmed_count=emergency_trimmed_count,
        semantic_status=durable_state.semantic_status,
    )
    return messages, dropped


def _history_tokens(messages: Iterable[ModelMessage], model_name: str | None) -> int:
    return sum(estimate_tokens_for_message(message, model_name) for message in messages)


def _should_compact(
    *,
    force: bool,
    current_tokens: int,
    predicted_growth: int,
    settings: ContinuityCompactionSettings,
) -> bool:
    if force:
        return True
    if current_tokens >= settings.soft_trigger:
        return True
    if current_tokens < settings.predictive_trigger_floor:
        return False
    return current_tokens + predicted_growth >= settings.soft_trigger


def _effective_target_after_compaction(
    settings: ContinuityCompactionSettings, predicted_growth: int
) -> int:
    """Choose a dynamic target near the configured ratio with growth-based runway."""
    context_window = max(1, settings.context_window)
    configured_target = max(1, settings.target_after_compaction)
    lower_band = configured_target - int(
        round(context_window * _TARGET_BAND_BELOW_RATIO)
    )
    upper_band = configured_target + int(
        round(context_window * _TARGET_BAND_ABOVE_RATIO)
    )
    lower_bound = max(
        1,
        lower_band,
        settings.recent_raw_floor + settings.predicted_growth_floor,
    )
    upper_bound = max(
        lower_bound,
        min(settings.soft_trigger - settings.predicted_growth_floor, upper_band),
    )
    runway_target = settings.soft_trigger - (
        max(predicted_growth, settings.predicted_growth_floor) * _TARGET_RUNWAY_TURNS
    )
    return max(lower_bound, min(upper_bound, runway_target))


def _emit_compaction_start(
    *,
    current_tokens: int,
    predicted_growth: int,
    settings: ContinuityCompactionSettings,
    model_max: int,
    force: bool,
) -> None:
    trigger = "forced" if force else "triggered"
    current = _format_context_use(current_tokens, model_max)
    predicted = _format_context_delta(predicted_growth, model_max)
    target = _format_context_use(settings.target_after_compaction, model_max)
    emit_info(
        "Continuity compaction "
        f"{trigger} at {current} context "
        f"(predicted next turn +{predicted}); target {target}. "
        "Preserving recent context and archiving older bulky observations.",
        message_group=_MESSAGE_GROUP,
    )


def _emit_compaction_complete(
    *,
    before_tokens: int,
    after_tokens: int,
    model_max: int,
    before_messages: int,
    after_messages: int,
    masked_count: int,
    summarized_count: int,
    target_trimmed_count: int,
    emergency_trimmed_count: int,
    semantic_status: str,
) -> None:
    actions = (
        [f"archived and masked {masked_count} observation(s)"]
        if masked_count
        else ["no bulky observations required masking"]
    )
    if summarized_count:
        actions.append(f"summarized {summarized_count} old masked message(s)")
    if target_trimmed_count:
        actions.append(f"trimmed {target_trimmed_count} older message(s) to target")
    if emergency_trimmed_count:
        actions.append(f"emergency-trimmed {emergency_trimmed_count} message(s)")
    if semantic_status == "semantic":
        actions.append("semantic memory updated")
    elif semantic_status == "fallback":
        actions.append("semantic memory fallback used")
    elif semantic_status == "disabled":
        actions.append("semantic memory disabled")
    if (
        not summarized_count
        and not target_trimmed_count
        and not emergency_trimmed_count
    ):
        actions.append("kept the recent raw tail intact")

    emit_success(
        "Continuity compaction complete: "
        f"{_format_context_use(before_tokens, model_max)} -> "
        f"{_format_context_use(after_tokens, model_max)} context, "
        f"{before_messages} -> {after_messages} messages; " + "; ".join(actions) + ".",
        message_group=_MESSAGE_GROUP,
    )


def _format_context_use(tokens: int, model_max: int) -> str:
    if model_max <= 0:
        return f"{tokens:,} tokens"
    return f"{tokens / model_max:.1%}"


def _format_context_delta(tokens: int, model_max: int) -> str:
    if model_max <= 0:
        return f"{tokens:,} tokens"
    return f"{tokens / model_max:.1%}"


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
) -> tuple[list[ModelMessage], int]:
    result: list[ModelMessage] = []
    masked_count = 0
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
                key_signals=_extract_key_signals(content),
                affected_files=_extract_paths(content),
                status=_status_from_text(content),
            )
            new_parts.append(
                dataclasses.replace(part, content=render_masked_observation(record))
            )
            masked_count += 1
            changed = True
        result.append(
            dataclasses.replace(message, parts=new_parts) if changed else message
        )
    return result, masked_count


def _summarize_oldest_masked_band(
    messages: list[ModelMessage],
    keep_indices: set[int],
    settings: ContinuityCompactionSettings,
    model_name: str | None,
    context_overhead: int,
) -> tuple[list[ModelMessage], int]:
    current = _history_tokens(messages, model_name) + context_overhead
    needed = max(1, current - settings.target_after_compaction)
    eligible_masked: list[int] = []
    for idx, message in enumerate(messages):
        if idx in keep_indices or not _is_masked_message(message):
            continue
        pair_indices = _expand_tool_pair_indices(messages, {idx})
        if pair_indices & keep_indices:
            continue
        eligible_masked.append(idx)
    if not eligible_masked:
        return messages, 0
    if len(eligible_masked) == 1:
        tolerance = max(settings.recent_raw_floor, settings.predicted_growth_floor)
        if current <= settings.target_after_compaction + tolerance:
            return messages, 0

    preserve_masked_idx = max(eligible_masked)
    selected: list[int] = []
    selected_tokens = 0
    for idx in eligible_masked:
        if len(eligible_masked) > 1 and idx == preserve_masked_idx:
            continue
        selected.append(idx)
        selected_tokens += estimate_tokens_for_message(messages[idx], model_name)
        if selected_tokens >= needed:
            break
    if not selected:
        return messages, 0

    drop_indices = _expand_tool_pair_indices(messages, set(selected))
    drop_indices.discard(0)
    if not drop_indices:
        return messages, 0
    summary_input = _messages_to_text(messages[idx] for idx in sorted(drop_indices))
    summary_text = _build_structured_masked_summary(summary_input)

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
    return rebuilt, len(drop_indices)


def _build_structured_masked_summary(summary_input: str) -> str:
    """Build a deterministic summary for already-masked observation capsules."""
    lines = [line.strip() for line in summary_input.splitlines() if line.strip()]
    values = _masked_summary_values(lines)

    observations = max(1, summary_input.count(MASKED_OBSERVATION_MARKER))
    validation_status = []
    for status in values["result"] or values["status"]:
        validation_status.append(status)
    for signal in values["key_signal"]:
        validation_status.append(signal)

    active_files: list[str] = []
    for files_line in values["files"]:
        active_files.extend(item.strip() for item in files_line.split(","))
    active_files.extend(_extract_paths(summary_input))

    important_decisions = [
        line
        for line in lines
        if line.lower().startswith("decision:")
        or " next action:" in line.lower()
        or "not the root cause" in line.lower()
    ]

    verified_facts = [
        f"Summarized {observations} already-masked observation(s).",
        *[f"Tool: {tool}" for tool in values["tool"]],
        *[f"Observation id: {obs_id}" for obs_id in values["id"]],
    ]

    sections = [
        ("Goal", []),
        ("Hard Constraints", []),
        ("Verified Facts", verified_facts),
        ("Invalidated Hypotheses", _extract_invalidated_hypotheses(lines)),
        ("Important Decisions", important_decisions),
        ("Validation Status", validation_status),
        ("Active Files", active_files),
        ("Next Action", _extract_next_actions(lines)),
        ("Archive References", values["full_log_ref"]),
    ]
    rendered: list[str] = []
    for title, items in sections:
        rendered.append(title)
        deduped = _dedupe_nonempty(items, limit=12)
        if deduped:
            rendered.extend(f"- {item}" for item in deduped)
        else:
            rendered.append("- Not present in selected masked observations.")
    return "\n".join(rendered)


def _masked_summary_values(lines: list[str]) -> dict[str, list[str]]:
    keys = {
        "id",
        "tool",
        "result",
        "status",
        "key_signal",
        "files",
        "full_log_ref",
    }
    values: dict[str, list[str]] = {key: [] for key in keys}
    for line in lines:
        key, separator, value = line.partition(":")
        normalized = key.strip().lower()
        if separator and normalized in values:
            values[normalized].append(value.strip())
    return values


def _extract_invalidated_hypotheses(lines: list[str]) -> list[str]:
    hypotheses: list[str] = []
    marker = " is not the root cause"
    for line in lines:
        lowered = line.lower()
        if marker in lowered:
            prefix = line[: lowered.index(marker)].strip()
            if prefix.lower().startswith("decision:"):
                prefix = prefix[len("decision:") :].strip()
            if prefix:
                hypotheses.append(prefix)
    return hypotheses


def _extract_next_actions(lines: list[str]) -> list[str]:
    actions: list[str] = []
    marker = "next action:"
    for line in lines:
        lowered = line.lower()
        if marker in lowered:
            actions.append(line[lowered.index(marker) + len(marker) :].strip())
    return actions


def _dedupe_nonempty(items: Iterable[str], limit: int) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value[:300])
        if len(deduped) >= limit:
            break
    return deduped


def _trim_to_target(
    messages: list[ModelMessage],
    settings: ContinuityCompactionSettings,
    model_name: str | None,
) -> list[ModelMessage]:
    if len(messages) <= 1:
        return messages
    keep = {0} if _is_system_anchor_message(messages[0]) else set()
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


def _build_durable_state(
    agent: Any,
    messages: list[ModelMessage],
    settings: ContinuityCompactionSettings,
    archive_index: list[dict[str, Any]],
) -> DurableState:
    recent_text = _messages_to_text(messages[-20:])
    previous = read_durable_state(agent)
    user_entries = _user_text_entries(messages)
    latest_user_request = _latest_user_text(messages)[:500]
    current_task = _select_current_task(user_entries, previous, latest_user_request)
    task_ledger = _build_task_ledger(user_entries, previous, current_task)
    fallback_state = _deterministic_durable_state(
        previous=previous,
        current_task=current_task,
        latest_user_request=latest_user_request,
        task_ledger=task_ledger,
        recent_text=recent_text,
        messages=messages,
        settings=settings,
    )

    semantic_state, semantic_error = _semantic_memory_state(
        user_entries=user_entries,
        previous=previous,
        latest_user_request=latest_user_request,
        fallback_state=fallback_state,
        archive_index=archive_index,
        messages=messages,
        settings=settings,
    )
    if semantic_state is not None:
        state = _state_from_semantic(
            previous=previous,
            fallback_state=fallback_state,
            semantic_state=semantic_state,
            settings=settings,
        )
    else:
        state = fallback_state
        if get_continuity_compaction_semantic_task_detection():
            state.semantic_status = "fallback"
            state.semantic_error = semantic_error or (
                "semantic memory unavailable; deterministic extraction used"
            )
        else:
            state.semantic_status = "disabled"

    state.retrieved_archive_signals = _retrieve_archive_signals(
        agent=agent,
        state=state,
        archive_index=archive_index,
        settings=settings,
        semantic_state=semantic_state,
    )
    return state


def _deterministic_durable_state(
    *,
    previous: DurableState | None,
    current_task: str,
    latest_user_request: str,
    task_ledger: list[str],
    recent_text: str,
    messages: list[ModelMessage],
    settings: ContinuityCompactionSettings,
) -> DurableState:
    current_constraints = _extract_matching_lines(
        recent_text, ("must", "do not", "don't", "preserve", "without")
    )
    global_constraints = _dedupe_nonempty(
        [
            *(previous.global_constraints if previous is not None else []),
            *_extract_matching_lines(
                recent_text, ("global", "for all tasks", "session-wide")
            ),
        ],
        limit=16,
    )
    active_files = _extract_paths(recent_text)[:20]
    tasks = _fallback_tasks(
        previous=previous,
        task_ledger=task_ledger,
        current_task=current_task,
        current_constraints=current_constraints,
        active_files=active_files,
        settings=settings,
    )
    current_task_id = _current_task_id(tasks, current_task)
    return DurableState(
        goal=current_task or latest_user_request,
        constraints=current_constraints,
        accepted_decisions=_extract_matching_lines(
            recent_text, ("decided", "decision", "use ", "using ")
        ),
        invalidated_hypotheses=_extract_matching_lines(
            recent_text, ("not the", "isn't", "wasn't", "failed attempt", "dead end")
        ),
        validation_status=_extract_validation_status(messages),
        active_files=active_files,
        next_action=_latest_assistant_text(messages)[:500],
        current_task=current_task,
        latest_user_request=latest_user_request,
        task_ledger=_trim_task_ledger(task_ledger, _TASK_LEDGER_LIMIT),
        tasks=tasks,
        current_task_id=current_task_id,
        original_root_task_id=_original_root_task_id(previous, tasks),
        global_constraints=global_constraints,
        semantic_status="deterministic",
    )


def _semantic_memory_state(
    *,
    user_entries: list[tuple[int, str]],
    previous: DurableState | None,
    latest_user_request: str,
    fallback_state: DurableState,
    archive_index: list[dict[str, Any]],
    messages: list[ModelMessage],
    settings: ContinuityCompactionSettings,
) -> tuple[SemanticMemoryState | None, str]:
    if not get_continuity_compaction_semantic_task_detection():
        return None, "semantic memory disabled"

    emit_info(
        "Continuity memory update: calling semantic memory model "
        f"(timeout {settings.semantic_timeout_seconds}s).",
        message_group=_MESSAGE_GROUP,
    )
    errors: list[str] = []
    try:
        semantic_state = resolve_semantic_memory_state(
            user_entries=user_entries,
            previous_state=previous,
            latest_user_request=latest_user_request,
            fallback_state=fallback_state,
            archive_index=archive_index,
            transcript_snippets=_transcript_snippets(messages),
            allowed_files=_allowed_files(fallback_state, archive_index),
            timeout_seconds=settings.semantic_timeout_seconds,
            error_sink=errors,
        )
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {str(exc).strip() or 'failed'}")
        semantic_state = None

    if semantic_state is None:
        reason = errors[-1] if errors else "semantic model returned no usable memory"
        emit_warning(
            "Continuity memory update: semantic memory unavailable "
            f"({reason}); using deterministic fallback.",
            message_group=_MESSAGE_GROUP,
        )
        return None, reason

    emit_success(
        "Continuity memory update: semantic memory refreshed "
        f"({len(semantic_state.tasks)} task(s), "
        f"{len(semantic_state.archive_queries)} archive hint(s)).",
        message_group=_MESSAGE_GROUP,
    )
    return semantic_state, ""


def _state_from_semantic(
    *,
    previous: DurableState | None,
    fallback_state: DurableState,
    semantic_state: SemanticMemoryState,
    settings: ContinuityCompactionSettings,
) -> DurableState:
    tasks = _merge_task_memories(
        previous.tasks if previous is not None else fallback_state.tasks,
        semantic_state.tasks,
        semantic_state.current_task,
        semantic_state.current_task_id,
        settings.task_retention_count,
    )
    current_task_id = semantic_state.current_task_id or _current_task_id(
        tasks, semantic_state.current_task
    )
    current_task = (
        _task_title_by_id(tasks, current_task_id) or semantic_state.current_task
    )
    task_ledger = _trim_task_ledger(
        _dedupe_task_entries(
            [
                *(previous.task_ledger if previous is not None else []),
                *semantic_state.task_ledger,
                current_task,
            ]
        ),
        _TASK_LEDGER_LIMIT,
    )
    active_files = _dedupe_nonempty(
        [*fallback_state.active_files, *semantic_state.active_files],
        limit=20,
    )
    return DurableState(
        goal=current_task or fallback_state.goal,
        constraints=_current_task_constraints(tasks, current_task_id)
        or fallback_state.constraints,
        accepted_decisions=_dedupe_nonempty(
            [
                *fallback_state.accepted_decisions,
                *semantic_state.accepted_decisions,
            ],
            limit=24,
        ),
        invalidated_hypotheses=_dedupe_nonempty(
            [
                *fallback_state.invalidated_hypotheses,
                *semantic_state.invalidated_hypotheses,
            ],
            limit=16,
        ),
        validation_status=semantic_state.validation_status
        or fallback_state.validation_status,
        active_files=active_files,
        next_action=semantic_state.next_action or fallback_state.next_action,
        current_task=current_task,
        latest_user_request=fallback_state.latest_user_request,
        task_ledger=task_ledger,
        tasks=tasks,
        current_task_id=current_task_id,
        original_root_task_id=_original_root_task_id(previous, tasks),
        global_constraints=_dedupe_nonempty(
            [*fallback_state.global_constraints, *semantic_state.global_constraints],
            limit=24,
        ),
        semantic_status="semantic",
    )


def _fallback_tasks(
    *,
    previous: DurableState | None,
    task_ledger: list[str],
    current_task: str,
    current_constraints: list[str],
    active_files: list[str],
    settings: ContinuityCompactionSettings,
) -> list[TaskMemory]:
    tasks = [
        dataclasses.replace(task)
        for task in (previous.tasks if previous is not None else [])
        if task.title
    ]
    if not tasks:
        for idx, title in enumerate(task_ledger, start=1):
            tasks.append(
                TaskMemory(
                    task_id=_task_id_from_text(title, idx),
                    title=title,
                    status="unknown",
                )
            )
    current_key = _task_key(current_task)
    current_task_memory = next(
        (task for task in tasks if _task_key(task.title) == current_key),
        None,
    )
    if current_task and current_task_memory is None:
        current_task_memory = TaskMemory(
            task_id=_task_id_from_text(current_task, len(tasks) + 1),
            title=current_task,
        )
        tasks.append(current_task_memory)

    if current_task_memory is not None:
        for task in tasks:
            if task.task_id == current_task_memory.task_id:
                task.status = "active"
                task.constraints = _dedupe_nonempty(
                    [*task.constraints, *current_constraints], limit=12
                )
                task.active_files = _dedupe_nonempty(
                    [*task.active_files, *active_files], limit=20
                )
            elif task.status == "active":
                task.status = "superseded"

    return _retain_tasks(tasks, settings.task_retention_count)


def _merge_task_memories(
    base_tasks: list[TaskMemory],
    semantic_tasks: list[TaskMemory],
    current_task: str,
    current_task_id: str,
    retention_count: int,
) -> list[TaskMemory]:
    merged: list[TaskMemory] = [dataclasses.replace(task) for task in base_tasks]
    by_id = {task.task_id: idx for idx, task in enumerate(merged)}
    by_title = {_task_key(task.title): idx for idx, task in enumerate(merged)}
    for task in semantic_tasks:
        semantic_copy = dataclasses.replace(task)
        if semantic_copy.task_id in by_id:
            merged[by_id[semantic_copy.task_id]] = semantic_copy
            continue
        title_key = _task_key(semantic_copy.title)
        if title_key in by_title:
            merged[by_title[title_key]] = semantic_copy
            continue
        merged.append(semantic_copy)
        by_id[semantic_copy.task_id] = len(merged) - 1
        by_title[title_key] = len(merged) - 1

    resolved_current_id = current_task_id or _current_task_id(merged, current_task)
    if resolved_current_id:
        for task in merged:
            if task.task_id == resolved_current_id:
                task.status = "active"
            elif task.status == "active":
                task.status = "superseded"
    return _retain_tasks(merged, retention_count)


def _retain_tasks(tasks: list[TaskMemory], retention_count: int) -> list[TaskMemory]:
    retention_count = max(1, retention_count)
    if len(tasks) <= retention_count:
        return tasks
    root = tasks[0]
    active = next((task for task in tasks if task.status == "active"), None)
    blocked = [task for task in tasks if task.status == "blocked"]
    selected: list[TaskMemory] = []

    def add(task: TaskMemory | None) -> None:
        if task is None:
            return
        if any(existing.task_id == task.task_id for existing in selected):
            return
        selected.append(task)

    add(root)
    add(active)
    for task in blocked:
        add(task)
    for task in reversed(tasks):
        add(task)
        if len(selected) >= retention_count:
            break
    selected = selected[:retention_count]
    selected.sort(key=lambda task: tasks.index(task) if task in tasks else len(tasks))
    return selected


def _retrieve_archive_signals(
    *,
    agent: Any,
    state: DurableState,
    archive_index: list[dict[str, Any]],
    settings: ContinuityCompactionSettings,
    semantic_state: SemanticMemoryState | None,
) -> list[ArchiveSignal]:
    if not settings.archive_retrieval_enabled or settings.archive_retrieval_count <= 0:
        return []
    queries = _dedupe_nonempty(
        [
            state.current_task,
            state.latest_user_request,
            *state.active_files,
            *(semantic_state.archive_queries if semantic_state is not None else []),
        ],
        limit=16,
    )
    if not queries:
        return []

    index_ids = {str(item.get("observation_id") or "") for item in archive_index}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries:
        for record in search_archive_index(
            agent, query, limit=settings.archive_retrieval_count
        ):
            obs_id = str(record.get("observation_id") or "")
            if not obs_id or obs_id in seen or obs_id not in index_ids:
                continue
            selected.append(record)
            seen.add(obs_id)
            if len(selected) >= settings.archive_retrieval_count:
                return [archive_signal_from_record(item) for item in selected]
    return [archive_signal_from_record(item) for item in selected]


def _transcript_snippets(messages: list[ModelMessage]) -> list[str]:
    snippets: list[str] = []
    for message in messages[-30:]:
        text = _messages_to_text([message]).strip()
        if text:
            snippets.append(text[:1000])
    return snippets


def _allowed_files(
    fallback_state: DurableState, archive_index: list[dict[str, Any]]
) -> list[str]:
    files = [*fallback_state.active_files]
    for task in fallback_state.tasks:
        files.extend(task.active_files)
    for item in archive_index:
        files.extend(str(path) for path in item.get("affected_files") or [])
    return _dedupe_nonempty(files, limit=100)


def _current_task_id(tasks: list[TaskMemory], current_task: str) -> str:
    current_key = _task_key(current_task)
    for task in reversed(tasks):
        if _task_key(task.title) == current_key:
            return task.task_id
    active = next((task for task in tasks if task.status == "active"), None)
    return active.task_id if active is not None else ""


def _task_title_by_id(tasks: list[TaskMemory], task_id: str) -> str:
    for task in tasks:
        if task.task_id == task_id:
            return task.title
    return ""


def _current_task_constraints(tasks: list[TaskMemory], task_id: str) -> list[str]:
    for task in tasks:
        if task.task_id == task_id:
            return task.constraints
    return []


def _original_root_task_id(
    previous: DurableState | None, tasks: list[TaskMemory]
) -> str:
    if previous is not None and previous.original_root_task_id:
        return previous.original_root_task_id
    return tasks[0].task_id if tasks else ""


def _task_id_from_text(text: str, idx: int) -> str:
    raw = re.sub(r"[^A-Za-z0-9_.-]+", "-", _compact_task_text(text).casefold())
    return (raw.strip("-")[:72] or f"task-{idx}") + f"-{idx}"


def _user_text_entries(messages: list[ModelMessage]) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    for idx, message in enumerate(messages):
        if _is_durable_memory(message):
            continue
        text = _user_prompt_text(message).strip()
        if not text:
            continue
        entries.append((idx, text))
    return entries


def _select_current_task(
    user_entries: list[tuple[int, str]],
    previous: DurableState | None,
    latest_user_request: str,
) -> str:
    previous_task = ""
    if previous is not None:
        previous_task = previous.current_task or previous.goal

    candidates = _task_root_candidates(user_entries)
    if candidates:
        latest_candidate = _compact_task_text(candidates[-1])
        if (
            previous_task
            and _task_key(latest_candidate) == _task_key(previous_task)
            and not _is_task_start(latest_user_request)
        ):
            return _compact_task_text(previous_task)
        return latest_candidate
    if previous_task:
        return _compact_task_text(previous_task)
    return _compact_task_text(latest_user_request)


def _build_task_ledger(
    user_entries: list[tuple[int, str]],
    previous: DurableState | None,
    current_task: str,
) -> list[str]:
    if previous is not None and previous.tasks:
        ledger = [task.title for task in previous.tasks]
    else:
        ledger = list(previous.task_ledger) if previous is not None else []
    for candidate in _task_root_candidates(user_entries):
        ledger.append(_compact_task_text(candidate))
    if current_task:
        ledger.append(_compact_task_text(current_task))
    return _dedupe_task_entries(ledger)


def _task_root_candidates(user_entries: list[tuple[int, str]]) -> list[str]:
    candidates: list[str] = []
    for offset, (_idx, text) in enumerate(user_entries):
        if offset == 0 or _is_task_start(text):
            candidates.append(text)
    return candidates


def _is_task_start(text: str) -> bool:
    return bool(_TASK_START_RE.search(text or ""))


def _compact_task_text(text: str) -> str:
    compacted = " ".join(str(text or "").split())
    return compacted[:_TASK_TEXT_LIMIT]


def _dedupe_task_entries(entries: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for entry in entries:
        value = _compact_task_text(entry)
        key = _task_key(value)
        if not value or key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _task_key(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _trim_task_ledger(entries: list[str], limit: int) -> list[str]:
    if len(entries) <= limit:
        return entries
    if limit <= 1:
        return entries[-limit:]
    return [entries[0], *entries[-(limit - 1) :]]


def _latest_user_text(messages: list[ModelMessage]) -> str:
    idx = _latest_user_index(messages)
    if idx is None:
        return ""
    return _user_prompt_text(messages[idx])


def _user_prompt_text(message: ModelMessage) -> str:
    chunks: list[str] = []
    for part in getattr(message, "parts", []) or []:
        if getattr(part, "part_kind", None) == "user-prompt":
            chunks.append(_content_text(getattr(part, "content", "")))
    return "\n".join(chunk for chunk in chunks if chunk)


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


def _is_system_anchor_message(message: ModelMessage) -> bool:
    return any(
        getattr(part, "part_kind", None) == "system-prompt"
        for part in getattr(message, "parts", []) or []
    )


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


def _extract_key_signals(text: str) -> list[str]:
    signals: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line and (_SIGNAL_RE.search(line) or _PATH_RE.search(line)):
            signals.append(line[:300])
        if len(signals) >= 8:
            break
    if not signals:
        first = _extract_key_signal(text)
        if first:
            signals.append(first)
    return _dedupe_nonempty(signals, limit=8)


def _status_from_text(text: str) -> str:
    return "failed" if _SIGNAL_RE.search(text) else "completed"
