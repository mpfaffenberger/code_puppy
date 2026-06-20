"""
MCP Silence/Unsilence Warning Commands.

Toggles persistent silencing of the "MCP server registered in mcp_servers.json
but not bound to agent" warning emitted by
:func:`code_puppy.mcp_.manager._warn_unbound_servers`.

State is persisted in ``mist.cfg`` under ``mcp_unbound_warning_silenced`` so
the silence survives restarts.
"""

import logging
from typing import List, Optional

from rich.text import Text

from code_puppy.config import (
    get_mcp_unbound_warning_silenced,
    set_mcp_unbound_warning_silenced,
)
from code_puppy.messaging import emit_error, emit_info

from .base import MCPCommandBase

logger = logging.getLogger(__name__)


class _ToggleSilenceCommand(MCPCommandBase):
    """Shared implementation for silence-warning / unsilence-warning.

    Single source of truth so we don't duplicate the read-current-state /
    write-new-state / emit-feedback dance twice. Subclasses just declare
    the target state.
    """

    #: Target value for ``mcp_unbound_warning_silenced`` after this runs.
    target_silenced: bool = True

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        if group_id is None:
            group_id = self.generate_group_id()

        try:
            current = get_mcp_unbound_warning_silenced()
            if current == self.target_silenced:
                state_word = "silenced" if current else "active"
                emit_info(
                    Text.from_markup(
                        f"[dim]Unbound-MCP-server warning is already "
                        f"{state_word}. Nothing to do.[/dim]"
                    ),
                    message_group=group_id,
                )
                return

            set_mcp_unbound_warning_silenced(self.target_silenced)

            if self.target_silenced:
                emit_info(
                    Text.from_markup(
                        "[green]\u2713[/green] Unbound-MCP-server warning "
                        "[bold]silenced forever[/bold] (persisted in "
                        "mist.cfg). Run [cyan]/mcp unsilence-warning[/cyan] "
                        "to restore it."
                    ),
                    message_group=group_id,
                )
            else:
                emit_info(
                    Text.from_markup(
                        "[green]\u2713[/green] Unbound-MCP-server warning "
                        "[bold]restored[/bold]. You'll see it again the next "
                        "time an agent loads with unbound servers."
                    ),
                    message_group=group_id,
                )
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Error toggling MCP unbound-warning silence: {e}")
            emit_error(f"Error updating silence setting: {e}", message_group=group_id)


class SilenceWarningCommand(_ToggleSilenceCommand):
    """``/mcp silence-warning`` \u2014 silence the unbound-server warning forever."""

    target_silenced = True


class UnsilenceWarningCommand(_ToggleSilenceCommand):
    """``/mcp unsilence-warning`` \u2014 restore the unbound-server warning."""

    target_silenced = False
