"""``/mcp trust`` — accept, inspect, or revoke a project-level MCP config.

Project MCP configs (``<CWD>/.code_puppy/mcp_servers.json``) can define
``stdio`` servers that run arbitrary commands, so they are ignored until the
user explicitly trusts them. This command drives that trust ceremony:

* ``/mcp trust``            → preview the project config + servers, show status.
* ``/mcp trust accept``     → record trust and re-sync the registry.
* ``/mcp trust revoke``     → drop trust for this project.
* ``/mcp trust status``     → just print the current trust status.

Trust is content-hashed and stored user-side; see
:mod:`code_puppy.mcp_.project_config`.
"""

import logging
from typing import List, Optional

from rich.text import Text

from code_puppy.mcp_.project_config import (
    CHANGED,
    TRUSTED,
    UNTRUSTED,
    get_project_mcp_servers_file,
    get_trust_status,
    revoke_project_mcp,
    trust_project_mcp,
)
from code_puppy.messaging import emit_error, emit_info

from .base import MCPCommandBase

logger = logging.getLogger(__name__)


class TrustCommand(MCPCommandBase):
    """Handle ``/mcp trust [accept|revoke|status]``."""

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        if group_id is None:
            group_id = self.generate_group_id()

        try:
            import os

            project_root = os.getcwd()
            config_file = get_project_mcp_servers_file()

            if config_file is None:
                emit_info(
                    Text.from_markup(
                        "[yellow]No project MCP config found.[/yellow] Create "
                        "[cyan].code_puppy/mcp_servers.json[/cyan] in this repo "
                        "to define project-scoped MCP servers."
                    ),
                    message_group=group_id,
                )
                return

            action = args[0].lower() if args else "preview"

            if action == "revoke":
                self._revoke(group_id)
            elif action == "accept":
                self._accept(config_file, group_id)
            elif action in ("status", "preview", ""):
                self._preview(project_root, config_file, group_id)
            else:
                emit_info(
                    Text.from_markup(
                        f"[yellow]Unknown '/mcp trust' action: {action}[/yellow]. "
                        "Use [cyan]accept[/cyan], [cyan]revoke[/cyan], or "
                        "[cyan]status[/cyan]."
                    ),
                    message_group=group_id,
                )
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Error handling /mcp trust: {e}")
            emit_error(f"Error handling /mcp trust: {e}", message_group=group_id)

    # ---- actions ------------------------------------------------------------

    def _preview(self, project_root: str, config_file, group_id: str) -> None:
        """Show the project config, its servers, and the trust status."""
        from pathlib import Path

        status = get_trust_status(Path(project_root), config_file)
        lines = [
            Text.from_markup(
                f"[bold]Project MCP config:[/bold] [cyan]{config_file}[/cyan]"
            ),
            Text.from_markup(f"[bold]Trust status:[/bold] {_status_markup(status)}"),
            Text(""),
        ]

        servers = self._safe_load_servers(config_file)
        if servers:
            lines.append(Text.from_markup("[bold]Declared servers:[/bold]"))
            for name, conf in servers.items():
                lines.append(_describe_server(name, conf))
        else:
            lines.append(
                Text.from_markup("[dim](no servers declared, or file unreadable)[/dim]")
            )
        lines.append(Text(""))

        if status == TRUSTED:
            lines.append(
                Text.from_markup(
                    "[green]\u2713 Trusted.[/green] These servers are loaded. "
                    "Run [cyan]/mcp trust revoke[/cyan] to disable them."
                )
            )
        else:
            verb = (
                "changed since you trusted it" if status == CHANGED else "not trusted"
            )
            lines.append(
                Text.from_markup(
                    f"[yellow]\u26a0 This config is {verb}, so its servers are "
                    "NOT loaded.[/yellow] These servers can run arbitrary "
                    "commands. If you trust this repo, run "
                    "[cyan]/mcp trust accept[/cyan]."
                )
            )
        _emit_lines(lines, group_id)

    def _accept(self, config_file, group_id: str) -> None:
        if trust_project_mcp():
            # Reflect the new trust immediately by re-syncing the registry.
            try:
                self.manager.sync_from_config()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Post-trust registry sync failed: %s", exc)
            emit_info(
                Text.from_markup(
                    f"[green]\u2713 Trusted[/green] [cyan]{config_file}[/cyan]. "
                    "Its servers are now available. Use [cyan]/mcp[/cyan] to see "
                    "them and [cyan]/mcp start <name>[/cyan] to run one."
                ),
                message_group=group_id,
            )
        else:
            emit_error(
                f"Could not trust project MCP config {config_file} "
                "(unreadable file or trust store write failure).",
                message_group=group_id,
            )

    def _revoke(self, group_id: str) -> None:
        if revoke_project_mcp():
            emit_info(
                Text.from_markup(
                    "[green]\u2713 Revoked[/green] trust for this project's MCP "
                    "config. Its servers will no longer load. Restart or re-sync "
                    "to drop already-registered ones."
                ),
                message_group=group_id,
            )
        else:
            emit_info(
                Text.from_markup(
                    "[dim]This project's MCP config wasn't trusted. "
                    "Nothing to revoke.[/dim]"
                ),
                message_group=group_id,
            )

    # ---- helpers ------------------------------------------------------------

    @staticmethod
    def _safe_load_servers(config_file) -> dict:
        """Parse the project config for display only; never raise."""
        try:
            from code_puppy.config import _parse_mcp_servers_mapping

            return _parse_mcp_servers_mapping(config_file.read_text(encoding="utf-8"))
        except Exception:
            return {}


def _status_markup(status: str) -> str:
    return {
        TRUSTED: "[green]trusted[/green]",
        CHANGED: "[yellow]changed (re-accept needed)[/yellow]",
        UNTRUSTED: "[yellow]untrusted[/yellow]",
    }.get(status, status)


def _describe_server(name: str, conf) -> Text:
    """One-line description of a declared server, flagging arbitrary-command types."""
    if not isinstance(conf, dict):
        # Shorthand form: name -> url string.
        return Text.from_markup(f"  \u2022 [cyan]{name}[/cyan]  [dim]{conf}[/dim]")
    stype = conf.get("type", "sse")
    if stype == "stdio" and conf.get("command"):
        cmd = conf.get("command")
        detail = f"[red]stdio[/red] \u2192 runs: [dim]{cmd}[/dim]"
    elif conf.get("url"):
        detail = f"[dim]{stype} \u2192 {conf.get('url')}[/dim]"
    else:
        detail = f"[dim]{stype}[/dim]"
    return Text.from_markup(f"  \u2022 [cyan]{name}[/cyan]  {detail}")


def _emit_lines(lines: List[Text], group_id: str) -> None:
    final = Text()
    for i, line in enumerate(lines):
        if i > 0:
            final.append("\n")
        final.append_text(line)
    emit_info(final, message_group=group_id)
