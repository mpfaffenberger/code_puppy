"""Wire the DBOS durable-execution plugin into core via callback hooks."""

from __future__ import annotations

import logging
import sys

from code_puppy.callbacks import register_callback

from .cancel import cancel_workflow
from .commands import dbos_command_help, handle_dbos_command
from .config import is_enabled
from .lifecycle import on_shutdown, on_startup
from .runtime import dbos_run_context, skip_fallback_render
from .wrapper import wrap_with_dbos_agent

logger = logging.getLogger(__name__)

# DIAG: raw stderr print so we can see if the plugin is even loaded in CI.
# Bypasses message bus / logging — guaranteed to show in pexpect logs.
print(
    f"[dbos_durable_exec] module loaded, is_enabled()={is_enabled()}",
    file=sys.stderr,
    flush=True,
)


# Slash command is always available so users can /dbos on even when the
# package isn't installed yet (we tell them to install + restart).
register_callback("custom_command", handle_dbos_command)
register_callback("custom_command_help", dbos_command_help)


if is_enabled():
    try:
        import dbos  # noqa: F401  -- early import check
    except ImportError:
        print(
            "[dbos_durable_exec] dbos package not importable; lifecycle SKIPPED",
            file=sys.stderr,
            flush=True,
        )
        logger.debug(
            "DBOS plugin enabled but `dbos` package not installed; "
            "durable-exec hooks not registered."
        )
    else:
        print(
            "[dbos_durable_exec] registering startup/shutdown/etc hooks",
            file=sys.stderr,
            flush=True,
        )
        register_callback("startup", on_startup)
        register_callback("shutdown", on_shutdown)
        register_callback("wrap_pydantic_agent", wrap_with_dbos_agent)
        register_callback("agent_run_context", dbos_run_context)
        register_callback("agent_run_cancel", cancel_workflow)
        register_callback("should_skip_fallback_render", skip_fallback_render)
else:
    print(
        "[dbos_durable_exec] is_enabled()==False; lifecycle SKIPPED",
        file=sys.stderr,
        flush=True,
    )
