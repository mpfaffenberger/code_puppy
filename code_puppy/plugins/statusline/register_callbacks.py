"""Wire up the statusline plugin."""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

from code_puppy.callbacks import register_callback

from .prompt_patch import install_prompt_patch
from .statusline_command import handle_statusline_command, statusline_command_help

logger = logging.getLogger(__name__)


def _on_startup() -> None:
    try:
        install_prompt_patch()
    except Exception:
        logger.debug("statusline: failed to install prompt patch", exc_info=True)


def _custom_command_help() -> List[Tuple[str, str]]:
    return statusline_command_help()


def _handle_custom_command(command: str, name: str) -> Optional[Any]:
    try:
        return handle_statusline_command(command, name)
    except Exception:
        logger.debug("statusline: command handler failed", exc_info=True)
        return None


register_callback("startup", _on_startup)
register_callback("custom_command_help", _custom_command_help)
register_callback("custom_command", _handle_custom_command)

# Install immediately too, in case startup already fired before this plugin
# loaded (plugin load order is not guaranteed relative to the startup hook).
_on_startup()

logger.debug("statusline plugin registered")
