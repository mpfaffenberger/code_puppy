"""macOS notification backend.

Preference order:
  1. alerter (vjeantet/alerter) — UNUserNotificationCenter, click-to-focus
  2. osascript display notification — display-only fallback

Timeout / persistent behaviour
--------------------------------
alerter   : --timeout N   (N > 0 → auto-dismiss after N seconds;
                           N == 0 → no auto-dismiss / persistent)
osascript : macOS dismisses these automatically; no programmatic control.
            timeout/persistent args are accepted but silently ignored.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 600  # seconds — alerter auto-dismisses after 10 min by default


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _escape_applescript(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _detect_terminal_bundle_id() -> Optional[str]:
    """Return the bundle ID of the terminal that owns this process, or None.

    Builds a pid→bundle_id map of all running GUI apps via ``lsappinfo list``,
    then walks the ppid chain from our own PID until it finds an ancestor that
    is a GUI app. That ancestor is the terminal emulator running Code Puppy.
    """
    import os
    import re

    # ── Step 1: pid → bundle_id for every running GUI app ──────────────────
    pid_to_bundle: dict[int, str] = {}
    try:
        result = subprocess.run(
            ["lsappinfo", "list"],
            capture_output=True,
            text=True,
            timeout=3,
        )

        # lsappinfo output varies; bundleID may appear before pid and with case
        # differences. Parse per-app blocks and only commit when both are known.
        current_pid: Optional[int] = None
        current_bundle: Optional[str] = None

        def _commit() -> None:
            nonlocal current_pid, current_bundle
            if current_pid is not None and current_bundle:
                pid_to_bundle[current_pid] = current_bundle
            current_pid = None
            current_bundle = None

        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # New app block starts with: '12) "Finder" ASN:...'
            if re.match(r"^\d+\)\s", line):
                _commit()

            bundle_match = re.search(
                r'bundleid\s*=\s*"([^"]+)"',
                line,
                flags=re.IGNORECASE,
            )
            if bundle_match:
                current_bundle = bundle_match.group(1)

            pid_match = re.search(r"\bpid\s*=\s*(\d+)\b", line)
            if pid_match:
                current_pid = int(pid_match.group(1))

        _commit()
    except Exception:
        pass  # lsappinfo unavailable; pid_to_bundle stays empty

    # ── Step 2: walk ppid chain until we hit a GUI-app ancestor ────────────
    pid = os.getpid()
    visited: set[int] = set()
    while pid > 1 and pid not in visited:
        visited.add(pid)
        if pid in pid_to_bundle:
            return pid_to_bundle[pid]
        try:
            ps = subprocess.run(
                ["ps", "-p", str(pid), "-o", "ppid="],
                capture_output=True,
                text=True,
                timeout=2,
            )
            ppid_str = ps.stdout.strip()
            if not ppid_str:
                break
            pid = int(ppid_str)
        except Exception:
            break

    return None


def _terminal_is_active(bundle_id: str) -> bool:
    """Return True if the terminal is already the frontmost app."""
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get bundle identifier of '
                "(first process whose frontmost is true)",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip() == bundle_id
    except Exception:
        return False


def is_terminal_focused() -> bool:
    """Return True if the terminal running Code Puppy is currently frontmost.

    Used by the notifier to suppress agent_run_end notifications when the
    user is already looking at the terminal — they don't need to be poked.
    Returns False on any error (fail open = send the notification).
    """
    try:
        bundle_id = _detect_terminal_bundle_id()
        if not bundle_id:
            return False
        return _terminal_is_active(bundle_id)
    except Exception:
        return False


def _focus_terminal(bundle_id: str) -> None:
    """Bring the terminal to the front using AppleScript activate.

    ``open -b`` is blocked by macOS focus-stealing protection when called
    from a background thread.  AppleScript's ``activate`` command bypasses
    that restriction and reliably raises the target window.
    """
    if not _terminal_is_active(bundle_id):
        script = f'tell application id "{bundle_id}" to activate'
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _run_alerter_and_focus(cmd: list[str], bundle_id: str) -> None:
    """Daemon thread: run alerter (blocking), focus terminal on click.

    alerter manages its own timeout via ``--timeout`` so we do NOT pass a
    Python-level timeout to ``subprocess.run`` — that races against alerter's
    own timer and can kill the process before it writes output.

    alerter stdout values:
      @CONTENTCLICKED  — user clicked the notification body  → focus terminal
      @ACTIONCLICKED   — user clicked an action button       → focus terminal
      @TIMEOUT         — notification expired                 → no-op
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout.strip()
        if output in ("@CONTENTCLICKED", "@ACTIONCLICKED"):
            _focus_terminal(bundle_id)
    except subprocess.TimeoutExpired:
        logger.debug("notifier: alerter process timed out unexpectedly")
    except Exception as exc:
        logger.debug("notifier: alerter thread error: %s", exc)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def send(
    title: str,
    message: str,
    subtitle: Optional[str] = None,
    timeout: Optional[int] = None,
    persistent: bool = False,
) -> bool:
    """Send a macOS desktop notification. Returns True on success.

    Args:
        title:      Notification title.
        message:    Notification body.
        subtitle:   Optional subtitle line (alerter only).
        timeout:    Seconds until auto-dismiss (alerter only).
                    None → use default (600 s).
                    0    → never auto-dismiss (same as persistent=True).
        persistent: If True, the notification never auto-dismisses.
                    Equivalent to timeout=0.  Overrides timeout when True.
    """
    bundle_id = _detect_terminal_bundle_id()
    alerter = shutil.which("alerter")

    # Resolve effective timeout for alerter
    if persistent:
        effective_timeout = 0  # 0 = no auto-dismiss in alerter
    elif timeout is not None:
        effective_timeout = max(0, int(timeout))
    else:
        effective_timeout = _DEFAULT_TIMEOUT

    if alerter:
        cmd = [
            alerter,
            "--title",
            title,
            "--message",
            message,
            "--sound",
            "default",
            "--timeout",
            str(effective_timeout),
        ]
        if subtitle:
            cmd.extend(["--subtitle", subtitle])

        if bundle_id:
            threading.Thread(
                target=_run_alerter_and_focus,
                args=(cmd, bundle_id),
                daemon=True,
            ).start()
        else:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    # osascript fallback — display only; timeout/persistent not controllable
    if persistent or timeout is not None:
        logger.debug(
            "notifier: timeout/persistent ignored — alerter not installed, "
            "osascript fallback has no timeout control"
        )
    parts = [f'display notification "{_escape_applescript(message)}"']
    parts.append(f'with title "{_escape_applescript(title)}"')
    if subtitle:
        parts.append(f'subtitle "{_escape_applescript(subtitle)}"')
    parts.append('sound name "Ping"')
    subprocess.Popen(
        ["osascript", "-e", " ".join(parts)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True
