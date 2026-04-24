"""Semantic task-state detection for continuity compaction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from code_puppy.config import get_continuity_compaction_semantic_task_detection
from code_puppy.summarization_agent import run_summarization_sync


@dataclass(slots=True)
class SemanticTaskState:
    current_task: str
    task_ledger: list[str]


def resolve_semantic_task_state(
    *,
    user_entries: list[tuple[int, str]],
    previous_current_task: str,
    previous_task_ledger: list[str],
    latest_user_request: str,
    fallback_current_task: str,
    fallback_task_ledger: list[str],
) -> SemanticTaskState | None:
    """Ask the summarization model to infer task state, or return None on failure."""
    if not get_continuity_compaction_semantic_task_detection():
        return None
    if not user_entries and not previous_task_ledger and not previous_current_task:
        return None

    prompt = _build_task_detection_prompt(
        user_entries=user_entries,
        previous_current_task=previous_current_task,
        previous_task_ledger=previous_task_ledger,
        latest_user_request=latest_user_request,
        fallback_current_task=fallback_current_task,
        fallback_task_ledger=fallback_task_ledger,
    )
    try:
        response_messages = run_summarization_sync(prompt, message_history=[])
        payload = _parse_json_object(_last_text(response_messages))
        return _coerce_semantic_task_state(payload)
    except Exception:
        return None


def _build_task_detection_prompt(
    *,
    user_entries: list[tuple[int, str]],
    previous_current_task: str,
    previous_task_ledger: list[str],
    latest_user_request: str,
    fallback_current_task: str,
    fallback_task_ledger: list[str],
) -> str:
    selected_entries = _selected_user_entries(user_entries)
    lines = [
        "Infer compact task memory for a long coding-assistant conversation.",
        "Return only a JSON object with this exact shape:",
        '{"current_task":"...","task_ledger":["..."]}',
        "",
        "Rules:",
        "- current_task is the active user objective, not merely the latest substep.",
        "- task_ledger is chronological task roots, not every user message.",
        "- Preserve the original/root task if it is available.",
        "- Include the active current task.",
        "- Omit routine follow-ups like run tests, continue, explain, or status unless they start a new objective.",
        "- Keep at most 16 ledger items and each item concise.",
        "- Do not invent task details not supported by the messages.",
        "",
        f"Previous current task: {_clip(previous_current_task, 500) or 'unknown'}",
        "Previous task ledger:",
        *_list_lines(previous_task_ledger),
        f"Latest user request: {_clip(latest_user_request, 500) or 'unknown'}",
        f"Deterministic fallback current task: {_clip(fallback_current_task, 500) or 'unknown'}",
        "Deterministic fallback task ledger:",
        *_list_lines(fallback_task_ledger),
        "",
        "User messages to inspect:",
    ]
    for idx, text in selected_entries:
        lines.append(f"[{idx}] {_clip(text, 700)}")
    return "\n".join(lines)


def _selected_user_entries(entries: list[tuple[int, str]]) -> list[tuple[int, str]]:
    if len(entries) <= 30:
        return entries
    return [entries[0], *entries[-29:]]


def _list_lines(items: Iterable[str]) -> list[str]:
    values = [_clip(item, 500) for item in items if str(item).strip()]
    if not values:
        return ["- none"]
    return [f"- {item}" for item in values]


def _clip(value: Any, limit: int) -> str:
    compacted = " ".join(str(value or "").split())
    return compacted[:limit]


def _last_text(messages: Any) -> str:
    if not isinstance(messages, list):
        return _message_text(messages)
    for message in reversed(messages):
        text = _message_text(message).strip()
        if text:
            return text
    return ""


def _message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    chunks: list[str] = []
    for part in getattr(message, "parts", []) or []:
        if hasattr(part, "content"):
            chunks.append(str(getattr(part, "content") or ""))
        elif hasattr(part, "args"):
            chunks.append(str(getattr(part, "args") or ""))
    if chunks:
        return "\n".join(chunks)
    if isinstance(message, dict):
        return json.dumps(message, sort_keys=True)
    return str(message or "")


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _strip_code_fence(stripped)
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for idx, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(stripped[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("semantic task detector did not return a JSON object")


def _strip_code_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _coerce_semantic_task_state(payload: dict[str, Any]) -> SemanticTaskState | None:
    current_task = _clip(payload.get("current_task"), 320)
    raw_ledger = payload.get("task_ledger")
    if not isinstance(raw_ledger, list):
        raw_ledger = []
    ledger = _dedupe(_clip(item, 320) for item in raw_ledger)
    if current_task and current_task.casefold() not in {
        item.casefold() for item in ledger
    }:
        ledger.append(current_task)
    ledger = _trim_ledger(ledger, 16)
    if not current_task and ledger:
        current_task = ledger[-1]
    if not current_task:
        return None
    return SemanticTaskState(current_task=current_task, task_ledger=ledger)


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = _clip(item, 320)
        key = " ".join(value.casefold().split())
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _trim_ledger(entries: list[str], limit: int) -> list[str]:
    if len(entries) <= limit:
        return entries
    if limit <= 1:
        return entries[-limit:]
    return [entries[0], *entries[-(limit - 1) :]]
