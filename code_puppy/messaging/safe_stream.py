"""Output proxies that survive a dead stdout handle.

A detached or closed terminal answers ``isatty()`` and then fails every
``write``/``flush`` with ``EINVAL``/``EPIPE``/``EBADF``. Display code should
degrade to silence instead of aborting the agent run, but only for that
specific failure: any other ``OSError`` (disk full, quota, ...) still raises.
"""

from __future__ import annotations

import errno
from typing import Any, Iterable, TextIO

_DEAD_ERRNOS = frozenset({errno.EINVAL, errno.EPIPE, errno.EBADF})
# ERROR_INVALID_HANDLE, ERROR_BROKEN_PIPE, ERROR_NO_DATA
_DEAD_WINERRORS = frozenset({6, 109, 232})


def is_dead_handle_error(exc: BaseException) -> bool:
    """True when ``exc`` means the output handle is gone for good."""
    if not isinstance(exc, OSError):
        return False
    if isinstance(exc, BrokenPipeError):
        return True
    return (
        exc.errno in _DEAD_ERRNOS or getattr(exc, "winerror", None) in _DEAD_WINERRORS
    )


class SafeTextStream:
    """Text-stream proxy that goes silent once the wrapped handle is dead.

    Everything except ``write``/``writelines``/``flush`` delegates to the
    wrapped stream, so ``isatty``/``fileno``/``encoding`` behave as before.
    """

    def __init__(self, wrapped: TextIO) -> None:
        self._wrapped = wrapped
        self._dead = False

    def write(self, text: str) -> int:
        if self._dead:
            return len(text)
        try:
            return self._wrapped.write(text)
        except OSError as exc:
            if not is_dead_handle_error(exc):
                raise
            self._dead = True
            return len(text)

    def writelines(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        if self._dead:
            return
        try:
            self._wrapped.flush()
        except OSError as exc:
            if not is_dead_handle_error(exc):
                raise
            self._dead = True

    def __getattr__(self, name: str) -> Any:
        if name == "_wrapped":
            raise AttributeError(name)
        return getattr(self._wrapped, name)


def ensure_safe_text_stream(stream: TextIO) -> TextIO:
    """Wrap ``stream`` in a :class:`SafeTextStream` unless it already is one."""
    if isinstance(stream, SafeTextStream):
        return stream
    return SafeTextStream(stream)  # type: ignore[return-value]


__all__ = ["SafeTextStream", "ensure_safe_text_stream", "is_dead_handle_error"]
