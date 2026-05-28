"""Model error normalization utilities.

Central place to parse provider-specific model errors (Anthropic, OpenAI,
Gemini, etc.) into a small, stable structure that the rest of the
application can use for retries and user-facing error messages.

This keeps provider-specific logic out of the core agent code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class NormalizedModelError:
    """Provider-agnostic view of a model error."""

    provider: Optional[str]
    code: Optional[str]
    http_status: Optional[int]
    is_transient: bool
    user_message: str
    raw_message: str


def _get_http_status(exc: Exception) -> Optional[int]:
    """Best-effort extraction of an HTTP status code from an exception."""

    for attr in ("status_code", "status", "http_status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    return None


def _get_body_dict(exc: Exception) -> Optional[dict[str, Any]]:
    """Try to extract a structured body dict from provider exceptions."""

    for attr in ("body", "response", "error", "errors", "detail"):
        value = getattr(exc, attr, None)
        if isinstance(value, dict):
            return value
    return None


def _detect_provider(exc: Exception) -> Optional[str]:
    """Infer model provider from the exception's module / type name."""

    module = getattr(exc.__class__, "__module__", "")
    name = exc.__class__.__name__.lower()
    module_lower = module.lower()

    if "anthropic" in module_lower or "anthropic" in name:
        return "anthropic"
    if "openai" in module_lower or "openai" in name:
        return "openai"
    if "google" in module_lower or "gemini" in module_lower or "gemini" in name:
        return "gemini"
    if "azure" in module_lower or "azure" in name:
        return "azure-openai"

    return None


def _classify_message(
    provider: Optional[str],
    raw: str,
    payload: Optional[dict[str, Any]],
    http_status: Optional[int],
) -> tuple[Optional[str], bool]:
    """Map provider error details to a (code, is_transient) pair.

    The goal is to keep this classification small and robust, not to
    perfectly mirror each provider's error taxonomy.
    """

    lower = raw.lower()

    # Rate limiting / overloaded / transient backend issues
    if any(
        k in lower
        for k in ("rate limit", "too many requests", "overloaded", "try again later")
    ):
        return "rate_limit_or_overloaded", True

    if any(
        k in lower
        for k in (
            "timeout",
            "temporarily unavailable",
            "server error",
            "gateway",
            "bad gateway",
        )
    ):
        return "backend_unavailable", True

    # HTTP status based classification (when available)
    if http_status in (429, 509):
        return "rate_limit_or_overloaded", True
    if http_status in (500, 502, 503, 504):
        return "backend_unavailable", True

    # Auth / configuration
    if any(
        k in lower
        for k in (
            "invalid api key",
            "authentication",
            "unauthorized",
            "forbidden",
            "permission",
        )
    ):
        return "auth_error", False

    # Model / quota
    if any(
        k in lower
        for k in (
            "model_not_found",
            "unknown model",
            "unsupported model",
            "no such model",
        )
    ):
        return "unsupported_model", False

    if any(
        k in lower for k in ("quota", "billing", "insufficient balance", "subscription")
    ):
        return "quota_exceeded", False

    # Safety / content policy
    if any(
        k in lower
        for k in ("safety", "content policy", "blocked content", "policy violation")
    ):
        return "content_blocked", False

    # Tool history corruption (Anthropic 400: orphaned or duplicated tool blocks).
    # These are non-transient — the history must be pruned before retrying.
    # Two distinct error shapes are handled:
    #   1. Orphaned tool_result: "unexpected tool_use_id" / "each tool_result block
    #      must have a corresponding tool_use" — a tool_result with no matching tool_use.
    #   2. Duplicate tool_result: "each tool_use must have a single result. Found
    #      multiple tool_result blocks with id: ..." — happens when a streaming session
    #      is interrupted mid-tool-call and the user resumes with "continue".
    if any(
        k in lower
        for k in (
            "unexpected tool_use_id",
            "unexpected tool_result",
            "tool_use ids found without tool_result",
            "each tool_result block must have a corresponding tool_use",
            "each tool_use must have a single result",
            "found multiple `tool_result` blocks",
        )
    ):
        return "invalid_tool_history", False

    # Default: unknown and non-transient
    return None, False


def _build_user_message(
    provider: Optional[str],
    code: Optional[str],
    is_transient: bool,
    raw: str,
) -> str:
    """Return a short, user-facing message based on normalized fields."""

    prov = provider or "The model"

    if code == "rate_limit_or_overloaded":
        return (
            f"{prov} is temporarily overloaded or rate-limited. "
            "You can try again in a bit, or switch models with /model."
        )

    if code == "backend_unavailable":
        return (
            f"{prov} is currently unavailable due to a server issue. "
            "Please try again shortly or switch models with /model."
        )

    if code == "auth_error":
        return (
            f"{prov} rejected this request due to an authentication or "
            "permission error. Check your API key and configuration."
        )

    if code == "unsupported_model":
        return (
            f"The requested model is not available for {prov}. "
            "Try switching to a different model with /model."
        )

    if code == "quota_exceeded":
        return (
            f"{prov} reports that your quota or billing limits have been "
            "exceeded. Check your usage or choose a different provider/model."
        )

    if code == "content_blocked":
        return (
            f"{prov} blocked this request due to safety or content policy "
            "restrictions. Try rephrasing the request."
        )

    if code == "invalid_tool_history":
        return (
            "The conversation history has mismatched tool calls. "
            "Code Puppy is attempting to repair it automatically. "
            "If this keeps happening, starting a new session will resolve it."
        )

    # Fallback: generic but informative
    short_raw = raw.strip().split("\n", 1)[0]
    if len(short_raw) > 200:
        short_raw = short_raw[:197] + "..."

    return f"The model returned an unexpected error: {short_raw}"


def normalize_model_error(exc: Exception) -> NormalizedModelError:
    """Normalize provider-specific model errors into a common structure.

    This is intentionally conservative: when we cannot confidently
    classify an error, we mark it as non-transient and provide a
    generic user-facing message.

    Classification uses the combined text from:
    - ``str(exc)`` — the primary error representation.
    - String-valued ``.message``, ``.body``, and ``.detail`` attributes —
      Anthropic's ``APIStatusError`` surfaces the HTTP body as ``.message``.
    - The exception's ``__cause__`` chain.
    """

    raw = str(exc) if exc is not None else ""

    # Collect additional candidate text from well-known string attributes so
    # that providers that embed the error body in a non-str attribute (e.g.
    # Anthropic's APIStatusError.message) are also classified correctly.
    parts: list[str] = [raw]
    for attr in ("message", "body", "detail"):
        val = getattr(exc, attr, None)
        if val and isinstance(val, str) and val != raw:
            parts.append(val)
        elif val and not isinstance(val, str):
            try:
                parts.append(str(val))
            except Exception:  # noqa: BLE001
                pass
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        parts.append(str(cause))
    combined_raw = " ".join(parts)

    provider = _detect_provider(exc)
    http_status = _get_http_status(exc)
    payload = _get_body_dict(exc)

    code, is_transient = _classify_message(provider, combined_raw, payload, http_status)
    user_message = _build_user_message(provider, code, is_transient, combined_raw)

    return NormalizedModelError(
        provider=provider,
        code=code,
        http_status=http_status,
        is_transient=is_transient,
        user_message=user_message,
        raw_message=raw,
    )
