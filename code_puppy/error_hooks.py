"""Chained uncaught-exception hooks that feed the ``log_error`` sink.

Every wrapper reports first and then ALWAYS delegates to the hook it replaced,
so the traceback and exit status stay exactly as before. Nothing is printed
from here. Importing this module installs nothing; callers opt in.

Imports are module-level on purpose: the sink must already be loaded if a
later import crashes.

Called by: main (install), future routing code (``report_exception``).
Depends on: error_logging::log_error, error_logging::was_logged,
error_policy::should_report.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable
from typing import Any

from code_puppy.error_logging import log_error, was_logged
from code_puppy.error_policy import should_report

logger = logging.getLogger(__name__)

_MARKER = "_code_puppy_error_hook"
_PREVIOUS = "_code_puppy_previous_hook"

_MAIN_CONTEXT = "code_puppy.error_hooks::_install_excepthook.hook: uncaught exception reached sys.excepthook"
_THREAD_CONTEXT = (
    "code_puppy.error_hooks::_thread_report: uncaught exception ended a worker thread"
)


def report_exception(exc: BaseException, *, context: str) -> bool:
    """Write *exc* to ``errors.log`` once; True only when this call wrote it.

    Returns False for control flow, for an exception already logged, and when
    the call itself raised. The sink swallows its own write failures, so a
    failed write still returns True. Never raises.
    """
    try:
        if not isinstance(exc, BaseException):
            return False
        if not should_report(exc) or was_logged(exc):
            return False
        log_error(exc, context=context)
        return True
    except Exception:
        logger.debug("reporting an uncaught exception failed", exc_info=True)
        return False


def _thread_report(args: Any) -> None:
    """Report a thread failure; the hook's delegation must survive any odd *args*."""
    try:
        try:
            name = getattr(getattr(args, "thread", None), "name", None) or "unknown"
        except Exception:
            logger.debug("reading the failing thread's name failed", exc_info=True)
            name = "unknown"
        report_exception(args.exc_value, context=f"{_THREAD_CONTEXT} ({name})")
    except Exception:
        logger.debug("reporting an uncaught thread exception failed", exc_info=True)


def _mark(wrapper: Callable[..., Any], previous: Callable[..., Any] | None) -> None:
    setattr(wrapper, _MARKER, True)
    setattr(wrapper, _PREVIOUS, previous)


def _is_ours(hook: object) -> bool:
    return bool(getattr(hook, _MARKER, False))


def _install_excepthook() -> None:
    if _is_ours(sys.excepthook):
        return
    previous = sys.excepthook or sys.__excepthook__

    def hook(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        report_exception(exc, context=_MAIN_CONTEXT)
        previous(exc_type, exc, tb)

    _mark(hook, previous)
    sys.excepthook = hook


def _install_threading_hook() -> None:
    if _is_ours(threading.excepthook):
        return
    previous = threading.excepthook or threading.__excepthook__

    def hook(args: threading.ExceptHookArgs) -> None:
        _thread_report(args)
        previous(args)

    _mark(hook, previous)
    threading.excepthook = hook


def install_error_hooks() -> None:
    """Chain ``sys.excepthook`` and ``threading.excepthook``.

    Idempotent: a hook already carrying the marker is left alone.
    """
    _install_excepthook()
    _install_threading_hook()


def uninstall_error_hooks() -> None:
    """Restore the hooks replaced by this module (tests only).

    A hook that another party chained on top of ours is left untouched.
    """
    if _is_ours(sys.excepthook):
        sys.excepthook = getattr(sys.excepthook, _PREVIOUS)
    if _is_ours(threading.excepthook):
        threading.excepthook = getattr(threading.excepthook, _PREVIOUS)
