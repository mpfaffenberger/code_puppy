"""Turn pydantic-ai's output-budget exhaustion error into an actionable hint."""

from __future__ import annotations

import re
from typing import Any, Iterator, Optional

from rich.markup import escape

_TOKEN_LIMIT_PATTERN = re.compile(
    r"Model token limit \(([^)]+)\) exceeded before any response was generated"
)
_MAX_CHAIN_DEPTH = 5


def _walk_chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    for _ in range(_MAX_CHAIN_DEPTH):
        if current is None or id(current) in seen:
            return
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _safe_text(value: Any) -> Optional[str]:
    try:
        return str(value)
    except Exception:
        return None


def resolve_model_name(agent: Any) -> Optional[str]:
    """Best-effort model name for diagnostics; never raises."""
    try:
        return agent.get_model_name()
    except Exception:
        return None


def token_limit_hint(exc: BaseException, model_name: Optional[str]) -> Optional[str]:
    """Rich-markup hint when ``exc`` is an output-budget exhaustion, else ``None``."""
    for link in _walk_chain(exc):
        text = _safe_text(link)
        match = _TOKEN_LIMIT_PATTERN.search(text) if text else None
        if match:
            break
    else:
        return None

    name = _safe_text(model_name) if model_name else None
    subject = f"[bold]{escape(name)}[/bold]" if name else "The model"
    cap = match.group(1)
    budget = f"{cap}-token" if cap.isdigit() else "provider-default"
    return (
        f"{subject} used its entire {budget} output budget before "
        "producing a response (reasoning counts against it). Run "
        "[cyan]/model_settings[/cyan], select this model, and raise "
        "[cyan]Max Output Tokens[/cyan]."
    )


__all__ = ["resolve_model_name", "token_limit_hint"]
