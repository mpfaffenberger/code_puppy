"""Wire the DBOS durable-execution plugin into core via callback hooks."""

from __future__ import annotations

import logging

from code_puppy.callbacks import register_callback

from .cancel import cancel_workflow
from .commands import dbos_command_help, handle_dbos_command
from .config import is_enabled
from .lifecycle import on_shutdown, on_startup
from .runtime import dbos_run_context, skip_fallback_render
from .wrapper import wrap_with_dbos_agent

logger = logging.getLogger(__name__)


# Slash command is always available so users can /dbos on even when the
# package isn't installed yet (we tell them to install + restart).
register_callback("custom_command", handle_dbos_command)
register_callback("custom_command_help", dbos_command_help)


if is_enabled():
    try:
        import dbos  # noqa: F401  -- early import check
    except ImportError:
        # Use logger.info (not debug) so it surfaces by default — silently
        # skipping a feature the user enabled is bad UX. Install with
        # `pip install code-puppy[durable]` to fix.
        logger.info(
            "DBOS plugin enabled but `dbos` package not installed; "
            "durable-exec hooks not registered. "
            "Install with: pip install 'code-puppy[durable]'"
        )
    else:
        register_callback("startup", on_startup)
        register_callback("shutdown", on_shutdown)
        register_callback("wrap_pydantic_agent", wrap_with_dbos_agent)
        register_callback("agent_run_context", dbos_run_context)
        register_callback("agent_run_cancel", cancel_workflow)
        register_callback("should_skip_fallback_render", skip_fallback_render)
