"""Silence noisy MCP server lifecycle tracebacks in the console.

Problem
-------
``code_puppy.mcp_`` modules log lifecycle errors with ``exc_info=True``, which
dumps ugly multi-page tracebacks straight onto the user's terminal — even for
totally expected failures like a 401 from a misconfigured PingFed token. The
user can't see what they were doing through the wall of stack frames.

Solution
--------
A ``logging.Filter`` installed on each MCP-related logger:

* If a record carries ``exc_info``, format the full traceback once and append
  it to the per-server log file via ``mcp_logs.write_log()``.
* Replace the record's message with a tidy one-liner pointing the user at
  ``/mcp logs <server>``.
* Strip ``exc_info`` so handlers don't print the traceback to console.

Records without ``exc_info`` (boring info/warning chatter) pass through
untouched.

We extract the server id from a small library of message patterns
(e.g. ``"Error in server {id} lifecycle: ..."``); if no pattern matches we
fall back to a generic ``_mcp_errors`` log bucket.
"""

from __future__ import annotations

import logging
import re
import traceback
from typing import Iterable, Optional

# Modules whose noisy errors we want to capture.
_NOISY_LOGGERS = (
    "code_puppy.mcp_.async_lifecycle",
    "code_puppy.mcp_.manager",
    "code_puppy.mcp_.health_monitor",
    "code_puppy.mcp_.managed_server",
    "code_puppy.mcp_.registry",
)

# Regex patterns for extracting the server id from common error messages.
# Order matters — first match wins.
_SERVER_ID_PATTERNS = (
    re.compile(r"server (?P<id>[\w\-.]+) lifecycle"),
    re.compile(r"server (?P<id>[\w\-.]+) (?:task|context|heartbeat)"),
    re.compile(r"(?:start|stop|reload|remove|sync|initialize) (?:registered )?server (?:'|\")?(?P<id>[\w\-.]+)(?:'|\")?"),
    re.compile(r"for (?:server )?(?P<id>[\w\-.]+):"),
    re.compile(r"server[: ]+(?P<id>[\w\-.]+)"),
)

_FALLBACK_BUCKET = "_mcp_errors"

_INSTALL_FLAG = "_walmart_mcp_silencer_installed"


def _extract_server_id(message: str) -> Optional[str]:
    """Best-effort: pull a server id out of a log message."""
    for pat in _SERVER_ID_PATTERNS:
        m = pat.search(message)
        if m:
            return m.group("id")
    return None


class MCPLogSilencer(logging.Filter):
    """Filter that diverts noisy MCP tracebacks to per-server log files."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        # Only mess with records that carry a traceback.
        if not record.exc_info:
            return True

        # Lazy import — keeps plugin import cheap and avoids cycles.
        try:
            from code_puppy.mcp_.mcp_logs import write_log
        except Exception:  # noqa: BLE001
            return True  # Don't break logging if mcp_logs isn't available.

        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            message = str(record.msg)

        server_id = _extract_server_id(message) or _FALLBACK_BUCKET

        # Format the full traceback and persist it.
        try:
            tb_text = "".join(traceback.format_exception(*record.exc_info))
            level = record.levelname or "ERROR"
            write_log(
                server_id,
                f"{message}\n{tb_text.rstrip()}",
                level=level,
            )
        except Exception:  # noqa: BLE001
            # Logging must never crash the app.
            pass

        # Neutralize the record so handlers print a one-liner only.
        record.exc_info = None
        record.exc_text = None
        first_line = message.splitlines()[0] if message else "MCP error"
        # Trim absurdly long messages so the console stays clean.
        if len(first_line) > 240:
            first_line = first_line[:237] + "..."
        record.msg = (
            f"{first_line}  (full traceback: /mcp logs {server_id})"
        )
        record.args = ()
        return True


def install_mcp_log_silencer(loggers: Iterable[str] = _NOISY_LOGGERS) -> bool:
    """Install the silencer filter on each noisy MCP logger.

    Idempotent — safe to call repeatedly (e.g. on plugin reload).

    Returns True if the filter was newly installed, False if it was already in
    place.
    """
    root = logging.getLogger()
    if getattr(root, _INSTALL_FLAG, False):
        return False

    silencer = MCPLogSilencer(name="walmart-mcp-silencer")
    for name in loggers:
        lg = logging.getLogger(name)
        # Avoid double-attach if user calls us twice somehow.
        if not any(isinstance(f, MCPLogSilencer) for f in lg.filters):
            lg.addFilter(silencer)

    setattr(root, _INSTALL_FLAG, True)
    return True
