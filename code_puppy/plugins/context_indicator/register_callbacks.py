"""Register callbacks for the ``context_indicator`` plugin.

Hooks:

* ``startup`` — wraps ``get_prompt_with_active_model`` to inject a colored
  circle (🟢/🟡/🔴) reflecting current context-window usage.
* ``custom_command`` / ``custom_command_help`` — exposes ``/context`` for a
  detailed token-usage breakdown.

Idempotent: re-installing the prompt patch is a no-op.
"""

from __future__ import annotations

from typing import List, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.plugins.context_indicator.usage import (
    ContextUsage,
    get_current_usage,
)

_COMMAND_NAME = "context"
_PATCH_ATTR = "_context_indicator_original"


# ---------------------------------------------------------------------------
# Messaging helpers (lazy-imported to dodge circular imports at boot)
# ---------------------------------------------------------------------------
def _emit_info(message: str) -> None:
    from code_puppy.messaging import emit_info

    emit_info(message)


def _emit_error(message: str) -> None:
    from code_puppy.messaging import emit_error

    emit_error(message)


# ---------------------------------------------------------------------------
# Prompt patching
# ---------------------------------------------------------------------------
def _build_indicator_tuple(usage: ContextUsage) -> Tuple[str, str]:
    """Build the (style, text) tuple that gets inserted into the prompt."""
    return ("class:context-indicator", f"{usage.indicator} ")


def _inject_indicator(formatted_text):
    """Return a new ``FormattedText`` with the usage indicator prepended.

    Placed AFTER the dog emoji but BEFORE the puppy name so the colored
    circle reads as a status badge for the prompt as a whole.
    """
    from prompt_toolkit.formatted_text import FormattedText

    usage = get_current_usage()
    if usage is None:
        return formatted_text

    try:
        parts = list(formatted_text)
        # Insert after the leading "🐶 " tuple (index 0) so the badge sits
        # right next to the puppy. Fall back to prepend if shape changed.
        insert_at = 1 if parts else 0
        parts.insert(insert_at, _build_indicator_tuple(usage))
        return FormattedText(parts)
    except Exception:
        return formatted_text


def _install_prompt_patch() -> None:
    """Monkey-patch ``get_prompt_with_active_model`` once."""
    from code_puppy.command_line import prompt_toolkit_completion as ptc

    if getattr(ptc, _PATCH_ATTR, None) is not None:
        return  # Already patched

    original = ptc.get_prompt_with_active_model
    setattr(ptc, _PATCH_ATTR, original)

    def patched(base: str = ">>> "):
        result = original(base)
        return _inject_indicator(result)

    ptc.get_prompt_with_active_model = patched


def _on_startup() -> None:
    try:
        _install_prompt_patch()
    except Exception as exc:
        _emit_error(f"context_indicator: failed to install prompt patch — {exc}")


# ---------------------------------------------------------------------------
# /context slash command
# ---------------------------------------------------------------------------
def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            _COMMAND_NAME,
            "Show context-window usage (tokens used vs. model capacity)",
        )
    ]


def _format_usage_report(usage: ContextUsage) -> str:
    bar_width = 30
    filled = min(bar_width, max(0, int(round(usage.proportion * bar_width))))
    bar = "█" * filled + "░" * (bar_width - filled)
    return (
        f"{usage.indicator} Context usage: {usage.percent:.1f}%\n"
        f"  [{bar}]\n"
        f"  Messages : {usage.used_tokens:,} tokens\n"
        f"  Overhead : {usage.overhead_tokens:,} tokens (system prompt + tools)\n"
        f"  Total    : {usage.total_tokens:,} / {usage.capacity:,} tokens\n"
        f"  Buckets  : 🟢 <30%   🟡 30–60%   🔴 >60%"
    )


def _handle_context_command(command: str) -> bool:
    usage = get_current_usage()
    if usage is None:
        _emit_info("🐶 No context info yet — load an agent and send a message first.")
        return True
    _emit_info(_format_usage_report(usage))
    return True


def _handle_custom_command(command: str, name: str):
    if name != _COMMAND_NAME:
        return None
    return _handle_context_command(command)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
register_callback("startup", _on_startup)
register_callback("custom_command", _handle_custom_command)
register_callback("custom_command_help", _custom_help)


__all__ = [
    "_build_indicator_tuple",
    "_custom_help",
    "_format_usage_report",
    "_handle_context_command",
    "_handle_custom_command",
    "_inject_indicator",
    "_install_prompt_patch",
    "_on_startup",
]
