"""Helpers for parsing file attachments from interactive prompts."""

from __future__ import annotations

import mimetypes
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from pydantic_ai import BinaryContent, DocumentUrl, ImageUrl

SUPPORTED_INLINE_SCHEMES = {"http", "https"}

# Allow common extensions people drag in the terminal.
DEFAULT_ACCEPTED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".tiff",
}
DEFAULT_ACCEPTED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
}


@dataclass
class PromptAttachment:
    """Represents a binary attachment parsed from the input prompt."""

    placeholder: str
    content: BinaryContent


@dataclass
class PromptLinkAttachment:
    """Represents a URL attachment supported by pydantic-ai."""

    placeholder: str
    url_part: ImageUrl | DocumentUrl


@dataclass
class ProcessedPrompt:
    """Container for parsed input prompt and attachments."""

    prompt: str
    attachments: List[PromptAttachment]
    link_attachments: List[PromptLinkAttachment]
    warnings: List[str]


class AttachmentParsingError(RuntimeError):
    """Raised when we fail to load a user-provided attachment."""


def _is_probable_path(token: str) -> bool:
    """Heuristically determine whether a token is a local filesystem path."""

    if not token:
        return False
    if token.startswith("#"):
        return False
    # Windows drive letters or Unix absolute/relative paths
    if token.startswith(("/", "~", "./", "../")):
        return True
    if len(token) >= 2 and token[1] == ":":
        return True
    # Things like `path/to/file.png`
    return os.sep in token or "\"" in token


def _normalise_path(token: str) -> Path:
    """Expand user shortcuts and resolve relative components without touching fs."""

    expanded = os.path.expanduser(token)
    try:
        # This will not resolve against symlinks because we do not call resolve()
        return Path(expanded).absolute()
    except Exception as exc:
        raise AttachmentParsingError(f"Invalid path '{token}': {exc}") from exc


def _determine_media_type(path: Path) -> str:
    """Best-effort media type detection."""

    mime, _ = mimetypes.guess_type(path.name)
    if mime:
        return mime
    # Default fallbacks keep LLMs informed.
    if path.suffix.lower() in DEFAULT_ACCEPTED_IMAGE_EXTENSIONS:
        return "image/png"
    if path.suffix.lower() in DEFAULT_ACCEPTED_DOCUMENT_EXTENSIONS:
        return "application/octet-stream"
    return "application/octet-stream"


def _load_binary(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise AttachmentParsingError(f"Attachment not found: {path}") from exc
    except PermissionError as exc:
        raise AttachmentParsingError(f"Cannot read attachment (permission denied): {path}") from exc
    except OSError as exc:
        raise AttachmentParsingError(f"Failed to read attachment {path}: {exc}") from exc


def _tokenise(prompt: str) -> Iterable[str]:
    """Split the prompt preserving quoted segments using shell-like semantics."""

    if not prompt:
        return []
    try:
        return shlex.split(prompt)
    except ValueError:
        # Fallback naive split when shlex fails (e.g. unmatched quotes)
        return prompt.split()


def _is_supported_extension(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in DEFAULT_ACCEPTED_IMAGE_EXTENSIONS | DEFAULT_ACCEPTED_DOCUMENT_EXTENSIONS


def _parse_link(token: str) -> PromptLinkAttachment | None:
    if "://" not in token:
        return None
    scheme = token.split(":", 1)[0].lower()
    if scheme not in SUPPORTED_INLINE_SCHEMES:
        return None
    if token.lower().endswith(".pdf"):
        return PromptLinkAttachment(
            placeholder=token,
            url_part=DocumentUrl(url=token),
        )
    return PromptLinkAttachment(
        placeholder=token,
        url_part=ImageUrl(url=token),
    )


def parse_prompt_attachments(prompt: str) -> ProcessedPrompt:
    """Extract attachments from the prompt returning cleaned text and metadata."""

    attachments: List[PromptAttachment] = []
    link_attachments: List[PromptLinkAttachment] = []
    warnings: List[str] = []
    tokens = list(_tokenise(prompt))
    replacement_map: dict[str, str] = {}

    for token in tokens:
        if token in replacement_map:
            continue
        link_attachment = _parse_link(token)
        if link_attachment:
            link_attachments.append(link_attachment)
            replacement_map[token] = ""
            continue

        if not _is_probable_path(token):
            continue
        try:
            path = _normalise_path(token)
            if not path.exists() or not path.is_file():
                warnings.append(f"Attachment ignored (not a file): {path}")
                continue
            if not _is_supported_extension(path):
                warnings.append(f"Unsupported attachment type: {path.suffix or path.name}")
                continue
            media_type = _determine_media_type(path)
            data = _load_binary(path)
            # Keep placeholder minimal; we will strip later.
            attachments.append(
                PromptAttachment(
                    placeholder=token,
                    content=BinaryContent(data=data, media_type=media_type),
                )
            )
            replacement_map[token] = ""
        except AttachmentParsingError as exc:
            warnings.append(str(exc))
            continue

    cleaned_prompt = prompt
    for original, replacement in replacement_map.items():
        cleaned_prompt = cleaned_prompt.replace(original, replacement).strip()

    # Collapse double spaces introduced by removals
    cleaned_prompt = " ".join(cleaned_prompt.split())

    if cleaned_prompt == "" and attachments:
        cleaned_prompt = "Describe the attached files in detail."

    return ProcessedPrompt(
        prompt=cleaned_prompt,
        attachments=attachments,
        link_attachments=link_attachments,
        warnings=warnings,
    )


__all__ = [
    "ProcessedPrompt",
    "PromptAttachment",
    "PromptLinkAttachment",
    "AttachmentParsingError",
    "parse_prompt_attachments",
]
