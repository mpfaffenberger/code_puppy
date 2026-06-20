"""Register the opt-in /share command."""

from __future__ import annotations

import shlex
from pathlib import Path

from code_puppy.callbacks import register_callback


def _share(command: str, name: str):
    if name != "share":
        return None
    from code_puppy.agents import get_current_agent
    from code_puppy.config import STATE_DIR
    from code_puppy.sharing import export_session_html

    try:
        parts = shlex.split(command)
        if len(parts) > 2 and parts[1] == "--upload":
            from code_puppy.sharing import upload_session_html

            return "Redacted session share: " + upload_session_html(
                get_current_agent().get_message_history(), parts[2]
            )
        destination = (
            Path(parts[1])
            if len(parts) > 1
            else Path(STATE_DIR) / "shares" / "mist-session.html"
        )
        path = export_session_html(
            get_current_agent().get_message_history(), destination
        )
        return f"Redacted session export: {path.as_uri()}"
    except Exception as exc:
        return f"Unable to export session: {exc}"


def _help() -> list[tuple[str, str]]:
    return [
        ("/share [file.html]", "Create a local redacted read-only session export"),
        ("/share --upload URL", "Upload a redacted export to your own HTTPS endpoint"),
    ]


register_callback("custom_command", _share)
register_callback("custom_command_help", _help)
