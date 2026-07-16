"""Register callbacks for the prompt_newline plugin.

This plugin is a tiny ergonomics hack: it places the user's input cursor on a
*new line* below the puppy/agent/model/cwd chrome, so long working-directory
paths don't squeeze the typing area.

It hooks two things:

* ``startup`` — wraps ``get_prompt_with_active_model`` so the FormattedText it
  returns gets a trailing ``\\n`` appended **at call time** (so the slash
  command toggle takes effect immediately, no restart needed).
* ``custom_command`` / ``custom_command_help`` — exposes ``/prompt_newline``
  for runtime on/off, persisted via ``puppy.cfg``.

Default: OFF. Opt-in only.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.plugins.prompt_newline.config import is_enabled, set_enabled

_COMMAND_NAME = "prompt_newline"
_PATCH_ATTR = "_prompt_newline_original"


def _emit_info(message: str) -> None:
    from code_puppy.messaging import emit_info

    emit_info(message)


def _emit_error(message: str) -> None:
    from code_puppy.messaging import emit_error

    emit_error(message)


def _emit_success(message: str) -> None:
    from code_puppy.messaging import emit_success

    emit_success(message)


def _append_newline(formatted_text):
    """Return a new FormattedText with a trailing newline tuple.

    ``FormattedText`` is a ``list`` subclass of ``(style, text)`` tuples, so we
    rebuild it rather than mutating in place — the upstream caller may cache
    or reuse the returned object.
    """
    from prompt_toolkit.formatted_text import FormattedText

    try:
        return FormattedText(list(formatted_text) + [("", "\n")])
    except Exception:
        # Defensive: never break the prompt if the upstream shape changes.
        return formatted_text


def _install_prompt_patch() -> None:
    """Monkey-patch ``get_prompt_with_active_model`` to honor ``is_enabled()``.

    Idempotent: re-running won't double-wrap.
    """
    from code_puppy.command_line import prompt_toolkit_completion as ptc

    if getattr(ptc, _PATCH_ATTR, None) is not None:
        return  # Already patched

    original = ptc.get_prompt_with_active_model
    setattr(ptc, _PATCH_ATTR, original)

    def patched(base: str = ">>> "):
        result = original(base)
        if is_enabled():
            return _append_newline(result)
        return result

    ptc.get_prompt_with_active_model = patched


def _on_startup() -> None:
    try:
        _install_prompt_patch()
    except Exception as exc:
        # Plugins must fail gracefully — never crash the app.
        _emit_error(f"prompt_newline: failed to install prompt patch — {exc}")


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            _COMMAND_NAME,
            "Toggle placing user input on a new line below the prompt chrome",
        )
    ]


def _parse_toggle_arg(command: str) -> Optional[bool]:
    """Parse ``/prompt_newline [on|off|true|false|toggle]``.

    Returns:
        True/False for an explicit set, or ``None`` to mean "flip current".
    """
    tokens = command.strip().split()
    if len(tokens) < 2:
        return None  # bare /prompt_newline → flip
    arg = tokens[1].lower()
    if arg in ("on", "true", "1", "yes", "enable", "enabled"):
        return True
    if arg in ("off", "false", "0", "no", "disable", "disabled"):
        return False
    if arg in ("toggle",):
        return None
    raise ValueError(arg)


def _handle_prompt_newline_command(command: str) -> bool:
    try:
        target = _parse_toggle_arg(command)
    except ValueError as exc:
        _emit_error(
            f"/{_COMMAND_NAME}: unknown argument '{exc.args[0]}'. "
            "Usage: /prompt_newline [on|off|toggle]"
        )
        return True

    if target is None:
        target = not is_enabled()

    set_enabled(target)
    state = "ON" if target else "OFF"
    _emit_success(f"🐶 prompt_newline is now {state}")
    if target:
        _emit_info("Your input will appear on a fresh line below the prompt chrome.")
    else:
        _emit_info("Prompt is back to single-line mode.")
    return True


def _handle_custom_command(command: str, name: str):
    if name != _COMMAND_NAME:
        return None
    return _handle_prompt_newline_command(command)


register_callback("startup", _on_startup)
register_callback("custom_command", _handle_custom_command)
register_callback("custom_command_help", _custom_help)


__all__ = [
    "_append_newline",
    "_custom_help",
    "_handle_custom_command",
    "_handle_prompt_newline_command",
    "_install_prompt_patch",
    "_on_startup",
    "_parse_toggle_arg",
]
