"""Plugin: `/btw` — ask a quick side question without derailing the task.

Runs an independent, single-turn model query (fresh throwaway agent, no
tools, no shared history) and shows the answer inline, Claude Code
style. The main conversation's context window never sees the exchange,
so minor "by the way..." curiosities stop costing you expensive tokens.

Mid-run behaviour comes free from ``run_ui._run_paused_commands``:
slash commands typed while the agent works are queued, the in-flight
stream finishes, the agent parks at its pause boundary, the command
runs with the terminal released, then the run resumes. `/btw` just has
to behave like any other blocking command inside that window — and the
dismiss-wait keeps the window open until the user has read the answer.

Usage:
    /btw <question>     One-shot side query, answer shown inline
    /btw --help         Show usage
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)

COMMAND_NAME = "btw"

_USAGE = (
    "Usage: /btw <question>\n"
    "  Runs an independent single-turn query and shows the answer in a\n"
    "  temporary overlay. Your main conversation history is untouched."
)


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            COMMAND_NAME,
            "Quick side question, answered inline (single turn, history untouched)",
        )
    ]


def _parse_question(command: str) -> Optional[str]:
    """Return the question text, or None if usage was shown instead."""
    parts = command.split(maxsplit=1)
    question = parts[1].strip() if len(parts) == 2 else ""
    if not question or question in {"--help", "-h", "help"}:
        from code_puppy.messaging import emit_info

        emit_info(_USAGE)
        return None
    return question


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if name != COMMAND_NAME:
        return None

    question = _parse_question(command)
    if question is None:
        return True

    from code_puppy.messaging import emit_error, emit_info

    from . import inline_view
    from .side_query import ask_blocking, resolve_model_name

    model_name = resolve_model_name()
    if not model_name:
        emit_error("/btw: could not resolve a model to ask. Check your model config.")
        return True

    tty = inline_view.is_tty()
    if tty:
        inline_view.show_asking(question, model_name)
    else:
        emit_info(f"btw: asking {model_name} (side query, history untouched)...")

    try:
        answer = ask_blocking(model_name, question)
    except Exception as exc:
        emit_error(f"/btw failed ({type(exc).__name__}): {exc}")
        return True

    if tty:
        inline_view.show_answer(answer)
        inline_view.wait_for_dismiss()
    else:
        inline_view.emit_fallback(question, answer)
    return True


register_callback("custom_command", _handle_custom_command)
register_callback("custom_command_help", _custom_help)


__all__ = [
    "COMMAND_NAME",
    "_custom_help",
    "_handle_custom_command",
    "_parse_question",
]
