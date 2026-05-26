"""notifier plugin — callback registration.

Three surfaces
--------------
1. **Automatic hooks** (non-terminal prompts only)
   pre_tool_call / post_tool_call
   → one notification per user-input event, deduped via _user_interacted_this_run.

2. **Agent tool** — ``send_notification``
   Any agent can call this tool to fire an arbitrary desktop notification::

       send_notification(
           title="Build done",
           message="bd-42 compiled cleanly",
           subtitle="husky",          # optional
           rate_limit_key="bd-42",    # optional
       )

3. **Slash command** — ``/notify``
   Quick manual testing from the REPL::

       /notify My title | Optional body text
       /notify Deploy complete          ← body defaults to empty string

Enable with: /set enable_notifications true
"""

from __future__ import annotations

import importlib.util
import logging
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from code_puppy.callbacks import register_callback
from code_puppy.config import get_value

logger = logging.getLogger(__name__)

_HERE = pathlib.Path(__file__).parent
_backend_cache: dict[str, Any] = {}

_MIN_NOTIFICATION_INTERVAL = 2.0  # seconds
_last_notification_times: dict[str, float] = {}

# Per-run interaction flag (see agent_run_start / post_tool_call)
_user_interacted_this_run: bool = False

INTERACTIVE_TOOLS = {"ask_user_question", "ask_user"}


# ---------------------------------------------------------------------------
# Backend loader (file-path based so user-plugin installs work too)
# ---------------------------------------------------------------------------


def _load_backend(name: str) -> Any:
    if name not in _backend_cache:
        spec = importlib.util.spec_from_file_location(
            f"_notifier.{name}", _HERE / f"{name}.py"
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot locate backend: {name}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _backend_cache[name] = mod
    return _backend_cache[name]


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _is_notifications_enabled() -> bool:
    cfg_val = get_value("enable_notifications")
    if cfg_val is None:
        return False
    return str(cfg_val).strip().lower() in {"1", "true", "yes", "on"}


def _get_terminal_identifier() -> str:
    try:
        if sys.stdin.isatty():
            tty = os.ttyname(sys.stdin.fileno())
            return (
                f"Terminal {tty.split('tty')[-1]}"
                if tty.startswith("/dev/tty")
                else f"Terminal {os.path.basename(tty)}"
            )
    except (OSError, AttributeError):
        pass
    return f"PID {os.getpid()}"


def _get_working_dir_hint() -> str:
    try:
        return os.path.basename(os.getcwd()) or os.getcwd()
    except OSError:
        return ""


def _is_terminal_focused() -> bool:
    """Return True when the terminal is the active foreground window.

    macOS  : osascript frontmost-process query via _macos.is_terminal_focused().
    Windows: GetForegroundWindow + process ancestor walk via _windows.is_terminal_focused().
    Linux  : always False (no reliable cross-desktop focus API without extra deps).

    All backends fail open: an error returns False so the notification is sent.
    """
    system = platform.system().lower()
    if system == "darwin":
        try:
            return _load_backend("_macos").is_terminal_focused()
        except Exception:
            return False
    if system == "windows":
        try:
            return _load_backend("_windows").is_terminal_focused()
        except Exception:
            return False
    # Linux / other: no reliable focus detection without extra deps.
    return False


# ---------------------------------------------------------------------------
# Linux backend (inline — simple enough)
# ---------------------------------------------------------------------------


def _send_linux_notification(
    title: str, message: str, timeout: Optional[int] = None, persistent: bool = False
) -> bool:
    notify_send = shutil.which("notify-send")
    if not notify_send:
        return False
    try:
        cmd = [notify_send, "--app-name=Code Puppy"]
        if persistent or timeout == 0:
            cmd.extend(["--expire-time", "0"])
        elif timeout is not None:
            cmd.extend(["--expire-time", str(timeout * 1000)])
        cmd.extend([title, message])
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as exc:
        logger.debug("notifier: linux notification failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Core dispatcher  ← imported by __init__.py as the public Python API
# ---------------------------------------------------------------------------


def _send_notification(
    title: str,
    message: str,
    subtitle: Optional[str] = None,
    rate_limit_key: Optional[str] = None,
    timeout: Optional[int] = None,
    persistent: bool = False,
) -> bool:
    """Dispatch a notification to the platform backend, rate-limited per key."""
    key = rate_limit_key or title
    now = time.time()
    if now - _last_notification_times.get(key, 0) < _MIN_NOTIFICATION_INTERVAL:
        logger.debug("notifier: rate-limited (%s)", key)
        return False
    _last_notification_times[key] = now

    system = platform.system().lower()
    try:
        if system == "darwin":
            return _load_backend("_macos").send(
                title, message, subtitle, timeout=timeout, persistent=persistent
            )
        if system == "windows":
            return _load_backend("_windows").send(
                title, message, timeout=timeout, persistent=persistent
            )
        if system == "linux":
            return _send_linux_notification(
                title, message, timeout=timeout, persistent=persistent
            )
    except Exception as exc:
        logger.debug("notifier: backend error: %s", exc)
    return False


# ---------------------------------------------------------------------------
# Shared helper used by automatic hooks
# ---------------------------------------------------------------------------


def _notify_with_context(
    title: str,
    message: str,
    rate_limit_key: Optional[str] = None,
    timeout: Optional[int] = None,
    persistent: bool = False,
) -> None:
    """Send a notification enriched with tty + cwd context as the subtitle."""
    if not _is_notifications_enabled():
        return
    terminal_id = _get_terminal_identifier()
    working_dir = _get_working_dir_hint()
    subtitle = f"{terminal_id} • {working_dir}" if working_dir else terminal_id
    _send_notification(
        title,
        message,
        subtitle,
        rate_limit_key=rate_limit_key,
        timeout=timeout,
        persistent=persistent,
    )


# ---------------------------------------------------------------------------
# 1. Automatic hooks
# ---------------------------------------------------------------------------


def _on_agent_run_end(*args, **kwargs) -> None:
    global _user_interacted_this_run
    if not _is_notifications_enabled():
        _user_interacted_this_run = False  # reset even when disabled
        return
    if _user_interacted_this_run:
        logger.debug("notifier: suppressing agent_run_end — user already interacted")
        _user_interacted_this_run = False  # reset before returning
        return
    if _is_terminal_focused():
        logger.debug(
            "notifier: suppressing agent_run_end — terminal is already focused"
        )
        _user_interacted_this_run = False  # reset before returning
        return
    agent_name = "Code Puppy"
    if args and isinstance(args[0], str) and args[0].strip():
        agent_name = args[0]
    elif "agent_name" in kwargs and isinstance(kwargs["agent_name"], str):
        agent_name = kwargs["agent_name"]
    _notify_with_context(
        title=f"🐶 {agent_name}",
        message="Waiting for your input",
        rate_limit_key="agent_run_end",
    )
    _user_interacted_this_run = False  # reset at the end of a normal notify


async def _on_pre_tool_call(*args, **kwargs) -> None:
    if not _is_notifications_enabled():
        return None
    if _is_terminal_focused():
        logger.debug(
            "notifier: suppressing pre_tool_call — terminal is already focused"
        )
        return None
    tool_name = kwargs.get("tool_name") or next(
        (a for a in args if isinstance(a, str)), None
    )
    tool_args = kwargs.get("tool_args") or next(
        (a for a in args if isinstance(a, dict)), None
    )
    if not tool_name or tool_name not in INTERACTIVE_TOOLS:
        return None
    message = "Selection required"
    if isinstance(tool_args, dict):
        questions = tool_args.get("questions", [])
        if isinstance(questions, list) and questions:
            first_q = questions[0]
            if isinstance(first_q, dict) and first_q.get("header"):
                message = f"Question: {first_q['header']}"
    _notify_with_context(
        title="🐶 User Selection Required",
        message=message,
        rate_limit_key="interactive_tool",
    )
    return None


async def _on_post_tool_call(*args, **kwargs) -> None:
    global _user_interacted_this_run
    tool_name = kwargs.get("tool_name") or next(
        (a for a in args if isinstance(a, str)), None
    )
    if tool_name and tool_name in INTERACTIVE_TOOLS:
        _user_interacted_this_run = True
    return None


# ---------------------------------------------------------------------------
# 2. Agent tool — send_notification
# ---------------------------------------------------------------------------


def _register_send_notification_tool(agent) -> None:
    """Register send_notification as an agent-callable tool."""
    from pydantic import BaseModel
    from pydantic_ai import RunContext

    class SendNotificationInput(BaseModel):
        title: str
        message: str
        subtitle: Optional[str] = None
        rate_limit_key: Optional[str] = None

    class SendNotificationOutput(BaseModel):
        success: bool
        suppressed: bool  # True when rate-limited
        platform: str

    @agent.tool
    async def send_notification(  # noqa: F811
        context: RunContext,
        title: str,
        message: str,
        subtitle: Optional[str] = None,
        rate_limit_key: Optional[str] = None,
        timeout: Optional[int] = None,
        persistent: bool = False,
    ) -> SendNotificationOutput:
        """Send a desktop notification to the user.

        Use this to alert the user about any event — build results, errors,
        task completions, or anything else requiring their attention.

        Args:
            title:           Bold header shown in the notification banner.
            message:         Body text of the notification.
            subtitle:        Optional second line (visible on macOS).
            rate_limit_key:  Optional dedup key — repeated calls with the same
                             key within 2 s are dropped silently.
            timeout:         Seconds until auto-dismiss. None = platform default.
                             0 = persistent. macOS: exact seconds via alerter.
                             Windows: ≤7→short (~5s), >7→long (~25s), 0→reminder.
                             Linux: exact seconds via notify-send.
            persistent:      If True, stays until manually dismissed (overrides timeout).

        Returns:
            success:    Whether the notification was dispatched.
            suppressed: True when the call was dropped by the rate limiter.
            platform:   The OS the notification was sent on.
        """
        sys_name = platform.system().lower()
        before = _last_notification_times.get(rate_limit_key or title, 0)
        ok = _send_notification(
            title,
            message,
            subtitle,
            rate_limit_key,
            timeout=timeout,
            persistent=persistent,
        )
        after = _last_notification_times.get(rate_limit_key or title, 0)
        suppressed = ok is False and after == before  # timestamp didn't advance
        return SendNotificationOutput(
            success=ok,
            suppressed=suppressed,
            platform=sys_name,
        )


def _get_notification_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": "send_notification",
            "register_func": _register_send_notification_tool,
        }
    ]


# ---------------------------------------------------------------------------
# 3. Slash command — /notify
# ---------------------------------------------------------------------------


def _handle_notify_command(command: str, name: str) -> Optional[Any]:
    """Handle /notify <title> | <message>

    Examples:
        /notify Build failed
        /notify Build failed | bd-42 compile error in main.py
        /notify "Deploy done" | "All 12 services healthy"
    """
    if name != "notify":
        return None

    from code_puppy.messaging import emit_error, emit_success

    # Strip the command name prefix
    body = command.strip()
    for prefix in ("/notify ", "/notify"):
        if body.startswith(prefix):
            body = body[len(prefix) :].strip()
            break

    if "|" in body:
        title_part, _, msg_part = body.partition("|")
        title = title_part.strip().strip('"').strip("'")
        message = msg_part.strip().strip('"').strip("'")
    else:
        title = body.strip().strip('"').strip("'")
        message = ""

    if not title:
        emit_error("Usage: /notify <title> [| <message>]")
        return True

    ok = _send_notification(title, message)
    if ok:
        emit_success(f"Notification sent: {title!r}")
    else:
        emit_error(
            "Notification not sent — check enable_notifications config "
            "or platform backend availability."
        )
    return True


def _notify_command_help() -> List[tuple]:
    return [
        (
            "notify",
            "Send a desktop notification  Usage: /notify <title> [| <message>]",
        )
    ]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_callback("pre_tool_call", _on_pre_tool_call)
register_callback("post_tool_call", _on_post_tool_call)
register_callback("register_tools", _get_notification_tools)
register_callback("custom_command", _handle_notify_command)
register_callback("custom_command_help", _notify_command_help)

logger.debug("notifier: loaded (5 hooks registered)")
