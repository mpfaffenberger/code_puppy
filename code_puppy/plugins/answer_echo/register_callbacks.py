"""Echo ``ask_user_question`` answers to scrollback after the TUI exits.

Hooks the ``post_tool_call`` callback. When the tool is
``ask_user_question`` and the result is a successful
``AskUserQuestionOutput``, prints a compact one-line-per-question summary
so the user can see what they answered once the alt-screen TUI is gone.
"""

from __future__ import annotations

from typing import Any

from code_puppy.callbacks import register_callback

# We import the models lazily inside the handler — registering the callback
# shouldn't fail if the ask_user_question module is unavailable (e.g. a
# stripped-down test environment).

_OTHER_LABEL = "Other"
_MAX_SUMMARY_LEN = 200
_MAX_LABEL_LEN = 60


def _truncate(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def _format_selection(answer: Any) -> str:
    """Format a single QuestionAnswer as a short `→ value` segment.

    Multi-select joins options with ``+``. ``Other`` text replaces the
    label so the user sees what they actually typed.
    """
    if not answer:
        return "(no selection)"
    selections = list(answer.selected_options or [])
    if answer.other_text:
        selections.append(
            f"{_OTHER_LABEL}: {_truncate(answer.other_text, _MAX_LABEL_LEN)}"
        )
    if not selections:
        return "(no selection)"
    return ", ".join(_truncate(s, _MAX_LABEL_LEN) for s in selections)


def _build_summary(result: Any) -> str:
    """Build the one-line summary printed to scrollback.

    Returns an empty string when there's nothing useful to display
    (e.g. the result is a model we don't recognise).
    """
    answers = list(getattr(result, "answers", None) or [])
    if not answers:
        return ""
    parts: list[str] = []
    for a in answers:
        header = _truncate(a.question_header or "question", _MAX_LABEL_LEN)
        parts.append(f"{header} → {_format_selection(a)}")
    summary = "; ".join(parts)
    return _truncate(summary, _MAX_SUMMARY_LEN)


def _terminal_outcome_line(result: Any) -> str:
    """Format a non-success result (cancelled / timed_out / error)."""
    if getattr(result, "cancelled", False):
        return "User cancelled the question prompt."
    if getattr(result, "timed_out", False):
        return "User did not answer in time (timed out)."
    err = getattr(result, "error", None)
    if err:
        return _truncate(f"ask_user_question error: {err}", _MAX_SUMMARY_LEN)
    return ""


def _emit(text: str, *, dim: bool = False) -> None:
    """Push a single line to the message bus; never raise into the agent."""
    if not text:
        return
    try:
        from code_puppy.messaging import emit_info

        style_arg = {"style": "dim"} if dim else None
        if style_arg:
            emit_info(f"[dim]{text}[/dim]")
        else:
            emit_info(text)
    except Exception:
        # Never let scrollback formatting take down the agent.
        try:
            import sys

            sys.stderr.write(f"{text}\n")
        except Exception:
            pass


async def _on_post_tool_call(
    tool_name: str,
    tool_args: dict,
    result: Any,
    duration_ms: float,
    context: Any = None,
) -> None:
    try:
        if tool_name != "ask_user_question":
            return

        # Handle the non-success cases first — they're cheap and short.
        outcome = _terminal_outcome_line(result)
        if outcome:
            _emit(outcome, dim=True)
            return

        # Try to import the output type for an isinstance check. If the
        # module is missing, or the result isn't an instance of that type
        # but still has the shape we need, fall back to duck-typing on
        # the attributes we actually use — covers tests / mocks that
        # don't construct a full pydantic model.
        is_typed = False
        try:
            from code_puppy.tools.ask_user_question.models import (
                AskUserQuestionOutput,
            )

            if isinstance(result, AskUserQuestionOutput):
                is_typed = True
        except Exception:
            pass
        if not is_typed:
            is_typed = hasattr(result, "answers") and hasattr(result, "cancelled")

        if not is_typed:
            return

        summary = _build_summary(result)
        if summary:
            _emit(f"▸ User answered: {summary}")
    except Exception:
        # Swallow — echo is a UX nicety, never a correctness requirement.
        pass


register_callback("post_tool_call", _on_post_tool_call)
