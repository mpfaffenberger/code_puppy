"""Text extraction helpers for Continuity compaction."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

_PATH_RE = re.compile(
    r"(?:\.{0,2}/|/)?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*"
    r"\.(?:py|pyi|js|jsx|ts|tsx|json|toml|yaml|yml|md|txt|go|rs|java|c|cc|cpp|h|hpp|css|html)"
)
SIGNAL_RE = re.compile(
    r"(error|failed|failure|exception|traceback|assertion|exit code|exit_code)",
    re.IGNORECASE,
)


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, sort_keys=True, default=str)
    except TypeError:
        return str(content)


def messages_to_text(messages: Iterable[Any]) -> str:
    chunks: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []) or []:
            if hasattr(part, "content"):
                chunks.append(content_text(getattr(part, "content")))
            elif hasattr(part, "args"):
                chunks.append(content_text(getattr(part, "args")))
    return "\n".join(chunk for chunk in chunks if chunk)


def extract_paths(text: str) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for match in _PATH_RE.findall(text):
        if match not in seen:
            seen.add(match)
            paths.append(match)
    return paths


def extract_key_signal(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line and SIGNAL_RE.search(line):
            return line[:300]
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line:
            return line[:300]
    return "no textual signal"


def extract_key_signals(text: str) -> list[str]:
    signals: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line and (SIGNAL_RE.search(line) or _PATH_RE.search(line)):
            signals.append(line[:300])
        if len(signals) >= 8:
            break
    if not signals:
        first = extract_key_signal(text)
        if first:
            signals.append(first)
    return dedupe_nonempty(signals, limit=8)


def status_from_text(text: str) -> str:
    return "failed" if SIGNAL_RE.search(text) else "completed"


def dedupe_nonempty(items: Iterable[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value[:500])
        if len(result) >= limit:
            break
    return result
