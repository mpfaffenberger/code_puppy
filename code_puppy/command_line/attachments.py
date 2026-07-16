"""Helpers for parsing file attachments from interactive prompts."""

from __future__ import annotations

import mimetypes
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Union

from pydantic_ai import BinaryContent, DocumentUrl, ImageUrl

from code_puppy.command_line.image_utils import normalize_image_bytes

SUPPORTED_INLINE_SCHEMES = {"http", "https"}

# Maximum path length to consider - conservative limit to avoid OS errors
# Most OS have limits around 4096, but we set lower to catch garbage early
MAX_PATH_LENGTH = 1024

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
DEFAULT_ACCEPTED_DOCUMENT_EXTENSIONS = set()


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


# Matches the placeholders inserted by ClipboardManager.add_image().
CLIPBOARD_PLACEHOLDER_RE = re.compile(r"\[(?:\U0001f4cb )?clipboard image \d+\]\s*")


@dataclass
class ResolvedUserPrompt:
    """A prompt fully resolved into text + multimodal attachments.

    Produced by :func:`resolve_user_prompt` — the single source of truth for
    turning raw user input (with ``@file`` paths, URLs, and clipboard-image
    placeholders) into model-ready content. Used by both the main prompt
    path and mid-run steering injection.
    """

    text: str
    file_attachments: List[BinaryContent]
    clipboard_images: List[BinaryContent]
    link_attachments: List[Union[ImageUrl, DocumentUrl]]
    warnings: List[str]

    @property
    def attachments(self) -> List[BinaryContent]:
        """All binary attachments (files first, clipboard images after)."""
        return [*self.file_attachments, *self.clipboard_images]

    @property
    def extra_content(self) -> list:
        """Everything besides the text: binaries + URL parts."""
        return [*self.attachments, *self.link_attachments]


def resolve_user_prompt(raw_prompt: str) -> ResolvedUserPrompt:
    """Resolve a raw prompt into cleaned text and all attachment content.

    Combines :func:`parse_prompt_attachments` (file paths / URLs) with the
    pending clipboard-image queue, stripping ``[clipboard image N]``
    placeholders from the text. Drains (and clears) the clipboard queue.
    """
    processed = parse_prompt_attachments(raw_prompt)

    # Local import: clipboard pulls in PIL and pydantic-ai lazily.
    from code_puppy.command_line.clipboard import get_clipboard_manager

    clipboard_manager = get_clipboard_manager()
    clipboard_images = clipboard_manager.get_pending_images()
    clipboard_manager.clear_pending()

    text = processed.prompt
    if clipboard_images and text:
        text = CLIPBOARD_PLACEHOLDER_RE.sub("", text).strip()

    return ResolvedUserPrompt(
        text=text,
        file_attachments=[a.content for a in processed.attachments],
        clipboard_images=clipboard_images,
        link_attachments=[link.url_part for link in processed.link_attachments],
        warnings=list(processed.warnings),
    )


def resolve_steer_content(raw_text: str) -> tuple:
    """Resolve attachments for a mid-run steering message. Never raises.

    Returns ``(content, preview_text)`` where ``content`` is either the raw
    text unchanged (no attachments found — preserves whitespace exactly) or
    a multimodal list ``[text, *attachments]`` ready for ``UserPromptPart``.
    """
    try:
        resolved = resolve_user_prompt(raw_text)
        extras = resolved.extra_content
        if not extras:
            return raw_text, raw_text
        text = resolved.text or "Describe the attached content in detail."
        return [text, *extras], text
    except Exception:
        # A broken attachment must never kill a steer — fall back to text.
        return raw_text, raw_text


def _is_probable_path(token: str) -> bool:
    """Heuristically determine whether a token is a local filesystem path."""

    if not token:
        return False
    # Reject absurdly long tokens before any processing to avoid OS errors
    if len(token) > MAX_PATH_LENGTH:
        return False
    if token.startswith("#"):
        return False
    # Windows drive letters or Unix absolute/relative paths
    if token.startswith(("/", "~", "./", "../")):
        return True
    if len(token) >= 2 and token[1] == ":":
        return True
    # Things like `path/to/file.png`
    return os.sep in token or '"' in token


def _unescape_dragged_path(token: str) -> str:
    """Convert backslash-escaped spaces used by drag-and-drop to literal spaces."""
    # Shell/terminal escaping typically produces '\ ' sequences
    return token.replace(r"\ ", " ")


def _normalise_path(token: str) -> Path:
    """Expand user shortcuts and resolve relative components without touching fs."""
    # First unescape any drag-and-drop backslash spaces before other expansions
    unescaped = _unescape_dragged_path(token)
    expanded = os.path.expanduser(unescaped)
    try:
        # This will not resolve against symlinks because we do not call resolve()
        return Path(expanded).absolute()
    except Exception as exc:
        raise AttachmentParsingError(f"Invalid path '{token}': {exc}") from exc


def _determine_media_type(path: Path) -> str:
    """Best-effort media type detection for images only."""

    mime, _ = mimetypes.guess_type(path.name)
    if mime:
        return mime
    if path.suffix.lower() in DEFAULT_ACCEPTED_IMAGE_EXTENSIONS:
        return "image/png"
    return "application/octet-stream"


def _load_binary(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise AttachmentParsingError(f"Attachment not found: {path}") from exc
    except PermissionError as exc:
        raise AttachmentParsingError(
            f"Cannot read attachment (permission denied): {path}"
        ) from exc
    except OSError as exc:
        raise AttachmentParsingError(
            f"Failed to read attachment {path}: {exc}"
        ) from exc


def _tokenise(prompt: str) -> Iterable[str]:
    """Split the prompt preserving quoted segments using shell-like semantics."""

    if not prompt:
        return []
    try:
        # On Windows, avoid POSIX escaping so backslashes are preserved
        posix_mode = os.name != "nt"
        return shlex.split(prompt, posix=posix_mode)
    except ValueError:
        # Fallback naive split when shlex fails (e.g. unmatched quotes)
        return prompt.split()


def _strip_attachment_token(token: str) -> str:
    """Trim surrounding whitespace/punctuation terminals tack onto paths."""

    token = token.strip().strip(",;:()[]{}")
    # Windows terminals paste copied files as fully-quoted paths
    # ("C:\...\shot.png"). Non-POSIX shlex (used on Windows in
    # _tokenise) keeps those quotes ON the token, so the path was never
    # detected — peel one matching surrounding pair. POSIX shlex already
    # strips quotes, making this a no-op elsewhere.
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        token = token[1:-1]
    return token


def _candidate_paths(
    tokens: Sequence[str],
    start: int,
    max_span: int = 5,
) -> Iterable[tuple[str, int]]:
    """Yield space-joined token slices to reconstruct paths with spaces."""

    collected: list[str] = []
    for offset, raw in enumerate(tokens[start : start + max_span]):
        collected.append(raw)
        yield " ".join(collected), start + offset + 1


def _is_supported_extension(path: Path) -> bool:
    suffix = path.suffix.lower()
    return (
        suffix
        in DEFAULT_ACCEPTED_IMAGE_EXTENSIONS | DEFAULT_ACCEPTED_DOCUMENT_EXTENSIONS
    )


def _parse_link(token: str) -> PromptLinkAttachment | None:
    """URL parsing disabled: no URLs are treated as attachments."""
    return None


@dataclass
class _DetectedPath:
    placeholder: str
    path: Path | None
    start_index: int
    consumed_until: int
    unsupported: bool = False
    link: PromptLinkAttachment | None = None

    def has_path(self) -> bool:
        return self.path is not None and not self.unsupported


def _detect_path_tokens(prompt: str) -> tuple[list[_DetectedPath], list[str]]:
    # Preserve backslash-spaces from drag-and-drop before shlex tokenization
    # Replace '\ ' with a marker that shlex won't split, then restore later
    ESCAPE_MARKER = "\u0000ESCAPED_SPACE\u0000"
    masked_prompt = prompt.replace(r"\ ", ESCAPE_MARKER)
    tokens = list(_tokenise(masked_prompt))
    # Restore escaped spaces in individual tokens
    tokens = [t.replace(ESCAPE_MARKER, " ") for t in tokens]

    detections: list[_DetectedPath] = []
    warnings: list[str] = []

    index = 0
    while index < len(tokens):
        token = tokens[index]

        link_attachment = _parse_link(token)
        if link_attachment:
            detections.append(
                _DetectedPath(
                    placeholder=token,
                    path=None,
                    start_index=index,
                    consumed_until=index + 1,
                    link=link_attachment,
                )
            )
            index += 1
            continue

        stripped_token = _strip_attachment_token(token)
        if not _is_probable_path(stripped_token):
            index += 1
            continue

        # Additional guard: skip if stripped token exceeds reasonable path length
        if len(stripped_token) > MAX_PATH_LENGTH:
            index += 1
            continue

        start_index = index
        consumed_until = index + 1
        candidate_path_token = stripped_token
        # For placeholder: try to reconstruct escaped representation; if none, use raw token
        original_tokens_for_slice = list(_tokenise(masked_prompt))[index:consumed_until]
        candidate_placeholder = "".join(
            ot.replace(ESCAPE_MARKER, r"\ ") if ESCAPE_MARKER in ot else ot
            for ot in original_tokens_for_slice
        )
        # If placeholder seems identical to raw token, just use the raw token
        if candidate_placeholder == token.replace(" ", r"\ "):
            candidate_placeholder = token

        try:
            path = _normalise_path(candidate_path_token)
        except AttachmentParsingError as exc:
            warnings.append(str(exc))
            index = consumed_until
            continue

        # Guard filesystem operations against OS errors (ENAMETOOLONG, etc.)
        try:
            path_exists = path.exists()
            path_is_file = path.is_file() if path_exists else False
        except OSError:
            # Skip this token if filesystem check fails (path too long, etc.)
            index = consumed_until
            continue

        if not path_exists or not path_is_file:
            found_span = False
            last_path = path
            for joined, end_index in _candidate_paths(tokens, index):
                stripped_joined = _strip_attachment_token(joined)
                if not _is_probable_path(stripped_joined):
                    continue
                candidate_path_token = stripped_joined
                candidate_placeholder = joined
                consumed_until = end_index
                if len(candidate_path_token) > MAX_PATH_LENGTH:
                    continue
                try:
                    last_path = _normalise_path(candidate_path_token)
                except AttachmentParsingError:
                    # Suppress warnings for non-file spans; just skip quietly
                    found_span = False
                    break
                try:
                    if last_path.exists() and last_path.is_file():
                        path = last_path
                        found_span = True
                        # We'll rebuild escaped placeholder after this block
                        break
                except OSError:
                    continue
            if not found_span:
                # Quietly skip tokens that are not files
                index += 1
                continue
            # Reconstruct escaped placeholder for multi-token paths
            original_tokens_for_path = tokens[index:consumed_until]
            escaped_placeholder = " ".join(original_tokens_for_path).replace(" ", r"\ ")
            candidate_placeholder = escaped_placeholder
        if not _is_supported_extension(path):
            detections.append(
                _DetectedPath(
                    placeholder=candidate_placeholder,
                    path=path,
                    start_index=start_index,
                    consumed_until=consumed_until,
                    unsupported=True,
                )
            )
            index = consumed_until
            continue

        # Reconstruct escaped placeholder for exact replacement later
        # For unquoted spaces, keep the original literal token from the prompt
        # so replacement matches precisely
        escaped_placeholder = candidate_placeholder

        detections.append(
            _DetectedPath(
                placeholder=candidate_placeholder,
                path=path,
                start_index=start_index,
                consumed_until=consumed_until,
            )
        )
        index = consumed_until

    return detections, warnings


def parse_prompt_attachments(prompt: str) -> ProcessedPrompt:
    """Extract attachments from the prompt returning cleaned text and metadata."""

    attachments: List[PromptAttachment] = []

    detections, detection_warnings = _detect_path_tokens(prompt)
    warnings: List[str] = list(detection_warnings)

    link_attachments = [d.link for d in detections if d.link is not None]

    for detection in detections:
        if detection.link is not None and detection.path is None:
            continue
        if detection.path is None:
            continue
        if detection.unsupported:
            # Skip unsupported attachments without warning noise
            continue

        try:
            media_type = _determine_media_type(detection.path)
            data = _load_binary(detection.path)
        except AttachmentParsingError:
            # Silently ignore unreadable attachments to reduce prompt noise
            continue
        # Resize oversized images to match the same policy applied to clipboard
        # pastes.  Non-image types and PIL-unavailable cases pass through unchanged.
        data, media_type = normalize_image_bytes(data, media_type)
        attachments.append(
            PromptAttachment(
                placeholder=detection.placeholder,
                content=BinaryContent(data=data, media_type=media_type),
            )
        )

    # Rebuild cleaned_prompt by skipping tokens consumed as file paths.
    # This preserves original punctuation and spacing for non-attachment tokens.
    ESCAPE_MARKER = "\u0000ESCAPED_SPACE\u0000"
    masked = prompt.replace(r"\ ", ESCAPE_MARKER)
    tokens = list(_tokenise(masked))

    # Build exact token spans for file attachments (supported or unsupported)
    # Skip spans for: supported files (path present and not unsupported) and links.
    spans = [
        (d.start_index, d.consumed_until)
        for d in detections
        if (d.path is not None and not d.unsupported)
        or (d.link is not None and d.path is None)
    ]
    cleaned_parts: list[str] = []
    i = 0
    while i < len(tokens):
        span = next((s for s in spans if s[0] <= i < s[1]), None)
        if span is not None:
            i = span[1]
            continue
        cleaned_parts.append(tokens[i].replace(ESCAPE_MARKER, " "))
        i += 1

    cleaned_prompt = " ".join(cleaned_parts).strip()
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
    "ResolvedUserPrompt",
    "parse_prompt_attachments",
    "resolve_steer_content",
    "resolve_user_prompt",
]
