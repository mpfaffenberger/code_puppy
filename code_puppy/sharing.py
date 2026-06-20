"""Opt-in, redacted, static session sharing."""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

import httpx

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|secret|password|authorization)"
    r"(\s*[:=]\s*|[\"']\s*:\s*[\"'])([^\s,;\"']+)"
)
_BEARER = re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{8,}")


def _known_secret_values() -> list[str]:
    markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    return [
        value
        for key, value in os.environ.items()
        if len(value) >= 8 and any(marker in key.upper() for marker in markers)
    ]


def redact_text(value: str) -> str:
    """Remove common credentials without altering ordinary transcript text."""
    redacted = _BEARER.sub("Bearer [REDACTED]", value)
    redacted = _SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", redacted
    )
    for secret in _known_secret_values():
        redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def serialise_messages(messages: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for message in messages:
        if hasattr(message, "model_dump"):
            value = message.model_dump(mode="json")
        elif (
            isinstance(message, (dict, list, str, int, float, bool)) or message is None
        ):
            value = message
        else:
            value = repr(message)
        result.append(json.loads(redact_text(json.dumps(value, default=str))))
    return result


def render_session_html(messages: Iterable[Any], *, title: str = "Mist session") -> str:
    payload = json.dumps(serialise_messages(messages), ensure_ascii=False, indent=2)
    safe_title = html.escape(title)
    safe_payload = html.escape(payload)
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{safe_title}</title>
<style>body{{max-width:960px;margin:2rem auto;padding:0 1rem;font:15px/1.5 system-ui;background:#0b1020;color:#e8edf7}}pre{{white-space:pre-wrap;background:#141b2d;padding:1rem;border-radius:10px}}small{{color:#9aa8bf}}</style>
<h1>{safe_title}</h1><small>Redacted, read-only export generated locally by Mist.</small>
<pre>{safe_payload}</pre></html>"""


def export_session_html(
    messages: Iterable[Any], destination: Path, *, title: str = "Mist session"
) -> Path:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_session_html(messages, title=title), encoding="utf-8")
    return destination


def upload_session_html(
    messages: Iterable[Any], endpoint: str, *, title: str = "Mist session"
) -> str:
    """Upload a redacted export to an explicitly selected user endpoint."""
    if not endpoint.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        raise ValueError("Share endpoint must use HTTPS (or be local)")
    response = httpx.post(
        endpoint,
        json={"title": title, "html": render_session_html(messages, title=title)},
        timeout=30,
    )
    response.raise_for_status()
    url = response.json().get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("Share endpoint response must contain a URL")
    return url
