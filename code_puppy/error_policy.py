"""Pure policy: which exceptions are worth writing to ``errors.log``.

Only the raised type is inspected (never ``__cause__``/``__context__``), so a
``ValueError`` raised ``from KeyboardInterrupt`` is still reported. Exception
groups are judged by their leaves only. There is no message matching: expected
flow is opt-in, through :class:`ExpectedFlow` or ``expected=True``.

Depends on: stdlib only (no I/O, no logging).
"""

from __future__ import annotations

import asyncio
from typing import Final


class ExpectedFlow(Exception):
    """Raised (or wrapped) for control flow that looks like an error but is not one."""


NEVER_REPORT: Final[tuple[type[BaseException], ...]] = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
    asyncio.CancelledError,
    StopIteration,
    StopAsyncIteration,
)


def _leaves(exc: BaseException) -> list[BaseException]:
    """Flatten nested exception groups into their leaf exceptions."""
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for inner in exc.exceptions for leaf in _leaves(inner)]
    return [exc]


def is_expected(exc: BaseException, *, expected: bool = False) -> bool:
    """True when the event is an anticipated flow (``expected=True`` or ExpectedFlow).

    Distinct from :func:`should_report` so callers can tell "expected" from
    "never reportable". A group is expected only if every leaf is ExpectedFlow.
    """
    if expected:
        return True
    return all(isinstance(leaf, ExpectedFlow) for leaf in _leaves(exc))


def should_report(exc: BaseException, *, expected: bool = False) -> bool:
    """False for NEVER_REPORT types (and subclasses) and expected flows.

    A group is silenced only when every leaf is NEVER_REPORT or ExpectedFlow.
    """
    if expected:
        return False
    return not all(
        isinstance(leaf, (*NEVER_REPORT, ExpectedFlow)) for leaf in _leaves(exc)
    )


def never_report(exc: BaseException) -> bool:
    """True when every leaf is a NEVER_REPORT type, regardless of ``expected``.

    ``expected=True`` can silence an event, but a KeyboardInterrupt or
    SystemExit is never reportable even when a caller marks it expected.
    """
    return all(isinstance(leaf, NEVER_REPORT) for leaf in _leaves(exc))
