"""On-demand stack dumps for wedged runs (``kill -USR2 <pid>``).

Field diagnosis for the "cancelled run wedges mid-unwind" class of bug
(Discord: "death spiral of 2 asyncs waiting for the other to finish").
``faulthandler`` alone is useless there — the event-loop thread is parked
in ``select()`` and every interesting frame lives in a *suspended asyncio
task*, which faulthandler cannot see. This module dumps BOTH:

- OS-thread stacks via ``faulthandler.dump_traceback`` (key listener,
  renderer, shell readers, ...); and
- every asyncio task's coroutine stack via ``Task.print_stack`` (the REPL
  coroutine stuck on ``await agent_task``, the agent task stuck in its
  cancel-scope teardown — the actual smoking gun).

Dumps are written to ``~/.code_puppy/stackdumps/`` (never the terminal:
the bottom-bar TUI owns it, and a wedged app may not repaint anyway) with
a one-line breadcrumb on stderr. POSIX only — Windows has no SIGUSR2;
``install_stack_dump_handler`` degrades to a no-op there.
"""

from __future__ import annotations

import asyncio
import faulthandler
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional, TextIO

logger = logging.getLogger(__name__)

DUMP_DIR = Path.home() / ".code_puppy" / "stackdumps"

#: Frames per task stack. Wedges live near the leaf; unbounded dumps of
#: deep pydantic-ai graphs just bury the signal.
TASK_STACK_LIMIT = 40

_captured_loop: Optional[asyncio.AbstractEventLoop] = None


def dump_stacks(file: TextIO, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """Write thread stacks + asyncio task stacks to ``file``.

    Never raises: each section is best-effort so a half-broken process
    can still confess as much as it knows.
    """
    print(f"=== code-puppy stack dump (pid {os.getpid()}) ===", file=file)
    print("--- OS threads (faulthandler) ---", file=file)
    try:
        file.flush()
        faulthandler.dump_traceback(file=file, all_threads=True)
    except Exception:
        logger.debug("faulthandler dump failed", exc_info=True)
        print("<faulthandler dump failed>", file=file)

    loop = loop or _captured_loop
    if loop is None:
        print("--- asyncio tasks: no loop captured ---", file=file)
        return
    try:
        tasks = asyncio.all_tasks(loop)
    except Exception:
        logger.debug("asyncio.all_tasks failed", exc_info=True)
        print("--- asyncio tasks: enumeration failed ---", file=file)
        return
    print(f"--- asyncio tasks: {len(tasks)} ---", file=file)
    for task in tasks:
        print(f"\nTask: {task!r}", file=file)
        try:
            task.print_stack(limit=TASK_STACK_LIMIT, file=file)
        except Exception:
            logger.debug("task.print_stack failed", exc_info=True)
            print("<task stack unavailable>", file=file)


def write_stack_dump(
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> Optional[Path]:
    """Dump to a timestamped file under ``DUMP_DIR``; return its path.

    Returns ``None`` (and stays silent beyond a debug log) if even the
    file can't be created — diagnostics must never hurt the patient.
    """
    try:
        DUMP_DIR.mkdir(parents=True, exist_ok=True)
        path = DUMP_DIR / f"stackdump-{os.getpid()}-{int(time.time())}.txt"
        with open(path, "w", encoding="utf-8") as f:
            dump_stacks(f, loop=loop)
        # stderr, not the message bus: a wedged loop may never render a
        # bus message, and stderr survives a hung TUI.
        print(f"[code-puppy] stack dump written to {path}", file=sys.stderr)
        return path
    except Exception:
        logger.debug("stack dump failed", exc_info=True)
        return None


def install_stack_dump_handler(
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> bool:
    """Register the SIGUSR2 stack-dump handler. Returns True if installed.

    Safe to call more than once (last loop reference wins). No-op on
    platforms without SIGUSR2 (Windows) and off the main thread, where
    ``signal.signal`` raises.
    """
    global _captured_loop
    if not hasattr(signal, "SIGUSR2"):
        return False
    if loop is not None:
        _captured_loop = loop

    def _handler(signum, frame) -> None:
        write_stack_dump()

    try:
        signal.signal(signal.SIGUSR2, _handler)
    except (ValueError, OSError):
        logger.debug("SIGUSR2 handler install failed", exc_info=True)
        return False
    return True
