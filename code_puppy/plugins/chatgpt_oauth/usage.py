"""Fetch and cache Codex plan usage without blocking the interactive UI."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests

from .config import CHATGPT_OAUTH_CONFIG

logger = logging.getLogger(__name__)

_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
_CACHE_TTL_SECONDS = 60.0


@dataclass(frozen=True)
class CodexUsage:
    """Remaining percentages for Codex's rolling usage windows."""

    primary_remaining: int | None = None
    secondary_remaining: int | None = None

    def format_status(self) -> str:
        parts: list[str] = []
        if self.primary_remaining is not None:
            parts.append(f"5h {self.primary_remaining}% remaining")
        if self.secondary_remaining is not None:
            parts.append(f"week {self.secondary_remaining}% remaining")
        return " · ".join(parts)


_lock = threading.Lock()
_cached_usage: CodexUsage | None = None
_last_attempt = 0.0
_fetch_in_progress = False


def _remaining_percent(window: Any) -> int | None:
    if not isinstance(window, dict):
        return None
    used = window.get("used_percent")
    if not isinstance(used, (int, float)):
        return None
    return max(0, min(100, round(100 - used)))


def parse_usage_payload(payload: Any) -> CodexUsage | None:
    """Parse the response returned by the Codex ``wham/usage`` endpoint."""
    if not isinstance(payload, dict):
        return None
    rate_limit = payload.get("rate_limit")
    if not isinstance(rate_limit, dict):
        return None
    usage = CodexUsage(
        primary_remaining=_remaining_percent(rate_limit.get("primary_window")),
        secondary_remaining=_remaining_percent(rate_limit.get("secondary_window")),
    )
    if usage.primary_remaining is None and usage.secondary_remaining is None:
        return None
    return usage


def _fetch(access_token: str, account_id: str) -> None:
    global _cached_usage, _fetch_in_progress
    headers = {
        "Authorization": f"Bearer {access_token}",
        "ChatGPT-Account-Id": account_id,
        "Accept": "application/json",
        "originator": CHATGPT_OAUTH_CONFIG.get("originator", "codex_cli_rs"),
    }
    try:
        response = requests.get(_USAGE_URL, headers=headers, timeout=10)
        response.raise_for_status()
        usage = parse_usage_payload(response.json())
        if usage is not None:
            with _lock:
                _cached_usage = usage
    except (requests.RequestException, ValueError):
        logger.debug("Unable to refresh Codex usage", exc_info=True)
    finally:
        with _lock:
            _fetch_in_progress = False


def refresh_usage_in_background(access_token: str, account_id: str) -> None:
    """Refresh the cache at most once per minute on a daemon thread."""
    global _fetch_in_progress, _last_attempt
    if not access_token or not account_id:
        return
    now = time.monotonic()
    with _lock:
        if _fetch_in_progress or now - _last_attempt < _CACHE_TTL_SECONDS:
            return
        _fetch_in_progress = True
        _last_attempt = now
    threading.Thread(
        target=_fetch,
        args=(access_token, account_id),
        name="codex-usage-refresh",
        daemon=True,
    ).start()


def get_usage_status() -> str:
    """Return cached status text; this function never performs I/O."""
    with _lock:
        usage = _cached_usage
    return usage.format_status() if usage is not None else ""
