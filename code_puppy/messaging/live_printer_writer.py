"""File-like adapter that routes termflow's rendered ANSI through the active
spinner's ``Live`` region so streamed text scrolls *above* the pinned footer
instead of racing with it.

Background
----------
Mist streams assistant markdown by handing a file-like object to
``termflow.Renderer``; the renderer writes pre-rendered ANSI bytes to that
object. Historically the target was ``console.file`` — raw writes that bypass
Rich's ``Live`` coordination and therefore race with the spinner (the root
cause behind every "always-on liveliness" attempt reverting, per
``docs/IN_PLACE_STATUS_PLAN.md`` §3b).

This module replaces that target. When compact-steps is on, termflow is given
a :class:`LivePrinterWriter` instead. Each write is converted to a Rich
``Text`` (via :func:`rich.text.Text.from_ansi`, which parses ANSI escape codes
into styled spans) and handed to the spinner's ``print_above``. Rich's ``Live``
then scrolls the content above the live region in a coordinated way — one
writer, one owner, no race.

The writer buffers partial lines so we don't spam ``console.print`` for every
1-3 character drain tick from the smooth-termflow typewriter. A line is
emitted as soon as it sees a newline; the trailing partial line is flushed on
``flush()`` / ``close()`` so streaming output never gets stuck.
"""

from __future__ import annotations

import threading
from typing import Optional

from rich.console import RenderableType
from rich.text import Text


class LivePrinterWriter:
    """File-like proxy that emits termflow output above the spinner Live.

    Callers (``termflow.Renderer`` and ``SmoothTermflowWriter``) treat this as
    a ``TextIO``: they call ``write(str)`` and ``flush()``. Internally each
    write is split on newlines; complete lines are emitted immediately via
    the spinner's ``print_above`` so they land above the pinned footer and
    stay in scrollback. The trailing partial line is held until the next
    newline or an explicit flush.
    """

    def __init__(self, spinner_ref) -> None:
        # ``spinner_ref`` is a callable returning the current ``ConsoleSpinner``
        # (or None) so we don't capture a stale reference across turns.
        self._get_spinner = spinner_ref
        self._lock = threading.Lock()
        self._line_buf = ""
        self._closed = False
        # True if the most recently WRITTEN line was blank — used by
        # ``_emit_chunk`` to drop blank-line chunks that follow a blank
        # line on the previous chunk. Only updated when we actually write,
        # not when we skip, so a run of blank-line chunks collapses to a
        # single blank line in total.
        self._last_written_was_blank = False

    # ---- file-like interface used by termflow.Renderer --------------------

    def write(self, text: str) -> int:
        if not text or self._closed:
            return len(text or "")
        with self._lock:
            self._line_buf += text
            pending = self._line_buf
            # Find the last newline; everything up to and including it is
            # emitted now, the remainder stays buffered.
            idx = pending.rfind("\n")
            if idx < 0:
                return len(text)
            emit = pending[: idx + 1]
            self._line_buf = pending[idx + 1 :]
        # Emit outside the lock so a slow console.print doesn't block writes.
        self._emit_chunk(emit)
        return len(text)

    def flush(self) -> None:
        with self._lock:
            if not self._line_buf:
                return
            emit, self._line_buf = self._line_buf, ""
        self._emit_chunk(emit)

    def close(self) -> None:
        self._closed = True
        # Reset cross-chunk state so the next text part starts fresh.
        self._last_written_was_blank = False
        try:
            self.flush()
        except Exception:
            pass

    # ---- internals --------------------------------------------------------

    def _emit_chunk(self, text: str) -> None:
        """Emit one chunk (one or more complete lines) above the live region.

        ``Text.from_ansi`` parses embedded ANSI styling into Rich spans so
        colors/code blocks/etc. render correctly. ``soft_wrap=True`` tells
        Rich not to fit the text to the console width — termflow has already
        wrapped it.

        Runs of consecutive blank lines are collapsed to a single blank line.
        Models tend to emit 2-5 trailing newlines between paragraphs (termflow
        parses them as-is), which renders as 2-5 empty lines in scrollback —
        excessive whitespace the user can see. One blank line is the markdown
        convention and matches what the model visually intended.

        The collapse is per-chunk AND across-chunks. ``_last_written_was_blank``
        is updated only when we actually emit (not when we skip) so a run
        of blank-line chunks collapses to a single blank line in total.
        """
        text = _collapse_blank_lines_across(
            text, last_was_blank=self._last_written_was_blank
        )
        if text and self._last_written_was_blank and _chunk_ends_with_blank(text):
            stripped = text.lstrip("\n")
            leading_blanks = len(text) - len(stripped)
            if leading_blanks > 0 and stripped:
                text = "\n\n" + stripped
            elif leading_blanks > 0 and not stripped:
                text = ""
        if not text:
            return
        if _chunk_ends_with_blank(text):
            self._last_written_was_blank = True
        elif text.strip():
            self._last_written_was_blank = False
        spinner = (
            self._get_spinner() if callable(self._get_spinner) else self._get_spinner
        )
        if spinner is None:
            return
        try:
            renderable: RenderableType = Text.from_ansi(text)
            # end="" — the chunk already carries its own newlines; letting
            # console.print add another would double-space every line.
            spinner.print_above(renderable, soft_wrap=True, end="")
        except Exception:
            # Never let a rendering hiccup kill the stream — fall back to
            # plain text so the user still sees something.
            try:
                spinner.print_above(text, soft_wrap=True, end="")
            except Exception:
                pass


def _collapse_blank_lines(text: str) -> str:
    """Collapse runs of consecutive blank lines to a single blank line.

    Preserves the single-blank-line markdown convention between paragraphs
    while removing the 2-5 trailing newlines models often emit between
    sections, which otherwise show up as 2-5 empty lines in scrollback.
    A single trailing newline (the normal "end of line" terminator) is
    preserved.
    """
    if not text:
        return text
    # Collapse 3+ consecutive newlines (\n\n + extras) to \n\n (one blank
    # line). \n\n alone stays as a single blank line — that's the
    # paragraph separator. Do this before rstrip so we don't accidentally
    # turn a meaningful trailing \n\n into nothing.
    import re

    text = re.sub(r"\n{3,}", "\n\n", text)
    # If the chunk is *all* newlines (a leading blank-line run before the
    # first meaningful line), trim to a single blank line. The
    # line buffer holds the rest of the partial line so the next write
    # can reattach.
    leading = len(text) - len(text.lstrip("\n"))
    if leading == len(text):
        return "\n" * (1 if leading else 0)
    return text


def _chunk_ends_with_blank(text: str) -> bool:
    """True if the chunk's last line is blank (no content).

    A line is the substring between two ``\\n`` characters (or the start
    of text and the first ``\\n``). A blank line has zero content.

    Examples:
        ``"abc\\n"``            → last line is ``"abc"``  (content)    → False
        ``"abc\\n\\n"``          → last line is ``""``     (blank)     → True
        ``"abc\\ndef\\n"``       → last line is ``"def"`` (content)    → False
        ``"abc\\ndef\\n\\n"``    → last line is ``""``    (blank)      → True
        ``"\\n"``                → last line is ``""``     (blank)     → True
        ``"\\n\\n"``             → last line is ``""``     (blank)     → True
        ``""``                  → no lines                            → False
    """
    if not text:
        return False
    # Find the start of the last line. The last line is everything
    # after the rightmost ``\n``. If the chunk ends with ``\n``, that
    # ``\n`` is the terminator of the last line — the last line itself
    # is the substring from the second-to-last ``\n`` (or start) to
    # this last ``\n``.
    if text.endswith("\n"):
        # Strip the trailing ``\n`` to see what the last line's content was.
        without_term = text[:-1]
        # The last line's content is everything after the rightmost ``\n``
        # in ``without_term``.
        last_nl = without_term.rfind("\n")
        last_line = without_term[last_nl + 1 :] if last_nl >= 0 else without_term
        return last_line == ""
    # No trailing ``\n`` — the last line is the substring after the last
    # ``\n`` (or the whole text if no ``\n``).
    last_nl = text.rfind("\n")
    last_line = text[last_nl + 1 :] if last_nl >= 0 else text
    return last_line == ""


def _collapse_blank_lines_across(text: str, last_was_blank: bool) -> str:
    """Collapse 3+ consecutive newlines to a single blank line, and —
    if the previous chunk ended on a blank line — drop leading blank lines
    on this chunk entirely so we never stack more than one blank line
    across chunk boundaries either.

    This matters because termflow can emit blank lines as their own chunks
    (one ``\\n`` per write) when streaming, in which case per-chunk
    collapse alone still allows 2-5 empty lines in scrollback. Tracking
    ``last_was_blank`` across chunks closes that gap.
    """
    text = _collapse_blank_lines(text)
    if not text:
        return text
    if last_was_blank:
        # Drop leading blank lines on this chunk.
        stripped = text.lstrip("\n")
        leading_blanks = len(text) - len(stripped)
        if leading_blanks > 0:
            # Keep one blank line (the markdown paragraph separator) only
            # if the chunk has content beyond the leading blanks. Since the
            # previous chunk was already blank, we drop them all and let
            # the content lines through.
            text = stripped
    return text


class BlankLineCollapsingFile:
    """File-like wrapper that runs each complete-line chunk through
    ``_collapse_blank_lines`` before delegating to the underlying file.

    Used as the termflow output target in compact mode when no spinner is
    active (so ``LivePrinterWriter``'s ``print_above`` path doesn't apply).
    Wrapping the raw ``console.file`` here keeps the in-place compact-mode
    behaviour — at most one blank line between paragraphs — without
    requiring the spinner to be live.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self._line_buf = ""
        self._closed = False
        # Tracks whether the most recently WRITTEN content ended on a
        # blank line. A subsequent blank-line chunk is dropped (or its
        # leading blanks stripped) to keep the rendered output at a
        # single blank line between paragraphs even when the model
        # streams blank lines as their own writes.
        self._last_written_was_blank = False

    def write(self, text: str) -> int:
        if not text or self._closed:
            return len(text or "")
        self._line_buf += text
        idx = self._line_buf.rfind("\n")
        if idx < 0:
            return len(text)
        emit = self._line_buf[: idx + 1]
        self._line_buf = self._line_buf[idx + 1 :]
        collapsed = _collapse_blank_lines_across(
            emit, last_was_blank=self._last_written_was_blank
        )
        # If the previous chunk already ended on a blank line, this chunk
        # would stack another blank line on top. Strip the leading
        # blank lines but keep the trailing one (paragraph separator) only
        # if the next line in this chunk is content.
        if collapsed and self._last_written_was_blank:
            stripped = collapsed.lstrip("\n")
            leading_blanks = len(collapsed) - len(stripped)
            if leading_blanks > 0 and stripped:
                # Replace any leading blank lines with exactly one (the
                # paragraph separator between the previous content and
                # this content). I.e. ``\n\n`` is what survives.
                collapsed = "\n\n" + stripped
            elif leading_blanks > 0 and not stripped:
                # All-blank chunk and we already wrote a blank line —
                # suppress entirely.
                collapsed = ""
        if collapsed and _chunk_ends_with_blank(collapsed):
            self._last_written_was_blank = True
        elif collapsed and collapsed.strip():
            self._last_written_was_blank = False
        if collapsed:
            return self._inner.write(collapsed)
        return len(text)

    def flush(self) -> None:
        try:
            self._inner.flush()
        except Exception:
            pass

    def close(self) -> None:
        self._closed = True
        try:
            if self._line_buf:
                tail = _collapse_blank_lines_across(
                    self._line_buf, last_was_blank=self._last_written_was_blank
                )
                if tail:
                    if self._last_written_was_blank and _chunk_ends_with_blank(tail):
                        stripped = tail.lstrip("\n")
                        if stripped:
                            tail = "\n\n" + stripped
                        else:
                            tail = ""
                    self._inner.write(tail)
                self._line_buf = ""
            self._inner.close()
        except Exception:
            pass

    def isatty(self) -> bool:  # pragma: no cover
        try:
            return self._inner.isatty()
        except Exception:
            return False

    def __getattr__(self, name: str):
        # Fall through any other attribute (e.g. ``encoding``, ``mode``) to
        # the inner file. Keeps this wrapper transparent to Rich and
        # termflow's probing.
        return getattr(self._inner, name)


__all__ = ["LivePrinterWriter", "get_live_printer_writer", "BlankLineCollapsingFile"]


def get_live_printer_writer(spinner_ref) -> Optional[LivePrinterWriter]:
    """Factory used by ``event_stream_handler`` to build a per-text-part
    writer. Returns ``None`` if there's no active spinner — caller should
    fall back to ``console.file`` in that case."""
    if spinner_ref is None:
        return None
    return LivePrinterWriter(spinner_ref)
