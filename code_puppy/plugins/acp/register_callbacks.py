"""Plugin registration: the ``--acp`` entry point.

This is the only place the ACP plugin touches Code Puppy's CLI. It:
  1. contributes a ``--acp`` flag via the ``register_cli_args`` hook, and
  2. in ``handle_cli_args``, when ``--acp`` is present, boots the ACP server
     over stdio and returns the short-circuit sentinel so the normal
     interactive TUI never starts.

Per the contributing guide, all of this rides on existing hooks — no edits to
``code_puppy/command_line`` or the core CLI runner.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)


def _register_cli_args(parser: Any) -> None:
    """Add the ``--acp`` flag to Code Puppy's argument parser."""
    parser.add_argument(
        "--acp",
        action="store_true",
        help="Run as a native agent over the Agent Client Protocol (ACP), speaking JSON-RPC over stdio.",
    )


def _handle_cli_args(args: Any) -> Optional[Dict[str, Any]]:
    """Boot the ACP server when ``--acp`` is set; otherwise stand down.

    Returns the ``{"handled": True, "exit_code": ...}`` sentinel so the CLI
    runner exits after the ACP session ends instead of falling through to the
    interactive TUI. Any other invocation returns ``None`` (not ours).

    This hook is invoked *synchronously from within* Code Puppy's already-
    running ``asyncio.run(main())`` loop, so we cannot start a nested loop
    here. Instead we run the server on its own event loop in a dedicated
    thread and block until it finishes — which keeps ``main()`` parked so the
    TUI never starts.
    """
    if not getattr(args, "acp", False):
        return None

    import threading

    box: Dict[str, int] = {"exit_code": 0}

    def _run() -> None:
        try:
            box["exit_code"] = asyncio.run(_serve())
        except Exception:  # noqa: BLE001 - never leak a traceback onto stdout
            logger.exception("ACP server crashed")
            box["exit_code"] = 1

    thread = threading.Thread(target=_run, name="acp-server")
    thread.start()
    thread.join()
    return {"handled": True, "exit_code": box["exit_code"]}


async def _serve() -> int:
    """Bind stdio via the ACP SDK and run one connection to completion.

    Before serving we protect stdout — the JSON-RPC channel — by pointing
    Code Puppy's streaming console and the root logger at stderr. In ACP mode
    the interactive path that normally calls ``set_streaming_console`` is
    short-circuited, so without this the streaming console would fall back to a
    plain ``Console()`` on stdout and corrupt the protocol.

    ``acp.run_agent`` owns the wire (stdio binding, JSON-RPC framing, param
    parsing); we hand it a ``CodePuppyAgent`` and tear down the approval + I/O
    backends afterwards so the process leaves no global seams set.
    """
    import sys

    from acp import run_agent
    from rich.console import Console

    from code_puppy.agents.event_stream_handler import set_streaming_console
    from code_puppy.plugins.acp import io_delegation, permissions, state
    from code_puppy.plugins.acp.agent import CodePuppyAgent

    # Route all incidental console output to stderr; stdout is JSON-RPC only.
    set_streaming_console(Console(file=sys.stderr))
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

    agent = CodePuppyAgent()
    try:
        await run_agent(agent)
    finally:
        agent.shutdown()
        permissions.uninstall()
        io_delegation.uninstall()
        state.set_connection(None, None)
    return 0


def register() -> None:
    """Register the ACP CLI hooks."""
    register_callback("register_cli_args", _register_cli_args)
    register_callback("handle_cli_args", _handle_cli_args)
    logger.debug("ACP plugin callbacks registered")


register()
