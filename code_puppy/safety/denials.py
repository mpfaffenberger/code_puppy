"""Per-run denial counters and human escalation thresholds."""

from __future__ import annotations

import contextvars
import sys
from dataclasses import dataclass


@dataclass(slots=True)
class DenialTracker:
    session_id: str | None
    consecutive_threshold: int = 3
    total_threshold: int = 20
    consecutive: int = 0
    total: int = 0

    def allow(self) -> None:
        self.consecutive = 0

    def deny(self) -> bool:
        self.consecutive += 1
        self.total += 1
        return (
            self.consecutive == self.consecutive_threshold
            or self.total == self.total_threshold
        )


_TRACKER: contextvars.ContextVar[DenialTracker | None] = contextvars.ContextVar(
    "mist_denial_tracker", default=None
)


def _threshold(key: str, default: int) -> int:
    from code_puppy.config import get_value

    try:
        return max(1, int(get_value(key) or default))
    except (TypeError, ValueError):
        return default


def start_denial_scope(session_id: str | None = None) -> DenialTracker:
    tracker = DenialTracker(
        session_id=session_id,
        consecutive_threshold=_threshold("denial_consecutive_threshold", 3),
        total_threshold=_threshold("denial_total_threshold", 20),
    )
    _TRACKER.set(tracker)
    return tracker


def clear_denial_scope() -> None:
    _TRACKER.set(None)


def get_denial_tracker() -> DenialTracker:
    tracker = _TRACKER.get()
    if tracker is None:
        tracker = start_denial_scope()
    return tracker


def record_allowed_action() -> None:
    get_denial_tracker().allow()


async def record_denied_action(reason: str) -> bool:
    """Record a denial and prompt a human exactly at configured thresholds."""
    tracker = get_denial_tracker()
    should_escalate = tracker.deny()
    if not should_escalate:
        return False

    from code_puppy.messaging import emit_warning

    emit_warning(
        "Safety policy escalation: "
        f"{tracker.consecutive} consecutive / {tracker.total} total denials."
    )
    if not getattr(sys.stdin, "isatty", lambda: False)():
        return True

    try:
        from code_puppy.tools.common import get_user_approval_async

        await get_user_approval_async(
            "Repeated Safety Denials",
            (
                f"Mist has encountered {tracker.consecutive} consecutive and "
                f"{tracker.total} total policy denials.\n\nLatest denial: {reason}\n\n"
                "Review the run before allowing it to continue trying alternatives."
            ),
        )
    except Exception:
        pass
    return True
