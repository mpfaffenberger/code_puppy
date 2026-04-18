"""Terminal-facing diagnostics for agent-run exceptions.

When an agent run blows up, ``str(exc)`` alone loses almost all of the
actionable signal that pydantic-ai / provider SDKs tuck onto ``__cause__``,
``__context__``, ``BaseExceptionGroup.exceptions``, or attributes like
``body`` / ``response`` / ``errors``. This module walks those paths in a
bounded, defensive way and emits structured diagnostic blocks to the terminal.

File-level logging (``log_error``) is untouched — this module only controls
what we *surface* in the terminal for the user. All ``getattr`` access is
guarded; diagnostic emit must never itself raise.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text

from code_puppy.error_logging import log_error
from code_puppy.messaging import emit_info

# Python 3.11+ builtin; graceful fallback for 3.10
try:
    from builtins import BaseExceptionGroup  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - 3.10 only
    BaseExceptionGroup = Exception  # type: ignore[misc,assignment]

# Only emit deep diagnostics for shapes that actually benefit. The boring 80%
# of errors get the cheap path (one-line emit + log-file pointer).
DIAGNOSTIC_TRIGGERS = ("output validation", "retries", "exceptiongroup")

# Attributes commonly carrying the "real" story on provider/pydantic-ai errors.
USEFUL_ATTRS = ("response", "body", "message", "detail", "errors")

# Hard caps so a pathological exception tree can't flood the terminal.
_MAX_CHAIN_DEPTH = 5
_MAX_GROUP_LEAVES = 10


def _safe_getattr(obj: Any, name: str) -> Any:
    """``getattr`` that never raises, even on hostile descriptors."""
    try:
        return getattr(obj, name, None)
    except Exception:  # pragma: no cover - defensive
        return None


def _emit_useful_attrs(exc: BaseException, group_id: str, indent: str) -> None:
    """Emit any ``USEFUL_ATTRS`` present on ``exc`` as dim lines."""
    for attr in USEFUL_ATTRS:
        val = _safe_getattr(exc, attr)
        if not val:
            continue
        try:
            rendered = str(val)
        except Exception:  # pragma: no cover - hostile __str__
            rendered = f"<unrenderable {type(val).__name__}>"
        emit_info(
            Text.from_markup(f"[dim]{indent}{attr}: {rendered}[/dim]"),
            group_id=group_id,
        )


def _emit_exception_chain(
    exc: BaseException,
    group_id: str,
    depth: int = 0,
    max_depth: int = _MAX_CHAIN_DEPTH,
) -> None:
    """Walk ``__cause__`` / ``__context__`` chains with a bounded depth."""
    # Guard against cycles (rare but possible when users re-raise chains).
    seen: set[int] = set()
    current: BaseException | None = exc
    current_depth = depth
    while current is not None and current_depth < max_depth:
        cause = _safe_getattr(current, "__cause__")
        context = _safe_getattr(current, "__context__")
        nxt = cause if cause is not None else context
        if nxt is None or id(nxt) in seen:
            return
        seen.add(id(nxt))
        label = "cause" if cause is not None else "context"
        emit_info(
            Text.from_markup(
                f"[dim]  {'  ' * current_depth}{label}: "
                f"{type(nxt).__name__}: {nxt}[/dim]"
            ),
            group_id=group_id,
        )
        _emit_useful_attrs(nxt, group_id, indent="    " + "  " * current_depth)
        current = nxt
        current_depth += 1


def _needs_deep_diagnostics(exc: BaseException) -> bool:
    """Return True when the cheap path would hide important detail."""
    if isinstance(exc, BaseExceptionGroup):
        return True
    try:
        msg = str(exc).lower()
    except Exception:  # pragma: no cover - hostile __str__
        return False
    return any(trigger in msg for trigger in DIAGNOSTIC_TRIGGERS)


def emit_exception_diagnostics(exc: BaseException, group_id: str) -> None:
    """Emit terminal diagnostics for ``exc``, bounded and defensive.

    Cheap path (always): one-line summary + log file write.
    Deep path (only for ``ExceptionGroup``s or trigger-phrase messages):
    cause/context chain + group leaves + useful attributes.

    Never raises. Worst-case failure is a slightly noisier terminal during an
    already-failed run.
    """
    try:
        emit_info(f"Unexpected error: {exc}", group_id=group_id)
    except Exception:  # pragma: no cover - emit should never fail
        pass

    # File logging is independent of terminal output and stays on the cheap path.
    try:
        log_error(
            exc,
            context=f"Agent run (group_id={group_id})",
            include_traceback=True,
        )
    except Exception:  # pragma: no cover - logging failure must not cascade
        pass

    try:
        if not _needs_deep_diagnostics(exc):
            return

        emit_info(
            Text.from_markup("[yellow]Diagnostic detail:[/yellow]"),
            group_id=group_id,
        )
        emit_info(
            Text.from_markup(f"[dim]  Exception type: {type(exc).__name__}[/dim]"),
            group_id=group_id,
        )

        _emit_exception_chain(exc, group_id)

        if isinstance(exc, BaseExceptionGroup):
            for i, sub in enumerate(exc.exceptions[:_MAX_GROUP_LEAVES], start=1):
                emit_info(
                    Text.from_markup(
                        f"[yellow]  Sub-exception {i}: "
                        f"{type(sub).__name__}: {sub}[/yellow]"
                    ),
                    group_id=group_id,
                )
                _emit_useful_attrs(sub, group_id, indent="    ")
                # One level of nested cause on each leaf is usually enough.
                _emit_exception_chain(sub, group_id, depth=1, max_depth=3)
            extra = len(exc.exceptions) - _MAX_GROUP_LEAVES
            if extra > 0:
                emit_info(
                    Text.from_markup(
                        f"[dim]  ... and {extra} more sub-exception(s) omitted[/dim]"
                    ),
                    group_id=group_id,
                )

        _emit_useful_attrs(exc, group_id, indent="  ")
    except Exception:  # pragma: no cover - diagnostics must never raise
        pass


__all__ = ["emit_exception_diagnostics"]
