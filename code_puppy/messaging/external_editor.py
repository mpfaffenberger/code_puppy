"""Ctrl+X Ctrl+E: edit the prompt buffer in an external editor.

The classic readline "edit-and-execute" chord: snapshot the buffer to a
temp file, launch ``$VISUAL`` / ``$EDITOR`` with the terminal handed
over (``suspended_run_ui()`` releases both stdin and the scroll region,
same as the prompt_toolkit TUIs), then load the saved text back into
the prompt on exit. A nonzero editor exit keeps the original buffer —
bash semantics.

The handler is wired by ``run_ui`` next to the Ctrl+V clipboard
handler and follows the same threading contract: the key-listener
thread only schedules a coroutine on the captured loop; the blocking
editor session runs in the loop's executor.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
import subprocess
import tempfile
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

#: Same LoopGetter contract as run_ui_wiring.
LoopGetter = Callable[[], Optional[asyncio.AbstractEventLoop]]


def resolve_editor_command() -> List[str]:
    """Editor argv: ``$VISUAL`` → ``$EDITOR`` → platform fallback.

    Values may carry arguments (e.g. ``code --wait``); they're split
    shell-style. Windows paths keep their backslashes (posix=False).
    """
    for var in ("VISUAL", "EDITOR"):
        cmd = os.environ.get(var, "").strip()
        if cmd:
            try:
                argv = shlex.split(cmd, posix=os.name != "nt")
            except ValueError:
                argv = [cmd]
            if os.name == "nt":  # posix=False keeps surrounding quotes
                argv = [a.strip('"') if a.startswith('"') else a for a in argv]
            if argv:
                return argv
    if os.name == "nt":
        return ["notepad"]
    for fallback in ("nano", "vi"):
        if shutil.which(fallback):
            return [fallback]
    return ["vi"]


def edit_text_blocking(initial: str) -> Optional[str]:
    """Run the editor on ``initial``; return the saved text or ``None``.

    Blocking — the caller owns the terminal-handover and threading
    concerns. ``None`` means "keep the original buffer": editor failed
    to launch, exited nonzero, or the temp file went unreadable.
    """
    fd, path = tempfile.mkstemp(prefix="code_puppy_prompt_", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(initial)
        try:
            rc = subprocess.call(resolve_editor_command() + [path])
        except Exception:
            logger.debug("external editor failed to launch", exc_info=True)
            return None
        if rc != 0:
            return None
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except Exception:
        logger.debug("external edit session failed", exc_info=True)
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    # Editors append a trailing newline on save; submitting it would be
    # a surprise. Strip exactly one (intentional blank lines survive).
    if text.endswith("\r\n"):
        return text[:-2]
    if text.endswith("\n"):
        return text[:-1]
    return text


def make_external_edit_handler(editor, get_loop: LoopGetter) -> Callable[[], None]:
    """Ctrl+X Ctrl+E: hop the blocking editor session onto the loop's
    executor — never block (or read stdin from) the key-listener thread."""

    def _handler() -> None:
        loop = get_loop()
        if loop is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(_edit_session(editor), loop)
        except RuntimeError:
            pass  # loop shut down between check and call

    return _handler


async def _edit_session(editor) -> None:
    """Snapshot → external edit (terminal handed over) → buffer replace."""
    initial = editor.buffer
    try:
        result = await asyncio.get_running_loop().run_in_executor(
            None, _edit_with_suspended_ui, initial
        )
    except Exception:
        logger.debug("external edit session crashed", exc_info=True)
        return
    if result is not None and result != initial:
        editor.replace_buffer_text(result)


def _edit_with_suspended_ui(initial: str) -> Optional[str]:
    """Release stdin + scroll region for the editor's lifetime."""
    from .run_ui import suspended_run_ui

    with suspended_run_ui():
        return edit_text_blocking(initial)


__all__ = [
    "edit_text_blocking",
    "make_external_edit_handler",
    "resolve_editor_command",
]
