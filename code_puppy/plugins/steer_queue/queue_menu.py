"""The /queue TUI: view / add / edit / delete queued prompts.

Runs as an async coroutine driven by ``asyncio.run`` on a worker thread
(the same pattern as ``interactive_set_picker``), while the caller has
already released the terminal via ``suspended_run_ui`` -- both the idle
REPL and the mid-run drain wrap command execution in it.

Mutations write back through
``PauseController.replace_pending_steer_queued`` / ``request_steer`` so
the '(N queued)' status suffix updates via the controller's listeners.
Concurrent drains aren't a concern while the menu is open: mid-run the
agent is paused at its boundary, and at idle nothing consumes the queue.
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

_ADD = "[ Add prompt ]"
_DONE = "[ Done ]"
_EDIT = "Edit"
_DELETE = "Delete"
_BACK = "Back"

_PREVIEW_CELLS = 56  # menu-row preview length for long prompts


def _preview(text: str) -> str:
    flat = " ".join(text.split())  # collapse newlines for the menu row
    if len(flat) <= _PREVIEW_CELLS:
        return flat
    return flat[: _PREVIEW_CELLS - 1] + "\u2026"


async def _input_line(prompt_text: str, default: str = "") -> Optional[str]:
    """One line of input with editing; None on Ctrl+C / Ctrl+D."""
    from prompt_toolkit import PromptSession

    try:
        return await PromptSession().prompt_async(prompt_text, default=default)
    except (KeyboardInterrupt, EOFError):
        return None


async def run_queue_menu() -> None:
    """Main loop: list -> item actions -> back, until Done / Ctrl+C."""
    from code_puppy.messaging.pause_controller import get_pause_controller
    from code_puppy.tools.common import arrow_select_async

    pc = get_pause_controller()
    while True:
        items = pc.peek_pending_steer_queued()
        choices = [f"{i + 1}. {_preview(text)}" for i, text in enumerate(items)]
        choices += [_ADD, _DONE]

        def _full_text(index: int, _items: List[str] = items) -> str:
            return _items[index] if index < len(_items) else ""

        try:
            selection = await arrow_select_async(
                f"Prompt queue \u2014 {len(items)} item(s)",
                choices,
                preview_callback=_full_text,
            )
        except KeyboardInterrupt:
            return

        if selection == _DONE:
            return
        if selection == _ADD:
            text = await _input_line("(add) > ")
            if text and text.strip():
                pc.request_steer(text, mode="queue")
            continue

        index = choices.index(selection)
        await _item_menu(pc, index)


async def _item_menu(pc, index: int) -> None:
    """Actions for one queued prompt: edit / delete / back."""
    from code_puppy.tools.common import arrow_select_async

    items = pc.peek_pending_steer_queued()
    if index >= len(items):
        return  # queue changed underneath us; back to the list
    try:
        action = await arrow_select_async(items[index], [_EDIT, _DELETE, _BACK])
    except KeyboardInterrupt:
        return

    if action == _EDIT:
        text = await _input_line("(edit) > ", default=items[index])
        if text is not None and text.strip():
            items[index] = text
            pc.replace_pending_steer_queued(items)
    elif action == _DELETE:
        del items[index]
        pc.replace_pending_steer_queued(items)


def open_queue_menu_blocking(timeout_s: float = 600.0) -> None:
    """Run the menu on a worker thread with its own event loop.

    Same pattern as ``interactive_set_picker``'s caller: prompt_toolkit
    apps can't ``run()`` inside the already-running main loop, so hop to
    a thread and ``asyncio.run`` there. Never raises.
    """
    import asyncio
    import concurrent.futures

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.submit(lambda: asyncio.run(run_queue_menu())).result(
                timeout=timeout_s
            )
    except Exception:
        logger.debug("queue menu failed", exc_info=True)


__all__ = ["open_queue_menu_blocking", "run_queue_menu"]
