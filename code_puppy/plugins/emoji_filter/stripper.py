"""Emoji stripping utilities.

One regex, one entrypoint. Beautiful is better than ugly.
"""

from __future__ import annotations

import re

# Covers the common pictographic / emoji unicode ranges, plus the zero-width
# joiner and variation selector-16 used to compose multi-codepoint emoji.
# Conservative: we do NOT strip basic punctuation, math symbols, arrows, or
# letter-like symbols outside these ranges.
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f5ff"  # misc symbols & pictographs
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f680-\U0001f6ff"  # transport & map
    "\U0001f700-\U0001f77f"  # alchemical
    "\U0001f780-\U0001f7ff"  # geometric shapes extended
    "\U0001f800-\U0001f8ff"  # supplemental arrows-C
    "\U0001f900-\U0001f9ff"  # supplemental symbols and pictographs
    "\U0001fa00-\U0001fa6f"  # chess symbols
    "\U0001fa70-\U0001faff"  # symbols & pictographs extended-A
    "\U0001fb00-\U0001fbff"  # symbols for legacy computing
    "\U00002600-\U000026ff"  # misc symbols (includes ☂ ☀ ♻ etc.)
    "\U00002700-\U000027bf"  # dingbats (✂ ✈ ✅ ❌ ❤ etc.)
    "\U0001f1e6-\U0001f1ff"  # regional indicator symbols (flags)
    "\U0000fe0f"  # variation selector-16
    "\U0000200d"  # zero width joiner
    "]+",
    flags=re.UNICODE,
)


def strip_emojis(text: str) -> str:
    """Return ``text`` with emoji codepoints removed. None-safe on non-strings."""
    if not isinstance(text, str) or not text:
        return text
    return _EMOJI_RE.sub("", text)


def contains_emoji(text: str) -> bool:
    """Quick check used mostly by tests."""
    if not isinstance(text, str) or not text:
        return False
    return _EMOJI_RE.search(text) is not None
