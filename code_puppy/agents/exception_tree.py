"""Shared traversal for wrapped and grouped model exceptions."""

from __future__ import annotations

from typing import Iterator

try:  # pragma: no cover - Python 3.11+ builtin, retained for embedders
    from builtins import BaseExceptionGroup
except ImportError:  # pragma: no cover - Python 3.10 only
    BaseExceptionGroup = Exception  # type: ignore[misc,assignment]


def _walk_cause_chain(
    exc: BaseException, max_depth: int = 5
) -> Iterator[BaseException]:
    """Yield a depth-capped, cycle-safe cause/context chain from ``exc``."""
    seen: set[int] = set()
    current: BaseException | None = exc
    for _ in range(max_depth):
        if current is None or id(current) in seen:
            return
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _group_members(exc: BaseException) -> tuple[BaseException, ...]:
    """Return group members without treating every 3.10 exception as a group."""
    if BaseExceptionGroup is Exception:  # pragma: no cover - Python 3.10 only
        return ()
    if isinstance(exc, BaseExceptionGroup):
        return tuple(exc.exceptions)
    return ()


def walk_exception_tree(exc: BaseException) -> Iterator[BaseException]:
    """Yield each reachable exception once across chains and exception groups.

    The same traversal underpins retry classification and private provider
    adapters, preventing subtle wrapping semantics from drifting between them.
    """
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        for link in _walk_cause_chain(node):
            if id(link) in seen:
                continue
            seen.add(id(link))
            yield link
            stack.extend(_group_members(link))
