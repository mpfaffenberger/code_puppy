"""``--no-tools`` CLI flag (issue #182).

Lets wrappers run Code Puppy as a plain text-in/text-out subprocess:
no tools registered on any agent, no MCP toolsets attached, and no tool
schemas eating tokens in the request.

Implementation is deliberately tiny: the flag just sets the
``CODE_PUPPY_NO_TOOLS`` env var, and the core tool registry
(``code_puppy.tools.tools_disabled``) honors it. Wrappers that can't pass
CLI flags can set the env var directly — same effect, zero magic.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from code_puppy.callbacks import register_callback


def _register_cli_args(parser: Any) -> None:
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help=(
            "Disable all agent tools and MCP servers for this run "
            "(pure text-in/text-out; equivalent to CODE_PUPPY_NO_TOOLS=1)"
        ),
    )


def _handle_cli_args(args: Any) -> Optional[dict]:
    if getattr(args, "no_tools", False):
        from code_puppy.tools import NO_TOOLS_ENV_VAR

        os.environ[NO_TOOLS_ENV_VAR] = "1"
    # Never short-circuit startup — this flag only flips the kill-switch.
    return None


register_callback("register_cli_args", _register_cli_args)
register_callback("handle_cli_args", _handle_cli_args)
