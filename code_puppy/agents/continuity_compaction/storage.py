"""Local durable continuity and observation archive helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from code_puppy.agents.continuity_compaction.settings import (
    ContinuityCompactionSettings,
)

DURABLE_MEMORY_MARKER = "[Code Puppy Durable Compaction Memory]"
MASKED_OBSERVATION_MARKER = "[Masked Observation]"
STRUCTURED_SUMMARY_MARKER = "[Code Puppy Structured Compaction Summary]"


@dataclass(slots=True)
class DurableState:
    goal: str
    constraints: list[str]
    accepted_decisions: list[str]
    invalidated_hypotheses: list[str]
    validation_status: dict[str, str]
    active_files: list[str]
    next_action: str


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
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    tmp_path.replace(path)
    return path


def render_durable_state(state: DurableState) -> str:
    def _section(name: str, items: list[str]) -> list[str]:
        if not items:
            return [f"{name}: none"]
        return [f"{name}:"] + [f"- {item}" for item in items]

    lines = [
        DURABLE_MEMORY_MARKER,
        f"Goal: {state.goal or 'unknown'}",
        *_section("Hard Constraints", state.constraints),
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
    lines.extend(_section("Active Files", state.active_files))
    lines.append(f"Next Action: {state.next_action or 'unknown'}")
    return "\n".join(lines)


def archive_observation(
    *,
    agent: Any,
    tool_name: str,
    tool_call_id: str | None,
    content: str,
    token_count: int,
    key_signal: str,
    affected_files: list[str],
    status: str,
) -> dict[str, Any]:
    checksum = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
    observation_id = f"obs_{int(time.time() * 1000)}_{checksum[:10]}"
    archive_path = observations_dir(agent) / f"{observation_id}.json"
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
        "content": content,
    }
    tmp_path = archive_path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, sort_keys=True)
    tmp_path.replace(archive_path)
    return record


def render_masked_observation(record: dict[str, Any]) -> str:
    files = ", ".join(record.get("affected_files") or []) or "none detected"
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
            f"files: {files}",
            f"full_log_ref: {record.get('local_ref') or record.get('archive_path')}",
        ]
    )


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
