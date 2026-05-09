"""Builtin plugin trust command handler.

Implements /plugin list, /plugin trust <name>, /plugin revoke <name>,
and /plugin help.
"""

from __future__ import annotations

import logging
from typing import Optional

from code_puppy.callbacks import register_callback
from code_puppy.plugins import (
    _PLUGINS_LOADED,
    compute_plugin_hash,
    get_user_plugins_dir,
    is_plugin_trusted,
    record_plugin_trust,
    revoke_plugin_trust,
)

logger = logging.getLogger(__name__)


def _plugin_command_help() -> list[tuple[str, str]]:
    """Return help entries for plugin trust commands."""
    return [
        ("plugin list", "List discovered user plugins with trust status"),
        ("plugin trust <name>", "Trust a user plugin by content hash"),
        ("plugin revoke <name>", "Revoke trust for a user plugin"),
        ("plugin help", "Show plugin trust command help"),
    ]


def _handle_plugin_command(command: str, name: str) -> Optional[str]:
    """Handle /plugin subcommands."""
    if name != "plugin":
        return None

    parts = command.strip().split()
    if len(parts) < 2:
        return _plugin_help_text()

    sub = parts[1].lower()

    if sub == "help":
        return _plugin_help_text()

    if sub in ("list", "plugins"):
        return _plugin_list()

    if sub == "trust":
        if len(parts) < 3:
            return "Usage: /plugin trust <plugin_name>"
        return _plugin_trust(parts[2])

    if sub == "revoke":
        if len(parts) < 3:
            return "Usage: /plugin revoke <plugin_name>"
        return _plugin_revoke(parts[2])

    return f"Unknown /plugin subcommand: {sub}. Usage: /plugin trust|revoke|list|help"


def _plugin_help_text() -> str:
    return (
        "Plugin trust commands:\n"
        "  /plugin list          — List discovered user plugins with hash & trust status\n"
        "  /plugin trust <name>  — Record trust for a user plugin\n"
        "  /plugin revoke <name> — Revoke trust for a user plugin\n"
        "  /plugin help          — Show this help"
    )


def _plugin_list() -> str:
    """Summarise discovered user plugins with hash and trust status."""
    user_dir = get_user_plugins_dir()
    if not user_dir.exists():
        return f"No user plugins directory found at {user_dir}"

    entries: list[str] = []
    for item in sorted(user_dir.iterdir()):
        if not item.is_dir() or item.name.startswith(".") or item.name.startswith("_"):
            continue

        has_callbacks = (item / "register_callbacks.py").exists()
        has_init = (item / "__init__.py").exists()
        if not has_callbacks and not has_init:
            continue

        try:
            content_hash = compute_plugin_hash(item)
        except OSError as exc:
            logger.warning("Failed to hash plugin %s: %s", item.name, exc)
            continue

        trusted = is_plugin_trusted(item.name, content_hash)
        status = "trusted" if trusted else "untrusted"
        entries.append(f"  {item.name:20}  {status:10}  {content_hash[:12]}…  {item}")

    if not entries:
        return f"No user plugins found in {user_dir}"

    header = f"{'Name':20}  {'Status':10}  {'Hash':14}  Path"
    return "User plugins:\n" + header + "\n" + "\n".join(entries)


def _plugin_trust(plugin_name: str) -> str:
    """Compute current hash and record trust for a user plugin."""
    user_dir = get_user_plugins_dir()
    plugin_dir = user_dir / plugin_name

    if not plugin_dir.exists() or not plugin_dir.is_dir():
        return f"Plugin '{plugin_name}' not found in {user_dir}"

    if (
        not (plugin_dir / "register_callbacks.py").exists()
        and not (plugin_dir / "__init__.py").exists()
    ):
        return f"Plugin '{plugin_name}' has no register_callbacks.py or __init__.py"

    try:
        content_hash = compute_plugin_hash(plugin_dir)
    except OSError as exc:
        logger.warning("Failed to hash plugin %s: %s", plugin_name, exc)
        return f"Failed to compute hash for plugin '{plugin_name}'"

    record_plugin_trust(plugin_name, content_hash, str(plugin_dir))

    msg = f"Trust recorded for plugin '{plugin_name}' (hash: {content_hash[:12]}…)."
    if _PLUGINS_LOADED:
        msg += " Restart code-puppy to load newly trusted plugins."
    return msg


def _plugin_revoke(plugin_name: str) -> str:
    """Revoke trust for a user plugin."""
    revoke_plugin_trust(plugin_name)
    return f"Trust revoked for plugin '{plugin_name}'. Restart code-puppy to unload."


register_callback("custom_command", _handle_plugin_command)
register_callback("custom_command_help", _plugin_command_help)
