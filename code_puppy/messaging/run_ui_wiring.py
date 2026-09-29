"""Editor accessory wiring for the run UI.

Split from ``run_ui`` (600-line cap): the completion engine attach and
the async Ctrl+V clipboard handler. Both degrade silently without a
captured event loop (event-driven editing still works).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from .bottom_bar import get_bottom_bar
from .line_editor import RunningLineEditor

logger = logging.getLogger(__name__)

LoopGetter = Callable[[], Optional[asyncio.AbstractEventLoop]]


def attach_completion(editor: RunningLineEditor, get_loop: LoopGetter) -> None:
    """Attach a CompletionEngine to the editor (Phase B).

    The engine schedules completer queries on the captured loop and
    paints the popup on the bottom bar.
    """
    loop = get_loop()
    if loop is None or loop.is_closed():
        return
    try:
        from .editor_completion import CompletionEngine
    except ImportError:
        return

    def _repaint_popup() -> None:
        engine = holder.get("engine")
        if engine is None:
            return
        try:
            lines, selected = engine.popup_rows()
            get_bottom_bar().set_popup_lines(lines, selected)
        except Exception:
            logger.debug("popup repaint failed", exc_info=True)
        editor.repaint()

    holder: dict = {}
    engine = CompletionEngine(
        loop, apply_edit=editor.apply_completion, repaint=_repaint_popup
    )
    holder["engine"] = engine
    editor.attach_completion(engine)


def make_clipboard_handler(editor: RunningLineEditor, get_loop: LoopGetter):
    """Ctrl+V: hop the (slow, subprocess-backed) clipboard read onto the
    loop's executor — never block the key-listener thread."""

    def _handler() -> None:
        loop = get_loop()
        if loop is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(_clipboard_paste(editor), loop)
        except RuntimeError:
            pass  # loop shut down between check and call

    return _handler


async def _clipboard_paste(editor: RunningLineEditor) -> None:
    """Read the clipboard off-loop and insert the result (image or text)."""
    try:
        from .editor_paste import read_clipboard_smart

        _kind, text = await asyncio.get_running_loop().run_in_executor(
            None, read_clipboard_smart
        )
    except Exception:
        logger.debug("clipboard paste failed", exc_info=True)
        return
    if text:
        editor.insert_paste_text(text)


def make_help_overlay_handler(get_loop: LoopGetter) -> Callable[[], None]:
    """Tab-on-empty-buffer: hop the fullscreen help overlay onto the loop's
    executor -- never block (or read stdin from) the key-listener thread.

    Mirrors ``make_external_edit_handler`` (external_editor.py): the actual
    ``suspended_run_ui()`` call happens on a pool thread, never the listener
    thread itself or the main loop thread, so releasing the listener can't
    deadlock against the very thread asking for the release.
    """

    def _handler() -> None:
        loop = get_loop()
        if loop is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(_help_overlay_session(), loop)
        except RuntimeError:
            pass  # loop shut down between check and call

    return _handler


async def _help_overlay_session() -> None:
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, _show_help_overlay_with_suspended_ui
        )
    except Exception:
        logger.debug("help overlay session crashed", exc_info=True)


def _show_help_overlay_with_suspended_ui() -> None:
    """Release stdin + scroll region for the overlay's lifetime."""
    from code_puppy.command_line.help_overlay import show_help_overlay

    from .run_ui import suspended_run_ui

    with suspended_run_ui():
        show_help_overlay()


__all__ = [
    "attach_completion",
    "make_clipboard_handler",
    "make_help_overlay_handler",
]
