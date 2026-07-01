"""notifier — public Python API.

Other plugins and built-in code can import directly::

    from code_puppy.plugins.notifier import send_notification

    # Default — auto-dismisses after platform default (~5-600 s)
    send_notification("Build done", "bd-42 compiled cleanly")

    # Auto-dismiss after 10 seconds
    send_notification("Tests passing", "All 47 green", timeout=10)

    # Persistent — stays until the user dismisses it
    send_notification("Deploy failed", "bd-99 needs attention", persistent=True)

    # All options
    send_notification(
        title="Build failed",
        message="bd-42 compile error in main.py",
        subtitle="husky",
        rate_limit_key="bd-42",
        timeout=30,
        persistent=False,
    )

The function is rate-limited per *rate_limit_key* (defaults to ``title``),
so calling it frequently for the same event is safe.
"""

from __future__ import annotations

from typing import Optional


def send_notification(
    title: str,
    message: str,
    subtitle: Optional[str] = None,
    rate_limit_key: Optional[str] = None,
    timeout: Optional[int] = None,
    persistent: bool = False,
) -> bool:
    """Send a desktop notification.

    Args:
        title:           Bold header line of the notification.
        message:         Body text.
        subtitle:        Optional second line below the title (macOS only).
        rate_limit_key:  Deduplicate key — calls with the same key within
                         ``MIN_NOTIFICATION_INTERVAL`` seconds are dropped.
                         Defaults to *title*.
        timeout:         Seconds until the notification auto-dismisses.
                         ``None`` = platform default.
                         ``0``    = never dismiss (same as ``persistent=True``).
                         macOS  : exact seconds via alerter (ignored on osascript fallback).
                         Windows: ≤ 7 → "short" (~5 s), > 7 → "long" (~25 s), 0 → "reminder".
                         Linux  : exact seconds via ``notify-send --expire-time``.
        persistent:      If True the notification stays until the user dismisses
                         it manually.  Overrides *timeout*.

    Returns:
        True if the notification was dispatched, False if suppressed or failed.
    """
    from code_puppy.plugins.notifier.register_callbacks import (
        _send_notification as _dispatch,
    )

    return _dispatch(
        title,
        message,
        subtitle,
        rate_limit_key=rate_limit_key,
        timeout=timeout,
        persistent=persistent,
    )
