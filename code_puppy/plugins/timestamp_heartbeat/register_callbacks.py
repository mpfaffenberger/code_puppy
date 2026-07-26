"""Plugin: timestamp heartbeat — stamp the current datetime into tool results.

Models are time-blind: nothing in a long agent run tells them how much
wall-clock time has passed. Every N tool calls this plugin injects a
``__SYS_TIMESTAMP__`` key into the tool's result dict so the model gets a
periodic clock tick without any extra transcript noise or history messages.

How the injection works (and why it's safe):
    ``pydantic_patches._patched_call_tool`` does ``return result`` inside a
    ``try`` block and awaits ``on_post_tool_call(..., result, ...)`` in the
    ``finally``. Python evaluates the return value (a *reference* to the
    dict) before running ``finally``, so an **in-place** mutation of that
    dict here is visible to the caller — and therefore to the model when
    the result is serialized into the ToolReturnPart.

    Corollary: only plain ``dict`` results can be stamped. When the k-th
    call returns something else (a string, a pydantic model), the stamp is
    marked *due* and lands on the next dict-shaped result instead of being
    silently dropped.

Config (puppy.cfg):
    timestamp_heartbeat_interval = 10   # stamp every N tool calls; 0 disables
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)

TIMESTAMP_KEY = "__SYS_TIMESTAMP__"
CONFIG_KEY = "timestamp_heartbeat_interval"
DEFAULT_INTERVAL = 10

# Module-level state. Tool calls are dispatched on the event loop, so plain
# ints are fine — no locking theater needed.
_calls_since_stamp = 0
_stamp_due = False


def _get_interval() -> int:
    """Read the heartbeat interval from puppy.cfg (0 or negative disables)."""
    try:
        from code_puppy.config import get_value

        raw = get_value(CONFIG_KEY)
        if raw is None or str(raw).strip() == "":
            return DEFAULT_INTERVAL
        return int(str(raw).strip())
    except (ValueError, TypeError):
        logger.warning(
            "Invalid %s value; falling back to %d", CONFIG_KEY, DEFAULT_INTERVAL
        )
        return DEFAULT_INTERVAL
    except Exception:
        return DEFAULT_INTERVAL


def _now_stamp() -> str:
    """Local time with UTC offset, second precision — readable and unambiguous."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _reset_state() -> None:
    """Reset the counter/due flag (used by tests and defensive re-init)."""
    global _calls_since_stamp, _stamp_due
    _calls_since_stamp = 0
    _stamp_due = False


def _on_post_tool_call(
    tool_name: str,
    tool_args: dict,
    result: Any,
    duration_ms: float,
    context: Any = None,
) -> None:
    """Count tool calls; every ``interval`` calls, stamp the result dict."""
    global _calls_since_stamp, _stamp_due
    _ = tool_name, tool_args, duration_ms, context  # signature conformance

    try:
        interval = _get_interval()
        if interval <= 0:
            return

        _calls_since_stamp += 1
        if _calls_since_stamp >= interval:
            _stamp_due = True
            _calls_since_stamp = 0

        if _stamp_due and isinstance(result, dict):
            result[TIMESTAMP_KEY] = _now_stamp()
            _stamp_due = False
    except Exception:
        # A clock tick is never worth breaking a tool call.
        logger.debug("timestamp heartbeat failed", exc_info=True)


register_callback("post_tool_call", _on_post_tool_call)


__all__ = [
    "CONFIG_KEY",
    "DEFAULT_INTERVAL",
    "TIMESTAMP_KEY",
    "_get_interval",
    "_on_post_tool_call",
    "_reset_state",
]
