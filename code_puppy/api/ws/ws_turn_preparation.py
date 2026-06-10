"""Helpers for preparing one WebSocket chat turn before agent execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from code_puppy.api.ws.attachments import build_file_context_and_attachments

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PreparedTurnInput:
    """Materialized input for one agent turn."""

    message_to_send: str
    run_kwargs: dict[str, Any]
    attachment_metadata: list[dict[str, Any]]
    last_context_sent_directory: str


def _maybe_inject_working_directory(
    *,
    agent: Any,
    session_working_directory: str,
    last_context_sent_directory: str,
) -> str:
    """Append a working-directory system message when the visible CWD changed."""
    if (
        not session_working_directory
        or session_working_directory == last_context_sent_directory
    ):
        return last_context_sent_directory

    from pydantic_ai.messages import ModelRequest, SystemPromptPart

    wd_system_msg = ModelRequest(
        parts=[
            SystemPromptPart(
                content=(
                    "The user's current working directory is updated to"
                    f" {session_working_directory}"
                )
            )
        ]
    )
    agent.append_to_message_history(wd_system_msg)
    logger.debug(
        "Injected working directory system message: %s",
        session_working_directory,
    )
    return session_working_directory


def _collect_attachment_metadata(msg: dict[str, Any]) -> list[dict[str, Any]]:
    """Build attachment metadata payloads for the UI without changing semantics."""
    attachment_metadata: list[dict[str, Any]] = []

    if not msg.get("attachments"):
        return attachment_metadata

    for raw_path in msg.get("attachments", []):
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue

        try:
            file_path = Path(raw_path)
            if file_path.exists():
                attachment_metadata.append(
                    {
                        "name": file_path.name,
                        "path": str(file_path.absolute()),
                        "sizeBytes": file_path.stat().st_size,
                    }
                )
        except Exception as e:
            logger.warning(
                "Error building attachment metadata for '%s': %s",
                raw_path,
                e,
            )

    return attachment_metadata


def prepare_turn_input(
    *,
    agent: Any,
    user_message: str,
    msg: dict[str, Any],
    session_working_directory: str,
    last_context_sent_directory: str,
) -> PreparedTurnInput:
    """Prepare the exact message payload and metadata for one agent turn."""
    last_context_sent_directory = _maybe_inject_working_directory(
        agent=agent,
        session_working_directory=session_working_directory,
        last_context_sent_directory=last_context_sent_directory,
    )

    message_to_send = user_message
    logger.debug("Calling run_with_mcp with message: %s...", message_to_send[:100])

    file_context, binary_attachments = build_file_context_and_attachments(msg)
    attachment_metadata = _collect_attachment_metadata(msg)

    if file_context:
        message_to_send = file_context + "\n\n" + message_to_send
        logger.debug("Added file context (%d chars)", len(file_context))

    run_kwargs: dict[str, Any] = {}
    if binary_attachments:
        run_kwargs["attachments"] = binary_attachments
        logger.debug(
            "Including %d binary attachment(s)",
            len(binary_attachments),
        )

    return PreparedTurnInput(
        message_to_send=message_to_send,
        run_kwargs=run_kwargs,
        attachment_metadata=attachment_metadata,
        last_context_sent_directory=last_context_sent_directory,
    )
