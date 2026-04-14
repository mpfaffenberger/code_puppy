"""Azure content-filter false-positive detection.

Azure's content-filtering gateway occasionally blocks perfectly legitimate
LLM responses with a canned "I'm sorry, but I cannot assist …" reply and
a ``response.incomplete`` status.  Simply re-sending the same conversation
(or asking the model to "continue") almost always succeeds.

This module centralises the detection heuristics so that
:pymod:`code_puppy.agents.base_agent` can auto-retry transparently.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Max automatic retries when a content-filter false-positive is detected.
MAX_CONTENT_FILTER_RETRIES: int = 2

#: Pause (seconds) between content-filter retries.
CONTENT_FILTER_RETRY_DELAY: float = 1.0

#: Prompt sent on retry so the model sees conversation context and continues.
CONTENT_FILTER_RETRY_PROMPT: str = (
    "Your previous response was incorrectly blocked by a content-safety "
    "filter. Please continue — restate your full answer to the original "
    "request."
)

#: Responses shorter than this (chars) are eligible for pattern matching.
#: Real agent answers are almost always longer; filter refusals are one sentence.
_MAX_REFUSAL_LENGTH: int = 200

# All patterns are lowercase for case-insensitive matching.
_REFUSAL_PATTERNS: tuple[str, ...] = (
    "i'm sorry, but i cannot assist with that",
    "i'm sorry, but i can't assist with that",
    "i'm sorry, but i cannot help with that",
    "i'm sorry, but i can't help with that",
    "i cannot assist with that request",
    "i can't assist with that request",
    "sorry, but i can't help with that",
    "sorry, but i cannot help with that",
    "i'm not able to assist with that",
    "i'm unable to help with that request",
    "i'm unable to assist with that",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_content_filter_response(text: str | None) -> bool:
    """Return ``True`` when *text* looks like an Azure content-filter refusal.

    The check is intentionally conservative:

    * The text must be **short** (≤ ``_MAX_REFUSAL_LENGTH`` chars).  Genuine
      agent responses that happen to contain "sorry" won't match because
      they'll be far longer.
    * It must contain one of the known canned refusal phrases (case-insensitive).
    """
    if not text:
        return False
    stripped = text.strip()
    if len(stripped) > _MAX_REFUSAL_LENGTH:
        return False
    lowered = stripped.lower()
    return any(p in lowered for p in _REFUSAL_PATTERNS)
