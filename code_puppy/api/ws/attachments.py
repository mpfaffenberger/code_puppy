"""File attachment processing utilities for WebSocket chat.

Handles converting file attachment paths into either binary content
(for images/PDFs) or text context (for code/text files).
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Supported binary types (Claude's native attachments)
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".bmp",
    ".tiff",
}


def build_file_context_and_attachments(msg: dict):
    """Convert attachment paths into either binary attachments OR text context.

    For images/PDFs: Send as BinaryContent (Claude's native attachment support)
    For text files: Read and prepend to message so Code Puppy can analyze them

    Returns: (text_context, binary_attachments)
        text_context: String to prepend to the message, or empty string
        binary_attachments: List of BinaryContent for images/PDFs
    """
    attachment_paths = msg.get("attachments") or []

    if not attachment_paths:
        return "", []

    text_context_parts = []
    binary_attachments = []

    for raw_path in attachment_paths:
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue

        try:
            file_path = Path(raw_path)

            if not file_path.exists():
                logger.warning("Attachment file not found: %s", raw_path)
                continue

            ext = file_path.suffix.lower()

            if ext in BINARY_EXTENSIONS:
                try:
                    from pydantic_ai import BinaryContent

                    from code_puppy.command_line.attachments import (
                        _determine_media_type,
                        _load_binary,
                    )

                    data = _load_binary(file_path)
                    media_type = _determine_media_type(file_path)
                    binary_attachments.append(
                        BinaryContent(data=data, media_type=media_type)
                    )
                    logger.debug("Loaded binary attachment: %s", file_path.name)
                except Exception as e:
                    logger.warning(
                        f"Failed to load binary attachment '{raw_path}': {e}"
                    )
            else:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    text_context_parts.append(
                        f"\n\n--- File: {file_path.name} ({raw_path}) ---\n"
                        f"{content}\n"
                        f"--- End of {file_path.name} ---\n"
                    )
                    logger.debug(
                        f"Loaded text file: {file_path.name} ({len(content)} chars)"
                    )
                except Exception as e:
                    logger.warning("Failed to read text file '%s': %s", raw_path, e)

        except Exception as e:
            logger.warning("Error processing attachment '%s': %s", raw_path, e)

    text_context = "".join(text_context_parts)
    return text_context, binary_attachments
