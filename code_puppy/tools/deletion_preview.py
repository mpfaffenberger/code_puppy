"""Safe, deletion-only content classification for previews and diffs."""

from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass
from typing import Literal

from code_puppy.tools import fs_access
from code_puppy.tools.io_backends import get_filesystem_backend


@dataclass(frozen=True)
class DeletionContent:
    """Text that is safe to preview, or an omission reason and known size."""

    kind: Literal["text", "omitted"]
    text: str | None
    size_bytes: int | None
    omission_reason: Literal["binary", "unsafe"] | None = None


class PlainTextDeletionPreview(str):
    """Marker for summaries that must bypass unified-diff rendering."""


@dataclass(frozen=True)
class DeletionPreparation:
    """Read result captured before permission is requested."""

    status: Literal["ready", "missing", "read_error"]
    content: DeletionContent | None = None
    error: Exception | None = None


def classify_deletion_content(content: bytes | str) -> DeletionContent:
    """Decode supported text strictly; never turn uncertain bytes into text.

    Byte input is decoded as BOM-marked UTF-8/16/32 (UTF-32 BOMs are checked
    before their UTF-16 prefixes), or plain UTF-8 when there is no BOM. String
    input is the filesystem-backend text API: it is inspected as-is and never
    encoded, re-encoded, or otherwise normalized.
    """
    if isinstance(content, bytes):
        size_bytes = len(content)
        has_bom = content.startswith(
            (
                b"\x00\x00\xfe\xff",
                b"\xff\xfe\x00\x00",
                b"\xef\xbb\xbf",
                b"\xfe\xff",
                b"\xff\xfe",
            )
        )
        # Outside a supported Unicode BOM, NUL bytes are strong evidence of
        # binary content. Check after recognizing BOMs so UTF-16/32 stays valid.
        text = None if b"\x00" in content and not has_bom else _decode_bytes(content)
    else:
        size_bytes = None
        text = content

    if text is None:
        return DeletionContent("omitted", None, size_bytes, "binary")
    if not _is_safe_text(text):
        return DeletionContent("omitted", None, size_bytes, "unsafe")
    return DeletionContent("text", text, size_bytes)


def prepare_deletion(file_path: str) -> DeletionPreparation:
    """Read once through the active filesystem and classify for safe preview."""
    try:
        if not fs_access.exists(file_path) or not fs_access.is_file(file_path):
            return DeletionPreparation("missing")

        if get_filesystem_backend() is None:
            with open(file_path, "rb") as file:
                source: bytes | str = file.read()
        else:
            # Backends expose text, not raw bytes/size. Inspect the returned
            # string as-is; never encode it or bypass the active backend.
            source = fs_access.read_text(file_path)

        return DeletionPreparation("ready", classify_deletion_content(source))
    except Exception as exc:
        return DeletionPreparation("read_error", error=exc)


def _decode_bytes(content: bytes) -> str | None:
    """Strictly decode supported BOMs, preferring UTF-32 over UTF-16."""
    if content.startswith((b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00")):
        encoding = "utf-32"
    elif content.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    elif content.startswith((b"\xfe\xff", b"\xff\xfe")):
        encoding = "utf-16"
    else:
        encoding = "utf-8"

    try:
        return content.decode(encoding, errors="strict")
    except UnicodeDecodeError:
        return None


def _is_safe_text(text: str) -> bool:
    """Reject terminal controls and lone CR while preserving ordinary text."""
    for index, char in enumerate(text):
        category = unicodedata.category(char)
        if category == "Cs":
            return False
        if category == "Cc" and char not in "\t\n\r":
            return False
        # str.splitlines() treats Unicode line/paragraph separators as line
        # boundaries too, which could inject extra lines into a unified diff.
        if category in {"Zl", "Zp"}:
            return False
        if char == "\r" and (index + 1 == len(text) or text[index + 1] != "\n"):
            return False
    return True


def escape_deletion_filename(filename: str) -> str:
    """Make controls, line separators, and lone surrogates visible in headers."""
    escaped: list[str] = []
    for char in filename:
        category = unicodedata.category(char)
        if category in {"Cc", "Cs", "Zl", "Zp"}:
            codepoint = ord(char)
            if codepoint <= 0xFF:
                escaped.append(f"\\x{codepoint:02x}")
            elif codepoint <= 0xFFFF:
                escaped.append(f"\\u{codepoint:04x}")
            else:
                escaped.append(f"\\U{codepoint:08x}")
        else:
            escaped.append(char)
    return "".join(escaped)


def create_deletion_diff(filename: str, text: str, context_lines: int) -> str:
    """Build a unified deletion diff using a terminal-safe display filename."""
    safe_filename = escape_deletion_filename(filename)
    return "".join(
        difflib.unified_diff(
            text.splitlines(keepends=True),
            [],
            fromfile=f"a/{safe_filename}",
            tofile=f"b/{safe_filename}",
            n=context_lines,
        )
    )
