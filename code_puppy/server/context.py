"""Task-local rendering policy for headless agent runs."""

from __future__ import annotations

import contextvars

_HEADLESS: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "mist_headless_transport", default=False
)


def is_headless_transport() -> bool:
    return _HEADLESS.get()


def push_headless_transport() -> contextvars.Token[bool]:
    return _HEADLESS.set(True)


def reset_headless_transport(token: contextvars.Token[bool]) -> None:
    _HEADLESS.reset(token)
