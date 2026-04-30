"""Observation archive storage for the Continuity compaction plugin."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from code_puppy.plugins.continuity_compaction.settings import (
    ContinuityCompactionSettings,
)
from code_puppy.plugins.continuity_compaction.storage import (
    MASKED_OBSERVATION_MARKER,
    ArchiveSignal,
    _as_int,
    _as_string_list,
    _dedupe_strings,
    _safe_segment,
    observations_dir,
    session_dir,
    session_key,
)


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
