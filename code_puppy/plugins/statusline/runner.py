"""Run the status line command (JSON on stdin -> stdout) without blocking.

The prompt is re-rendered frequently; running a shell command synchronously
each time would make the prompt janky. So we cache the last stdout and refresh
it in a background thread no more often than ``statusline_refresh_ms``. The
prompt always reads the cached value instantly.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time

from .config import get_command, get_refresh_ms, get_timeout_ms, is_enabled
from .payload import build_payload_json

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cached_output: str = ""
_last_run_monotonic: float = 0.0
_running: bool = False


def _run_command_blocking(command: str) -> str:
    payload = build_payload_json()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",  # explicit UTF-8: prevents cp1252 crash on Windows with umlauts
            errors="replace",  # never raise UnicodeDecodeError — bad chars become '?'
            timeout=get_timeout_ms() / 1000.0,
        )
    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        logger.debug("statusline command failed", exc_info=True)
        return ""
    out = (proc.stdout or "").strip("\n")
    # Status line is a single line: collapse any extra newlines.
    return out.replace("\n", " ").strip()


def _refresh_async(command: str) -> None:
    global _cached_output, _running, _last_run_monotonic
    try:
        result = _run_command_blocking(command)
        with _lock:
            _cached_output = result
            _last_run_monotonic = time.monotonic()
    finally:
        with _lock:
            _running = False


def get_status_text() -> str:
    """Return the status line, refreshing in the background when stale.

    First call (cold cache) runs **synchronously** once so the very first
    prompt — including the one shown at startup — has a status line. After that
    it never blocks: it returns the cached value and schedules a background
    refresh when the value goes stale.
    """
    global _running, _last_run_monotonic, _cached_output
    if not is_enabled():
        return ""
    command = get_command()
    if not command:
        return ""

    now = time.monotonic()
    with _lock:
        cached = _cached_output
        cold = _last_run_monotonic == 0.0
        if cold:
            # Reserve the slot so we don't also spawn an async refresh below.
            _last_run_monotonic = now

    if cold:
        # One-time synchronous warm-up so the FIRST prompt (startup) has a
        # status line. Bounded by the command timeout.
        result = _run_command_blocking(command)
        with _lock:
            _cached_output = result
            _last_run_monotonic = time.monotonic()
        return result

    with _lock:
        due = (now - _last_run_monotonic) * 1000.0 >= get_refresh_ms()
        should_start = due and not _running
        if should_start:
            _running = True
            # Reserve the slot immediately so concurrent prompt renders don't
            # spawn a thundering herd of refreshes.
            _last_run_monotonic = now

    if should_start:
        threading.Thread(target=_refresh_async, args=(command,), daemon=True).start()

    return cached


def run_once_sync() -> str:
    """Run the command synchronously once (for /statusline show preview)."""
    command = get_command()
    if not command:
        return ""
    return _run_command_blocking(command)


def reset_cache() -> None:
    global _cached_output, _last_run_monotonic, _running
    with _lock:
        _cached_output = ""
        _last_run_monotonic = 0.0
        _running = False
