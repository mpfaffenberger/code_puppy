"""Wire emoji_filter into the runtime.

Three points of contact, all gated by ``config.is_enabled()``:

1. ``pre_tool_call`` callback — mutates the *args dict in-place* for file-write
   and shell tools before the tool actually runs. We only touch text destined
   for disk (new_str, content, payload) and the shell command string. Search
   strings (old_str / snippet) are left alone so matching doesn't silently
   break.

2. ``startup`` callback — installs a one-time monkey-patch on
   ``pydantic_ai.messages.TextPart`` / ``TextPartDelta`` to strip emojis from
   streamed text content. ``ThinkingPart`` / ``ThinkingPartDelta`` are
   deliberately untouched.

3. ``custom_command`` / ``custom_command_help`` — a tiny ``/emoji-filter``
   slash command so the user can flip the switch without editing mist.cfg.

Failures here must never crash the app: every patch site is wrapped.
"""

from __future__ import annotations

import logging
from typing import Any

from code_puppy.callbacks import register_callback

from .config import is_enabled, set_enabled
from .stripper import strip_emojis

logger = logging.getLogger(__name__)

# Tool name → handler. Keeps the dispatch table flat and inspectable (no
# nested if/elif soup).  All handlers mutate ``args`` in place and return None.
_FILE_WRITE_TOOLS = {"create_file", "edit_file", "replace_in_file"}
_SHELL_TOOLS = {"agent_run_shell_command"}


def _strip_field(container: dict, key: str) -> bool:
    """Strip emojis from ``container[key]`` in place. Return True if it changed.

    One helper, one job. Used by every other strip-site so the
    "did anything actually change?" signal is honest and DRY.
    """
    val = container.get(key)
    if not isinstance(val, str) or not val:
        return False
    stripped = strip_emojis(val)
    if stripped == val:
        return False
    container[key] = stripped
    return True


def _filter_replacements(replacements: Any) -> int:
    """Strip emojis from each ``new_str`` in a replacements list (in place).

    Returns the number of items whose ``new_str`` was modified.
    """
    if not isinstance(replacements, list):
        return 0
    count = 0
    for item in replacements:
        if isinstance(item, dict) and _strip_field(item, "new_str"):
            count += 1
    return count


def _filter_edit_payload(payload: Any) -> list[str]:
    """Mutate an edit_file payload dict in place.

    edit_file accepts three payload shapes:
      * ContentPayload      → strip ``content``
      * ReplacementsPayload → strip each ``new_str``
      * DeleteSnippetPayload → leave alone (it's a search string)

    Returns a list of human-readable labels describing what was stripped
    (empty list = nothing changed).
    """
    if not isinstance(payload, dict):
        return []
    stripped: list[str] = []
    if _strip_field(payload, "content"):
        stripped.append("payload.content")
    if "replacements" in payload:
        n = _filter_replacements(payload["replacements"])
        if n:
            stripped.append(f"payload.replacements ({n} item{'s' if n != 1 else ''})")
    return stripped


# Notify the model when we tamper with its tool call so it stops emitting
# emojis instead of silently fighting the filter every turn. The framework
# (see ``pydantic_patches._patched_call_tool``) collects ``context_message``
# values from pre-tool-call hooks and prepends them to the tool result as
# ``[hook context]\n{msg}``, which the model then reads.
_CONTEXT_MESSAGE_TEMPLATE = (
    "emoji_filter is ENABLED. Emojis were detected and stripped from "
    "`{tool_name}` arg(s): {fields}. This project does not allow emojis "
    "in file writes, shell commands, or assistant output \u2014 please "
    "omit them in future tool calls and responses."
)


def _on_pre_tool_call(
    tool_name: str, tool_args: dict, context: Any = None
) -> dict | None:
    """Strip emojis from file-write and shell tool args, and notify the model.

    Returns ``{"context_message": ...}`` when any emojis were detected so the
    framework can surface that fact to the model via the tool result. Returns
    ``None`` otherwise (no-op for the framework).
    """
    if not is_enabled() or not isinstance(tool_args, dict):
        return None

    stripped_fields: list[str] = []
    try:
        if tool_name == "create_file":
            if _strip_field(tool_args, "content"):
                stripped_fields.append("content")

        elif tool_name == "replace_in_file":
            n = _filter_replacements(tool_args.get("replacements"))
            if n:
                stripped_fields.append(
                    f"replacements ({n} item{'s' if n != 1 else ''})"
                )

        elif tool_name == "edit_file":
            stripped_fields.extend(_filter_edit_payload(tool_args.get("payload")))

        elif tool_name in _SHELL_TOOLS:
            if _strip_field(tool_args, "command"):
                stripped_fields.append("command")
    except Exception as exc:  # never block tool execution
        logger.debug("emoji_filter pre_tool_call failed: %s", exc)
        return None

    if not stripped_fields:
        return None

    return {
        "context_message": _CONTEXT_MESSAGE_TEMPLATE.format(
            tool_name=tool_name, fields=", ".join(stripped_fields)
        )
    }


# --- Streaming patch ---------------------------------------------------------
# We patch TextPart and TextPartDelta __init__ exactly once. The patched init
# checks ``is_enabled()`` at call time so the user can toggle without restart.

_STREAM_PATCH_FLAG = "_emoji_filter_patched"


def _install_streaming_patch() -> None:
    try:
        from pydantic_ai.messages import TextPart, TextPartDelta
    except Exception as exc:
        logger.debug("emoji_filter: pydantic_ai.messages unavailable: %s", exc)
        return

    for cls, attr in ((TextPartDelta, "content_delta"), (TextPart, "content")):
        if getattr(cls, _STREAM_PATCH_FLAG, False):
            continue
        _wrap_init(cls, attr)


def _wrap_init(cls: type, content_attr: str) -> None:
    original_init = cls.__init__

    def patched_init(self, *args, **kwargs):  # noqa: ANN001 - dataclass-y
        original_init(self, *args, **kwargs)
        if not is_enabled():
            return
        try:
            current = getattr(self, content_attr, None)
            if isinstance(current, str) and current:
                stripped = strip_emojis(current)
                if stripped != current:
                    setattr(self, content_attr, stripped)
        except Exception as exc:  # defensive: never break message construction
            logger.debug(
                "emoji_filter stream patch failed on %s: %s", cls.__name__, exc
            )

    cls.__init__ = patched_init  # type: ignore[method-assign]
    setattr(cls, _STREAM_PATCH_FLAG, True)


def _on_startup() -> None:
    _install_streaming_patch()


# --- /emoji-filter slash command --------------------------------------------

_COMMAND_NAMES = {"emoji-filter", "emojifilter"}


def _custom_help():
    return [
        ("emoji-filter", "Show / toggle the emoji filter (on|off|status)"),
    ]


def _handle_command(command: str, name: str):
    if name not in _COMMAND_NAMES:
        return None

    from code_puppy.messaging import emit_info

    parts = command.split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) == 2 else "status"

    if arg in ("on", "enable", "enabled", "true", "1"):
        set_enabled(True)
        emit_info(
            "emoji_filter: ON (emojis will be stripped from outputs/file writes/shell)"
        )
        return True
    if arg in ("off", "disable", "disabled", "false", "0"):
        set_enabled(False)
        emit_info("emoji_filter: OFF (emojis pass through untouched)")
        return True
    if arg in ("status", ""):
        state = "ON" if is_enabled() else "OFF"
        emit_info(f"emoji_filter: {state}")
        return True

    emit_info("Usage: /emoji-filter [on|off|status]")
    return True


# --- Registration ------------------------------------------------------------

register_callback("startup", _on_startup)
register_callback("pre_tool_call", _on_pre_tool_call)
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_command)
