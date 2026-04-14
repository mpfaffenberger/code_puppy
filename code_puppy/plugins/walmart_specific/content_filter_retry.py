"""Azure content-filter false-positive detection and auto-retry callback.

Azure's content-filtering gateway (Element LLM Gateway → Azure) occasionally
blocks perfectly legitimate LLM responses with a canned "I'm sorry, but I
cannot assist …" reply and a ``response.incomplete`` status.  Simply
re-sending the conversation (or asking the model to "continue") almost always
succeeds on the next attempt.

This module provides:

* **Detection** — ``is_content_filter_response()`` uses conservative
  heuristics (short text + known refusal patterns) to identify false
  positives without matching legitimate agent refusals.

* **Callback** — ``on_result_check_content_filter()`` is registered on the
  ``agent_run_result`` hook so that :pymod:`base_agent` automatically retries
  when a filter hit is detected.  All Walmart / Azure-specific knowledge
  lives here; the core agent loop only knows "a plugin asked me to retry."
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from code_puppy.messaging import emit_warning

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Prompt sent on retry so the model sees conversation context and continues.
CONTENT_FILTER_RETRY_PROMPT: str = (
    "Your previous response was incorrectly blocked by a content-safety "
    "filter. Please continue — restate your full answer to the original "
    "request."
)

#: Pause (seconds) between content-filter retries.
CONTENT_FILTER_RETRY_DELAY: float = 1.0

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
# Detection
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


def _iter_result_text_candidates(result) -> Iterable[str]:
    """Yield plausible text payloads from a pydantic-ai run result.

    ``result.output`` is not reliably the raw model text — it may be structured
    output, empty, or something else entirely.  The durable signal lives in the
    underlying ``ModelResponse`` messages returned by ``new_messages()`` /
    ``all_messages()``.
    """
    output = getattr(result, "output", None)
    if isinstance(output, str) and output.strip():
        yield output

    for accessor_name in ("new_messages", "all_messages"):
        accessor = getattr(result, accessor_name, None)
        if not callable(accessor):
            continue

        try:
            messages = accessor()
        except Exception:
            continue

        for message in reversed(messages or []):
            text = getattr(message, "text", None)
            if isinstance(text, str) and text.strip():
                yield text

            for part in getattr(message, "parts", ()) or ():
                content = getattr(part, "content", None)
                if isinstance(content, str) and content.strip():
                    yield content



def _result_has_content_filter_finish_reason(result) -> bool:
    """Return True when the provider explicitly flagged content filtering."""
    for accessor_name in ("new_messages", "all_messages"):
        accessor = getattr(result, accessor_name, None)
        if not callable(accessor):
            continue

        try:
            messages = accessor()
        except Exception:
            continue

        for message in reversed(messages or []):
            if getattr(message, "finish_reason", None) == "content_filter":
                return True

    return False


# ---------------------------------------------------------------------------
# Hook callback  (registered on ``agent_run_result``)
# ---------------------------------------------------------------------------


def on_result_check_content_filter(result, agent_name: str, model_name: str):
    """Inspect an agent result; request retry if it's a content-filter refusal.

    Registered as an ``agent_run_result`` callback so the core retry loop in
    ``base_agent._run_with_result_hooks`` handles the mechanics (updating
    message history, re-running the agent, etc.).

    Returns:
        ``{"retry": True, "prompt": ..., "delay": ...}`` when a refusal is
        detected, otherwise ``None``.
    """
    detected_output = next(
        (text for text in _iter_result_text_candidates(result) if is_content_filter_response(text)),
        None,
    )
    if not detected_output and not _result_has_content_filter_finish_reason(result):
        return None

    emit_warning(
        "⚡ Azure content filter false-positive detected, requesting retry…"
    )
    logger.warning(
        "Content-filter false positive on model=%s agent=%s output=%r",
        model_name,
        agent_name,
        (detected_output or "<finish_reason=content_filter>")[:120],
    )
    return {
        "retry": True,
        "prompt": CONTENT_FILTER_RETRY_PROMPT,
        "delay": CONTENT_FILTER_RETRY_DELAY,
    }
