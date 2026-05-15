"""Slash command: /dbos on|off|status to toggle the durable-execution plugin."""

from __future__ import annotations

from .config import is_enabled, set_enabled


def handle_dbos_command(command: str, name: str):
    if name != "dbos":
        return None
    parts = command.strip().split()
    if len(parts) < 2:
        status = "ON" if is_enabled() else "OFF"
        return (
            f"DBOS durable execution is currently {status}. Usage: /dbos on|off|status"
        )
    sub = parts[1].lower()
    if sub == "status":
        status = "ON" if is_enabled() else "OFF"
        return f"DBOS durable execution: {status}"
    if sub == "on":
        set_enabled(True)
        return "DBOS durable execution enabled. Restart code-puppy to apply."
    if sub == "off":
        set_enabled(False)
        return "DBOS durable execution disabled. Restart code-puppy to apply."
    return f"Unknown /dbos subcommand: {sub}. Usage: /dbos on|off|status"


def dbos_command_help():
    return [("dbos", "Toggle DBOS durable execution: /dbos on|off|status")]
