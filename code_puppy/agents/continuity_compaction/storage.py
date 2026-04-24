"""Local durable continuity and observation archive helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from code_puppy.agents.continuity_compaction.settings import (
    ContinuityCompactionSettings,
)

DURABLE_MEMORY_MARKER = "[Code Puppy Durable Compaction Memory]"
MASKED_OBSERVATION_MARKER = "[Masked Observation]"
STRUCTURED_SUMMARY_MARKER = "[Code Puppy Structured Compaction Summary]"
CURRENT_SCHEMA_VERSION = 2
TASK_STATUSES = {
    "active",
    "completed",
    "blocked",
    "superseded",
    "abandoned",
    "unknown",
}
PROMPT_TASK_LIMIT = 16


@dataclass(slots=True)
class TaskMemory:
    task_id: str
    title: str
    status: str = "unknown"
    summary: str = ""
    constraints: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    validation_status: dict[str, str] = field(default_factory=dict)
    active_files: list[str] = field(default_factory=list)
    archive_refs: list[str] = field(default_factory=list)
    last_seen: str = ""


@dataclass(slots=True)
class ArchiveSignal:
    observation_id: str
    tool_name: str = "unknown"
    status: str = "unknown"
    key_signals: list[str] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    local_ref: str = ""
    token_count: int = 0
    checksum: str = ""
    timestamp: str = ""


@dataclass(slots=True)
class DurableState:
    schema_version: int = CURRENT_SCHEMA_VERSION
    goal: str = ""
    constraints: list[str] = field(default_factory=list)
    accepted_decisions: list[str] = field(default_factory=list)
    invalidated_hypotheses: list[str] = field(default_factory=list)
    validation_status: dict[str, str] = field(default_factory=dict)
    active_files: list[str] = field(default_factory=list)
    next_action: str = ""
    current_task: str = ""
    latest_user_request: str = ""
    task_ledger: list[str] = field(default_factory=list)
    tasks: list[TaskMemory] = field(default_factory=list)
    current_task_id: str = ""
    original_root_task_id: str = ""
    global_constraints: list[str] = field(default_factory=list)
    retrieved_archive_signals: list[ArchiveSignal] = field(default_factory=list)
    semantic_status: str = "deterministic"
    semantic_error: str = ""


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return cleaned[:96] or "default"


def session_key(agent: Any) -> str:
    if agent is None:
        return "default"
    raw = (
        getattr(agent, "session_id", None)
        or getattr(agent, "id", None)
        or getattr(agent, "name", None)
        or "default"
    )
    return _safe_segment(str(raw))


def session_dir(agent: Any) -> Path:
    from code_puppy import config as cp_config

    path = Path(cp_config.DATA_DIR) / "compaction" / session_key(agent)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def observations_dir(agent: Any) -> Path:
    path = session_dir(agent) / "observations"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def durable_state_path(agent: Any) -> Path:
    return session_dir(agent) / "durable_state.json"


def write_durable_state(agent: Any, state: DurableState) -> Path:
    path = durable_state_path(agent)
    tmp_path = path.with_suffix(".tmp")
    payload = asdict(state)
    payload["schema_version"] = CURRENT_SCHEMA_VERSION
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    tmp_path.replace(path)
    return path


def read_durable_state(agent: Any) -> DurableState | None:
    path = durable_state_path(agent)
    try:
        with path.open(encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    try:
        schema_version = int(payload.get("schema_version") or 1)
    except (TypeError, ValueError):
        schema_version = 1
    if schema_version < CURRENT_SCHEMA_VERSION:
        return _migrate_v1_state(payload)

    goal = str(payload.get("goal") or "")
    current_task = str(payload.get("current_task") or goal)
    latest_user_request = str(payload.get("latest_user_request") or goal)
    tasks = _as_task_memory_list(payload.get("tasks"))
    if not tasks:
        tasks = _tasks_from_legacy_ledger(
            _as_string_list(payload.get("task_ledger")),
            current_task,
            [],
        )
    current_task_id = str(payload.get("current_task_id") or "")
    if not current_task_id:
        current_task_id = _task_id_for_title(tasks, current_task)
    original_root_task_id = str(payload.get("original_root_task_id") or "")
    if not original_root_task_id and tasks:
        original_root_task_id = tasks[0].task_id
    return DurableState(
        schema_version=CURRENT_SCHEMA_VERSION,
        goal=goal,
        constraints=_as_string_list(payload.get("constraints")),
        accepted_decisions=_as_string_list(payload.get("accepted_decisions")),
        invalidated_hypotheses=_as_string_list(payload.get("invalidated_hypotheses")),
        validation_status=_as_string_dict(payload.get("validation_status")),
        active_files=_as_string_list(payload.get("active_files")),
        next_action=str(payload.get("next_action") or ""),
        current_task=current_task,
        latest_user_request=latest_user_request,
        task_ledger=_as_string_list(payload.get("task_ledger")),
        tasks=tasks,
        current_task_id=current_task_id,
        original_root_task_id=original_root_task_id,
        global_constraints=_as_string_list(payload.get("global_constraints")),
        retrieved_archive_signals=_as_archive_signal_list(
            payload.get("retrieved_archive_signals")
        ),
        semantic_status=str(payload.get("semantic_status") or "deterministic"),
        semantic_error=str(payload.get("semantic_error") or ""),
    )


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _as_string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _migrate_v1_state(payload: dict[str, Any]) -> DurableState:
    goal = str(payload.get("goal") or "")
    current_task = str(payload.get("current_task") or goal)
    latest_user_request = str(payload.get("latest_user_request") or goal)
    constraints = _as_string_list(payload.get("constraints"))
    task_ledger = _as_string_list(payload.get("task_ledger"))
    tasks = _tasks_from_legacy_ledger(task_ledger, current_task, constraints)
    current_task_id = _task_id_for_title(tasks, current_task)
    return DurableState(
        schema_version=CURRENT_SCHEMA_VERSION,
        goal=goal,
        constraints=constraints,
        accepted_decisions=_as_string_list(payload.get("accepted_decisions")),
        invalidated_hypotheses=_as_string_list(payload.get("invalidated_hypotheses")),
        validation_status=_as_string_dict(payload.get("validation_status")),
        active_files=_as_string_list(payload.get("active_files")),
        next_action=str(payload.get("next_action") or ""),
        current_task=current_task,
        latest_user_request=latest_user_request,
        task_ledger=task_ledger,
        tasks=tasks,
        current_task_id=current_task_id,
        original_root_task_id=tasks[0].task_id if tasks else "",
        global_constraints=constraints,
        semantic_status="migrated-v1",
    )


def _as_task_memory_list(value: Any) -> list[TaskMemory]:
    if not isinstance(value, list):
        return []
    tasks: list[TaskMemory] = []
    seen_ids: set[str] = set()
    for idx, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        title = _compact_text(item.get("title"), 320)
        if not title:
            continue
        task_id = _safe_task_id(item.get("task_id"), title, idx)
        if task_id in seen_ids:
            task_id = f"{task_id}-{idx}"
        seen_ids.add(task_id)
        tasks.append(
            TaskMemory(
                task_id=task_id,
                title=title,
                status=_coerce_status(item.get("status")),
                summary=_compact_text(item.get("summary"), 500),
                constraints=_as_string_list(item.get("constraints"))[:12],
                decisions=_as_string_list(item.get("decisions"))[:12],
                validation_status=_as_string_dict(item.get("validation_status")),
                active_files=_as_string_list(item.get("active_files"))[:20],
                archive_refs=_as_string_list(item.get("archive_refs"))[:12],
                last_seen=_compact_text(item.get("last_seen"), 80),
            )
        )
    return tasks


def _as_archive_signal_list(value: Any) -> list[ArchiveSignal]:
    if not isinstance(value, list):
        return []
    signals: list[ArchiveSignal] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        obs_id = _compact_text(item.get("observation_id"), 120)
        if not obs_id:
            continue
        signals.append(
            ArchiveSignal(
                observation_id=obs_id,
                tool_name=_compact_text(item.get("tool_name"), 120) or "unknown",
                status=_compact_text(item.get("status"), 80) or "unknown",
                key_signals=_as_string_list(item.get("key_signals"))[:5],
                affected_files=_as_string_list(item.get("affected_files"))[:12],
                local_ref=_compact_text(item.get("local_ref"), 240),
                token_count=_as_int(item.get("token_count")),
                checksum=_compact_text(item.get("checksum"), 80),
                timestamp=_compact_text(item.get("timestamp"), 80),
            )
        )
    return signals


def _tasks_from_legacy_ledger(
    ledger: Iterable[str], current_task: str, constraints: list[str]
) -> list[TaskMemory]:
    titles = _dedupe_strings([*ledger, current_task], limit=100)
    tasks: list[TaskMemory] = []
    current_key = _task_key(current_task)
    for idx, title in enumerate(titles, start=1):
        status = "active" if _task_key(title) == current_key else "unknown"
        tasks.append(
            TaskMemory(
                task_id=_safe_task_id("", title, idx),
                title=title,
                status=status,
                constraints=constraints if status == "active" else [],
            )
        )
    return tasks


def _task_id_for_title(tasks: list[TaskMemory], title: str) -> str:
    key = _task_key(title)
    for task in reversed(tasks):
        if _task_key(task.title) == key:
            return task.task_id
    active = next((task for task in tasks if task.status == "active"), None)
    return active.task_id if active else ""


def _safe_task_id(value: Any, title: str, idx: int) -> str:
    raw = _compact_text(value, 80)
    if not raw:
        raw = f"task-{idx}-{title}"
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw.casefold()).strip("-")
    return cleaned[:80] or f"task-{idx}"


def _coerce_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in TASK_STATUSES else "unknown"


def _compact_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dedupe_strings(items: Iterable[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = _compact_text(item, 320)
        key = _task_key(value)
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _task_key(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def render_durable_state(state: DurableState) -> str:
    def _section(name: str, items: list[str]) -> list[str]:
        if not items:
            return [f"{name}: none"]
        return [f"{name}:"] + [f"- {item}" for item in items]

    current_task = state.current_task or state.goal or "unknown"
    latest_request = state.latest_user_request or state.goal or "unknown"
    current_task_memory = _current_task_memory(state)
    current_constraints = current_task_memory.constraints if current_task_memory else []
    active_files = _dedupe_strings(
        [
            *state.active_files,
            *((current_task_memory.active_files if current_task_memory else [])),
        ],
        limit=20,
    )
    legacy_constraints = _dedupe_strings(
        [*state.global_constraints, *current_constraints, *state.constraints],
        limit=16,
    )
    lines = [
        DURABLE_MEMORY_MARKER,
        f"Schema Version: {CURRENT_SCHEMA_VERSION}",
        f"Goal: {current_task}",
        f"Current Task: {current_task}",
        f"Current Task Status: {_current_task_status(state)}",
        f"Latest User Request: {latest_request}",
        *_section("Global Constraints", state.global_constraints),
        *_section("Current Task Constraints", current_constraints),
        *_section("Task Ledger", _render_task_ledger_entries(state)),
        *_section("Hard Constraints", legacy_constraints),
        *_section("Accepted Decisions", state.accepted_decisions),
        *_section("Invalidated Hypotheses", state.invalidated_hypotheses),
        "Validation Status:",
    ]
    if state.validation_status:
        lines.extend(
            f"- {key}: {value}" for key, value in state.validation_status.items()
        )
    else:
        lines.append("- unknown")
    lines.extend(_section("Active Files", active_files))
    lines.extend(_section("Retrieved Archive Signals", _render_archive_signals(state)))
    lines.append(f"Semantic Memory: {state.semantic_status or 'deterministic'}")
    if state.semantic_error:
        lines.append(f"Semantic Fallback Reason: {state.semantic_error[:240]}")
    lines.append(f"Next Action: {state.next_action or 'unknown'}")
    return "\n".join(lines)


def _current_task_memory(state: DurableState) -> TaskMemory | None:
    if state.current_task_id:
        for task in state.tasks:
            if task.task_id == state.current_task_id:
                return task
    current_key = _task_key(state.current_task)
    for task in reversed(state.tasks):
        if _task_key(task.title) == current_key:
            return task
    return None


def _current_task_status(state: DurableState) -> str:
    task = _current_task_memory(state)
    return task.status if task is not None else "unknown"


def _render_task_ledger_entries(state: DurableState) -> list[str]:
    tasks = _prompt_tasks(state)
    if tasks:
        entries = []
        for task in tasks:
            detail = task.summary or ""
            suffix = f" | {detail}" if detail else ""
            entries.append(f"[{task.status}] {task.title}{suffix}")
        return entries
    return state.task_ledger[:PROMPT_TASK_LIMIT]


def _prompt_tasks(state: DurableState) -> list[TaskMemory]:
    if not state.tasks:
        return []
    selected: list[TaskMemory] = []

    def add(task: TaskMemory | None) -> None:
        if task is None:
            return
        if any(existing.task_id == task.task_id for existing in selected):
            return
        selected.append(task)

    root = next(
        (task for task in state.tasks if task.task_id == state.original_root_task_id),
        None,
    )
    add(root or state.tasks[0])
    add(_current_task_memory(state))
    for task in state.tasks:
        if task.status == "blocked":
            add(task)
    for task in reversed(state.tasks):
        add(task)
        if len(selected) >= PROMPT_TASK_LIMIT:
            break
    return selected[:PROMPT_TASK_LIMIT]


def _render_archive_signals(state: DurableState) -> list[str]:
    rendered: list[str] = []
    for signal in state.retrieved_archive_signals[:3]:
        snippets = "; ".join(signal.key_signals[:3]) or "no extracted signal"
        files = ", ".join(signal.affected_files[:3])
        files_suffix = f" | files: {files}" if files else ""
        rendered.append(
            f"{signal.observation_id} ({signal.tool_name}, {signal.status}): "
            f"{snippets}{files_suffix}"
        )
    return rendered


def archive_observation(
    *,
    agent: Any,
    tool_name: str,
    tool_call_id: str | None,
    content: str,
    token_count: int,
    key_signal: str,
    key_signals: list[str] | None = None,
    affected_files: list[str],
    status: str,
) -> dict[str, Any]:
    checksum = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
    observation_id = f"obs_{int(time.time() * 1000)}_{checksum[:10]}"
    archive_path = observations_dir(agent) / f"{observation_id}.json"
    extracted_signals = _dedupe_strings(
        key_signals if key_signals is not None else [key_signal],
        limit=8,
    )
    if key_signal and key_signal not in extracted_signals:
        extracted_signals.insert(0, key_signal)
    record = {
        "observation_id": observation_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "status": status,
        "affected_files": affected_files,
        "token_count": token_count,
        "checksum": checksum,
        "archive_path": str(archive_path),
        "local_ref": (
            f"local://compaction/{session_key(agent)}/observations/"
            f"{observation_id}.json"
        ),
        "key_signal": key_signal,
        "key_signals": extracted_signals,
        "content": content,
    }
    tmp_path = archive_path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, sort_keys=True)
    tmp_path.replace(archive_path)
    return record


def render_masked_observation(record: dict[str, Any]) -> str:
    files = ", ".join(record.get("affected_files") or []) or "none detected"
    key_signals = record.get("key_signals")
    if not isinstance(key_signals, list):
        key_signals = [record.get("key_signal") or "none"]
    signal_lines = ["key_signals:"]
    signal_lines.extend(f"- {str(signal)[:300]}" for signal in key_signals[:5])
    return "\n".join(
        [
            MASKED_OBSERVATION_MARKER,
            f"id: {record['observation_id']}",
            f"tool: {record.get('tool_name') or 'unknown'}",
            f"tool_call_id: {record.get('tool_call_id') or 'unknown'}",
            f"result: {record.get('status') or 'unknown'}",
            f"tokens: {record.get('token_count') or 0}",
            f"checksum: {record.get('checksum') or 'unknown'}",
            f"key_signal: {record.get('key_signal') or 'none'}",
            *signal_lines,
            f"files: {files}",
            f"full_log_ref: {record.get('local_ref') or record.get('archive_path')}",
        ]
    )


def archive_index_path(agent: Any) -> Path:
    return session_dir(agent) / "archive_index.json"


def build_archive_index(agent: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for archive_file in sorted(observations_dir(agent).glob("obs_*.json")):
        record = read_observation_archive(agent, archive_file.stem)
        if record is None:
            continue
        records.append(_archive_metadata(record))

    path = archive_index_path(agent)
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, sort_keys=True)
    tmp_path.replace(path)
    return records


def read_archive_index(agent: Any) -> list[dict[str, Any]]:
    path = archive_index_path(agent)
    try:
        with path.open(encoding="utf-8") as f:
            value = json.load(f)
    except (OSError, json.JSONDecodeError):
        return build_archive_index(agent)
    if not isinstance(value, list):
        return build_archive_index(agent)
    return [item for item in value if isinstance(item, dict)]


def read_observation_archive(agent: Any, observation_id: str) -> dict[str, Any] | None:
    cleaned = _safe_segment(observation_id)
    path = observations_dir(agent) / f"{cleaned}.json"
    try:
        with path.open(encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return record if isinstance(record, dict) else None


def search_archive_index(
    agent: Any, query: str, *, limit: int = 3
) -> list[dict[str, Any]]:
    index = read_archive_index(agent)
    terms = [term.casefold() for term in re.findall(r"[A-Za-z0-9_.-]+", query or "")]
    if not terms:
        return index[-limit:]
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in index:
        haystack = _archive_search_text(item)
        score = sum(1 for term in terms if term and term in haystack)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: (pair[0], str(pair[1].get("timestamp") or "")))
    return [item for _score, item in scored[-limit:]][::-1]


def archive_signal_from_record(record: dict[str, Any]) -> ArchiveSignal:
    return ArchiveSignal(
        observation_id=str(record.get("observation_id") or ""),
        tool_name=str(record.get("tool_name") or "unknown"),
        status=str(record.get("status") or "unknown"),
        key_signals=_as_string_list(record.get("key_signals"))
        or _as_string_list([record.get("key_signal")]),
        affected_files=_as_string_list(record.get("affected_files")),
        local_ref=str(record.get("local_ref") or record.get("archive_path") or ""),
        token_count=_as_int(record.get("token_count")),
        checksum=str(record.get("checksum") or ""),
        timestamp=str(record.get("timestamp") or ""),
    )


def archive_preview(record: dict[str, Any], *, max_chars: int = 1600) -> str:
    signals = _as_string_list(record.get("key_signals")) or _as_string_list(
        [record.get("key_signal")]
    )
    lines = [
        f"id: {record.get('observation_id') or 'unknown'}",
        f"tool: {record.get('tool_name') or 'unknown'}",
        f"result: {record.get('status') or 'unknown'}",
        f"tokens: {record.get('token_count') or 0}",
        f"checksum: {record.get('checksum') or 'unknown'}",
        f"ref: {record.get('local_ref') or record.get('archive_path') or 'unknown'}",
        "signals:",
        *[f"- {signal}" for signal in signals[:8]],
    ]
    content = str(record.get("content") or "")
    if content:
        lines.extend(["preview:", content[:max_chars]])
    return "\n".join(lines)


def _archive_metadata(record: dict[str, Any]) -> dict[str, Any]:
    signals = _as_string_list(record.get("key_signals")) or _as_string_list(
        [record.get("key_signal")]
    )
    return {
        "observation_id": str(record.get("observation_id") or ""),
        "timestamp": str(record.get("timestamp") or ""),
        "tool_name": str(record.get("tool_name") or "unknown"),
        "tool_call_id": str(record.get("tool_call_id") or ""),
        "status": str(record.get("status") or "unknown"),
        "affected_files": _as_string_list(record.get("affected_files")),
        "token_count": _as_int(record.get("token_count")),
        "checksum": str(record.get("checksum") or ""),
        "archive_path": str(record.get("archive_path") or ""),
        "local_ref": str(record.get("local_ref") or ""),
        "key_signal": str(record.get("key_signal") or ""),
        "key_signals": signals[:8],
    }


def _archive_search_text(item: dict[str, Any]) -> str:
    parts = [
        item.get("observation_id"),
        item.get("tool_name"),
        item.get("status"),
        item.get("key_signal"),
        *(item.get("key_signals") or []),
        *(item.get("affected_files") or []),
    ]
    return " ".join(str(part or "") for part in parts).casefold()


def cleanup_observation_archives(
    agent: Any, settings: ContinuityCompactionSettings
) -> None:
    path = observations_dir(agent)
    now = time.time()
    max_age = settings.archive_retention_days * 24 * 60 * 60
    entries = sorted(path.glob("obs_*.json"), key=lambda item: item.stat().st_mtime)
    for entry in entries:
        try:
            if now - entry.stat().st_mtime > max_age:
                entry.unlink(missing_ok=True)
        except OSError:
            continue

    entries = sorted(path.glob("obs_*.json"), key=lambda item: item.stat().st_mtime)
    stale_count = max(0, len(entries) - settings.archive_retention_count)
    for entry in entries[:stale_count]:
        try:
            entry.unlink(missing_ok=True)
        except OSError:
            continue

    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    try:
        build_archive_index(agent)
    except OSError:
        pass
