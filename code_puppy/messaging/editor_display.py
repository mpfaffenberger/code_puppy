"""Display-time attachment placeholders for the persistent editor.

The classic prompt rendered recognised attachment paths as friendly
tags ("[png image]") via a prompt_toolkit ``Processor``
(``AttachmentPlaceholderProcessor`` in
``command_line.prompt_toolkit_completion`` — source of truth; its
span-location logic is mirrored here because a Processor can't run
outside prompt_toolkit). The raw editor paints plain text, so the same
transformation is applied to ``(buffer, cursor)`` right before the bar
paints the prompt row.

The REAL buffer keeps the path — submit-time attachment resolution
(``command_line.attachments``) is untouched; this is presentation only.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

#: Skip detection for very long input — likely pasted content; matches
#: the classic processor's ``_MAX_TEXT_LENGTH_FOR_REALTIME``.
MAX_TEXT_LENGTH_FOR_REALTIME = 500

_ESCAPE_MARKER = "\u0000ESCAPED_SPACE\u0000"


def to_display(text: str, cursor: int) -> Tuple[str, int]:
    """Map ``(buffer, cursor)`` to ``(display_text, display_cursor)``.

    Recognised attachment spans render as ``[png image]`` /
    ``[pdf document]`` / ``[file attachment]`` tags. Never raises — any
    failure falls back to the untransformed input.
    """
    try:
        return _transform(text, cursor)
    except Exception:
        logger.debug("attachment display transform failed", exc_info=True)
        return text, cursor


def _transform(text: str, cursor: int) -> Tuple[str, int]:
    if not text or len(text) > MAX_TEXT_LENGTH_FOR_REALTIME:
        return text, cursor
    # Cheap pre-check: every detectable path/link contains a separator.
    # Skips tokenisation + filesystem stats for ordinary typed prompts.
    if "/" not in text and "\\" not in text:
        return text, cursor

    replacements = _find_spans(text)
    if not replacements:
        return text, cursor
    replacements.sort(key=lambda item: item[0])

    display_parts: List[str] = []
    display_cursor = None
    src = 0
    disp = 0
    for start, end, tag in replacements:
        plain = text[src:start]
        if src <= cursor < start:
            display_cursor = disp + (cursor - src)
        display_parts.append(plain)
        disp += len(plain)
        if start <= cursor < end:
            # Classic parity: in-span source positions map to tag start.
            display_cursor = disp
        display_parts.append(tag)
        disp += len(tag)
        src = end
    tail = text[src:]
    display_parts.append(tail)
    if display_cursor is None:
        display_cursor = disp + max(0, min(cursor - src, len(tail)))
    return "".join(display_parts), display_cursor


def _find_spans(text: str) -> List[Tuple[int, int, str]]:
    """Locate ``(start, end, tag)`` spans for recognised attachments.

    Mirrors ``AttachmentPlaceholderProcessor.apply_transformation``'s
    span lookup (masked escaped-space tokenisation + sequential find).
    """
    from code_puppy.command_line.attachments import (
        DEFAULT_ACCEPTED_DOCUMENT_EXTENSIONS,
        DEFAULT_ACCEPTED_IMAGE_EXTENSIONS,
        _detect_path_tokens,
        _tokenise,
    )

    detections, _warnings = _detect_path_tokens(text)
    if not detections:
        return []

    masked_text = text.replace(r"\ ", _ESCAPE_MARKER)
    token_view = list(_tokenise(masked_text))

    spans: List[Tuple[int, int, str]] = []
    search_cursor = 0
    for detection in detections:
        tag: str | None = None
        if detection.path and detection.has_path():
            suffix = detection.path.suffix.lower()
            if suffix in DEFAULT_ACCEPTED_IMAGE_EXTENSIONS:
                tag = f"[{suffix.lstrip('.') or 'image'} image]"
            elif suffix in DEFAULT_ACCEPTED_DOCUMENT_EXTENSIONS:
                tag = f"[{suffix.lstrip('.') or 'file'} document]"
            else:
                tag = "[file attachment]"
        elif detection.link is not None:
            tag = "[link]"
        if not tag:
            continue

        span_tokens = token_view[detection.start_index : detection.consumed_until]
        raw_span = " ".join(span_tokens).replace(_ESCAPE_MARKER, r"\ ")
        index = text.find(raw_span, search_cursor)
        span_len = len(raw_span)
        if index == -1:
            placeholder = detection.placeholder
            index = text.find(placeholder, search_cursor)
            span_len = len(placeholder)
        if index == -1:
            continue
        spans.append((index, index + span_len, tag))
        search_cursor = index + span_len
    return spans


__all__ = ["MAX_TEXT_LENGTH_FOR_REALTIME", "to_display"]
