"""Line-ending reconciliation for the file-editing engine.

Why this exists
---------------
``fs_access`` reads and writes files with ``newline=""`` so bytes round-trip
faithfully -- a file's existing CRLF/LF/CR terminators are never silently
rewritten just because the file was edited. That is correct at the I/O layer,
but it pushes one problem up to the editing layer: **models always emit
``\\n``** in an ``old_str``/snippet, even when the target file uses ``\\r\\n``.
Matching a model-supplied ``\\n`` pattern against raw CRLF content fails on
every multi-line edit.

The strategy here is to translate the *pattern* into the *file's* line-ending
style, rather than normalizing the whole file to the model's style. Every byte
the model did not target stays untouched -- including in files with mixed
terminators, which stay mixed everywhere except the edited region.
"""

from __future__ import annotations

from typing import Optional, Tuple

CRLF = "\r\n"
LF = "\n"
CR = "\r"

# CRLF must be probed before CR/LF so its two-character sequence isn't shadowed.
_STYLES = (CRLF, LF, CR)


def detect_dominant(text: str) -> str:
    """Return the most common line terminator in ``text``.

    Falls back to ``"\\n"`` when ``text`` has no terminators at all (empty or
    single-line content), which makes every conversion below a no-op.
    """
    crlf = text.count(CRLF)
    # Each CRLF contains a CR and an LF; discount them from the solo tallies.
    cr_only = text.count(CR) - crlf
    lf_only = text.count(LF) - crlf

    if crlf and crlf >= lf_only and crlf >= cr_only:
        return CRLF
    if cr_only and cr_only > lf_only:
        return CR
    return LF


def to_lf(text: str) -> str:
    """Normalize every terminator style in ``text`` to a bare ``\\n``."""
    return text.replace(CRLF, LF).replace(CR, LF)


def to_style(text: str, style: str) -> str:
    """Rewrite every terminator in ``text`` to ``style``."""
    normalized = to_lf(text)
    if style == LF:
        return normalized
    return normalized.replace(LF, style)


def resolve_pattern(haystack: str, pattern: str) -> Tuple[Optional[str], int, str]:
    """Find the form of ``pattern`` that actually occurs in ``haystack``.

    Returns ``(effective_pattern, occurrence_count, style)``. ``style`` is the
    terminator the matched form uses, so the caller can convert its
    replacement text to match the surrounding file.

    The pattern is tried verbatim first, so a caller that already supplied
    exact bytes is never second-guessed. Then the file's dominant style, then
    the remaining styles -- which is what makes mixed-terminator files work.
    When nothing matches, returns ``(None, 0, <dominant style>)`` so the
    caller can still report a sensible style in its error path.
    """
    dominant = detect_dominant(haystack)

    if pattern == "":
        return None, 0, dominant

    # Single-line patterns contain no terminators; no reconciliation applies.
    if LF not in pattern and CR not in pattern:
        return pattern, haystack.count(pattern), dominant

    count = haystack.count(pattern)
    if count:
        return pattern, count, detect_dominant(pattern)

    ordered = (dominant,) + tuple(s for s in _STYLES if s != dominant)
    for style in ordered:
        candidate = to_style(pattern, style)
        if candidate == pattern:
            continue  # already tried verbatim above
        count = haystack.count(candidate)
        if count:
            return candidate, count, style

    return None, 0, dominant
