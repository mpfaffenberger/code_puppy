"""The single owner of the ``errors.log`` record layout: field order, size caps and renderers."""

from __future__ import annotations

import logging
import reprlib
import traceback
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Size bounds. Rotation keeps one ``.1`` backup, so errors.log plus its backup
# stay under 2 * MAX_LOG_SIZE only if no single entry is unbounded: every field
# is capped and the whole entry has a hard limit.
_MAX_MESSAGE_CHARS = 4096
_MAX_ARGS_CHARS = 2048
_MAX_CONTEXT_CHARS = 1024
_MAX_TRACEBACK_CHARS = 32768
_MAX_ENTRY_CHARS = 65536

_RULE = "=" * 80


def _marker(cut: int) -> str:
    return f"…[truncated {cut} chars]"


def _cap(text: object, limit: int) -> str:
    """Keep the start of *text* and say exactly how many characters were cut.

    Not used for Args: that repr is bounded while it is built (``_args_text``),
    so how much was dropped is unknown and its marker carries no number.
    """
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + _marker(len(text) - limit)


def _cap_traceback(text: str, limit: int) -> str:
    """Keep the ``Traceback`` head line and the end (innermost frames, final line)."""
    if len(text) <= limit:
        return text
    head_end = text.find("\n") + 1
    start = max(len(text) - max(limit - head_end, 0), head_end)
    if start > head_end and text[start - 1] != "\n":
        newline = text.find("\n", start)
        if 0 <= newline < len(text) - 1:
            start = newline + 1  # begin the kept tail on a whole line
    return text[:head_end] + _marker(start - head_end) + "\n" + text[start:]


def cap_entry(entry: str) -> str:
    """Final guard: no entry exceeds ``_MAX_ENTRY_CHARS``; the header is kept."""
    if len(entry) <= _MAX_ENTRY_CHARS:
        return entry
    footer_room = len(f"\n{_marker(len(entry))}\n{_RULE}\n")
    keep = _MAX_ENTRY_CHARS - footer_room
    return f"{entry[:keep]}\n{_marker(len(entry) - keep)}\n{_RULE}\n"


# reprlib bounds the repr as it builds it for builtin containers and strings,
# so a huge one is never rendered in full; for any other object, ints included,
# it calls repr() unbounded and only then truncates (accepted: transient, output
# bounded). It marks every elision with ``fillvalue``. U+FDD0 is a non-printable
# noncharacter, so the builtin reprs always escape it and finding it means
# something was elided, with no need to measure the full repr. A custom
# __repr__ returning it raw can only cause a spurious marker; output stays bounded.
_ELIDED = "\ufdd0"
_ELIDED_MARKER = "…[truncated, repr elided]"
_args_repr = reprlib.Repr()
_args_repr.fillvalue = _ELIDED
_args_repr.maxlevel = 6
_args_repr.maxtuple = _args_repr.maxlist = _args_repr.maxdict = 32
_args_repr.maxset = _args_repr.maxfrozenset = _args_repr.maxdeque = 32
_args_repr.maxarray = 32
_args_repr.maxlong = _MAX_ARGS_CHARS  # the default of 40 would elide a 100-digit int
_args_repr.maxstring = _args_repr.maxother = _MAX_ARGS_CHARS


def _args_text(args: object) -> str:
    """Bounded repr of *args*; ends with a fixed marker when anything was elided or cut."""
    text = _args_repr.repr(args)
    elided = _ELIDED in text
    text = text.replace(_ELIDED, "...")
    if elided or len(text) > _MAX_ARGS_CHARS:
        return text[:_MAX_ARGS_CHARS] + _ELIDED_MARKER
    return text


def _format_traceback(error: BaseException) -> str:
    """The traceback text with each chunk (so each exception line) capped first."""
    chunks = []
    for chunk in traceback.TracebackException.from_exception(error).format():
        body, newline = (chunk[:-1], "\n") if chunk.endswith("\n") else (chunk, "")
        chunks.append(_cap(body, _MAX_MESSAGE_CHARS) + newline)
    return _cap_traceback("".join(chunks), _MAX_TRACEBACK_CHARS)


def _bare_entry(timestamp: str, *lines: str) -> str:
    return "\n".join([f"\n{_RULE}", f"Timestamp: {timestamp}", *lines, f"{_RULE}\n"])


def _build_error_entry(
    error: BaseException,
    context: Optional[str],
    include_traceback: bool,
    timestamp: str,
) -> str:
    """Lay out the fields: Timestamp, Error Type, Error Message, Context, Traceback, Args."""
    lines = [
        f"Error Type: {type(error).__name__}",
        f"Error Message: {_cap(str(error), _MAX_MESSAGE_CHARS)}",
    ]
    if context:
        lines.append(f"Context: {_cap(context, _MAX_CONTEXT_CHARS)}")
    if include_traceback:
        lines.append(f"Traceback:\n{_format_traceback(error)}")
    if hasattr(error, "args") and error.args:
        lines.append(f"Args: {_args_text(error.args)}")
    return _bare_entry(timestamp, *lines)


def render_error_entry(
    error: BaseException, context: Optional[str], include_traceback: bool
) -> str:
    """The ``errors.log`` entry for *error*; a bare one when rendering fails. Never raises."""
    timestamp = datetime.now().isoformat()
    try:
        return _build_error_entry(error, context, include_traceback, timestamp)
    except Exception:
        logger.debug("rendering the error entry failed", exc_info=True)
        return _bare_entry(
            timestamp,
            f"Error Type: {type(error).__name__}",
            "Error Message: <entry could not be rendered>",
        )


def render_message_entry(message: str, context: Optional[str]) -> str:
    """The ``log_error_message`` entry; a bare one when rendering fails. Never raises."""
    timestamp = datetime.now().isoformat()
    try:
        lines = [f"Message: {_cap(message, _MAX_MESSAGE_CHARS)}"]
        if context:
            lines.append(f"Context: {_cap(context, _MAX_CONTEXT_CHARS)}")
        return _bare_entry(timestamp, *lines)
    except Exception:
        logger.debug("rendering the message entry failed", exc_info=True)
        return _bare_entry(timestamp, "Message: <entry could not be rendered>")
