"""Deprecated compatibility shim -- the classic prompt path is gone.

The classic prompt_toolkit input path was retired when every TUI moved
to termflow; the survivors live in :mod:`code_puppy.command_line.completers`.
This module re-exports the names published plugins still monkey-patch
(statusline, prompt_newline) so they keep working until they migrate.
It imports nothing from prompt_toolkit.

Do not add new imports of this module -- use ``completers`` directly.
"""

from code_puppy.command_line.completers import (  # noqa: F401
    PROMPT_STYLES,
    AgentCompleter,
    CDCompleter,
    SetCompleter,
    SlashCompleter,
    get_prompt_with_active_model,
)

__all__ = [
    "PROMPT_STYLES",
    "AgentCompleter",
    "CDCompleter",
    "SetCompleter",
    "SlashCompleter",
    "get_prompt_with_active_model",
]
