"""Drag-and-drop attachment placeholder helpers for the Textual prompt.

The classic (prompt_toolkit) UI shows a friendly ``[png image]`` placeholder
in place of a dragged image path via a display-only ``Processor`` -- the real
path stays in the buffer so attachment parsing still loads the bytes.

Textual's ``TextArea`` has no equivalent display-only transform, so we mirror
the behaviour with a small substitution dance instead:

* On paste, recognised image/document paths are swapped for their friendly
  placeholder *in the buffer*, and an ordered ``(placeholder, real_path)``
  mapping is returned.
* On submit, the placeholders are expanded back to the real (space-escaped)
  paths before the text reaches ``parse_prompt_attachments``.

All path detection + label formatting is reused verbatim from
``command_line/attachments.py`` so both UIs stay perfectly in sync.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from code_puppy.command_line.attachments import (
    _detect_path_tokens,
    _tokenise,
    attachment_placeholder_label,
)

# Same sentinel the attachments parser uses to survive shlex tokenisation of
# backslash-escaped (drag-and-drop) spaces.
_ESCAPE_MARKER = "\u0000ESCAPED_SPACE\u0000"

# Ordered list of (placeholder_text, real_path) substitutions.
AttachmentMapping = List[Tuple[str, str]]


def transform_dragged_paths(text: str) -> Tuple[str, AttachmentMapping]:
    """Replace recognised attachment paths with friendly placeholders.

    Returns ``(display_text, mapping)`` where ``display_text`` has each
    supported image/document path swapped for e.g. ``[png image]`` and
    ``mapping`` is the ordered list of ``(placeholder, real_path)`` pairs
    needed to expand them again at submit time. When nothing is recognised
    the original text is returned with an empty mapping.
    """
    if not text:
        return text, []

    detections, _warnings = _detect_path_tokens(text)
    masked = text.replace(r"\ ", _ESCAPE_MARKER)
    token_view = list(_tokenise(masked))

    # Collect (start, end, label, real_path) character spans to replace.
    replacements: list[tuple[int, int, str, str]] = []
    search_cursor = 0
    for detection in detections:
        if not (detection.path and detection.has_path()):
            continue

        label = attachment_placeholder_label(detection.path)
        span_tokens = token_view[detection.start_index : detection.consumed_until]
        raw_span = " ".join(span_tokens).replace(_ESCAPE_MARKER, r"\ ")

        index = text.find(raw_span, search_cursor)
        span_len = len(raw_span)
        if index == -1:
            # Fall back to the detection's own placeholder representation.
            index = text.find(detection.placeholder, search_cursor)
            span_len = len(detection.placeholder)
        if index == -1:
            continue

        replacements.append((index, index + span_len, label, str(detection.path)))
        search_cursor = index + span_len

    if not replacements:
        return text, []

    replacements.sort(key=lambda item: item[0])

    out: list[str] = []
    mapping: AttachmentMapping = []
    cursor = 0
    for start, end, label, real_path in replacements:
        out.append(text[cursor:start])
        out.append(label)
        mapping.append((label, real_path))
        cursor = end
    out.append(text[cursor:])

    return "".join(out), mapping


def placeholder_spans(plain: str, placeholders: Iterable[str]) -> List[Tuple[int, int]]:
    """Return ``(start, end)`` char spans of each placeholder within ``plain``.

    Every occurrence of every (unique) placeholder is reported, so the Textual
    prompt can italic-cyan them just like the classic prompt_toolkit UI does.
    """
    spans: List[Tuple[int, int]] = []
    for placeholder in dict.fromkeys(placeholders):  # de-dupe, keep order
        if not placeholder:
            continue
        width = len(placeholder)
        start = plain.find(placeholder)
        while start != -1:
            spans.append((start, start + width))
            start = plain.find(placeholder, start + width)
    return spans


def expand_placeholders(text: str, mapping: AttachmentMapping) -> str:
    """Swap friendly placeholders back to real (space-escaped) paths.

    Each mapping entry consumes the *first* remaining occurrence of its
    placeholder, so multiple identical placeholders (e.g. two ``[png image]``)
    expand to their respective paths in insertion order. Stale entries whose
    placeholder no longer appears (user deleted it) are simply skipped.
    """
    if not mapping:
        return text
    for placeholder, real_path in mapping:
        index = text.find(placeholder)
        if index == -1:
            continue
        escaped_path = real_path.replace(" ", r"\ ")
        text = text[:index] + escaped_path + text[index + len(placeholder) :]
    return text


__all__ = [
    "AttachmentMapping",
    "transform_dragged_paths",
    "expand_placeholders",
    "placeholder_spans",
]
