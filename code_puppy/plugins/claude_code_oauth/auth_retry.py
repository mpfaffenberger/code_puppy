"""Agent-level auto-retry for Claude Code OAuth auth failures.

The HTTP client (``ClaudeCacheAsyncClient``) already refreshes tokens and
retries a *single request* once. But when an auth error still escapes —
refresh hiccup, a second 401 blocked by the one-shot request guard, or a
Cloudflare HTML 400 — it surfaces as a 4xx exception that the core
streaming-retry classifier deliberately does not retry, killing the whole
agent run.

This module plugs that gap via the ``agent_retryable_exception`` hook:
when the active model is a ``claude-code-*`` OAuth model and the exception
chain looks auth-related (401/403, or Cloudflare's HTML 400), we force a
token refresh, propagate the fresh token to any live Anthropic clients,
and return ``True`` so the exception rides the **main agent retry loop**
(``streaming_retry``) — the same delays, banners, error-logging, and
attempt cap as a 429. The loop's ``max_attempts`` bounds us, so a dead
refresh token can't spin forever.

Recovery escalation ladder for Cloudflare HTML 400s specifically:
refresh-token exchanges only buy temporary recovery (the edge starts
flapping again minutes later), while a full interactive re-auth durably
cures it. So the first CF400 gets the cheap refresh+retry; a recurrence
within ``CLOUDFLARE_REAUTH_WINDOW_SECONDS`` escalates to the browser
sign-in flow before retrying.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Iterator, Optional
from weakref import WeakSet

from code_puppy.messaging import emit_info, emit_warning

from .config import CLAUDE_CODE_OAUTH_CONFIG
from .utils import load_stored_tokens, refresh_access_token

logger = logging.getLogger(__name__)

AUTH_STATUS_CODES = frozenset({401, 403})
CLOUDFLARE_400_MARKERS = ("cloudflare", "400 bad request")

# Cloudflare 400s are only *durably* cured by a full interactive re-auth
# (field evidence: refresh-token exchanges buy temporary recovery, then the
# edge starts flapping again; a browser sign-in stops it entirely). The
# first CF400 gets the cheap refresh+retry. A recurrence within this window
# proves refresh isn't curing it, so we escalate to the browser flow.
CLOUDFLARE_REAUTH_WINDOW_SECONDS = 900.0  # 15 minutes

# Monotonic timestamp of the last Cloudflare-400 recovery attempt.
# Module-level: recurrence is a per-process pattern, not per-run.
_last_cloudflare_event_at: float = 0.0

# Live-client token updaters, registered when a claude_code model is built.
# Weak references: entries vanish automatically when a model is torn down
# (the client holds the only strong ref to its updater closure).
_token_updaters: "WeakSet[Callable[[str], None]]" = WeakSet()


def register_runtime_token_updater(updater: Callable[[str], None]) -> None:
    """Track a live client's token-update callback for broadcast on refresh."""
    _token_updaters.add(updater)


def _broadcast_token(access_token: str) -> None:
    """Push a freshly refreshed token into every live Anthropic client."""
    for updater in list(_token_updaters):
        try:
            updater(access_token)
        except Exception as exc:
            logger.debug("Runtime token updater failed: %s", exc)


def _iter_exception_chain(exc: BaseException) -> Iterator[BaseException]:
    """Yield ``exc`` and everything it wraps via __cause__/__context__."""
    seen: set = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _status_code_of(exc: BaseException) -> Optional[int]:
    """Best-effort HTTP status extraction across SDK exception shapes.

    Covers anthropic ``APIStatusError`` / pydantic-ai ``ModelHTTPError``
    (``status_code`` attribute) and ``httpx.HTTPStatusError``
    (``response.status_code``).
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _is_cloudflare_400(exc: BaseException, status: Optional[int]) -> bool:
    """Detect Cloudflare's HTML 400 page, which masks auth failures."""
    if status not in (None, 400):
        return False
    text = str(exc).lower()
    body = getattr(exc, "body", None)
    if body is not None:
        text = f"{text} {str(body).lower()}"
    return all(marker in text for marker in CLOUDFLARE_400_MARKERS)


def is_claude_auth_error(exc: BaseException) -> bool:
    """True when any link in the exception chain looks auth-related."""
    for link in _iter_exception_chain(exc):
        status = _status_code_of(link)
        if status in AUTH_STATUS_CODES:
            return True
        if _is_cloudflare_400(link, status):
            return True
    return False


def is_cloudflare_error(exc: BaseException) -> bool:
    """True when any link in the chain is specifically a Cloudflare 400."""
    return any(
        _is_cloudflare_400(link, _status_code_of(link))
        for link in _iter_exception_chain(exc)
    )


def _run_full_reauthentication(model_name: str) -> Optional[str]:
    """Launch the interactive browser OAuth flow; returns a token or None.

    Lazy import: register_callbacks imports this module at load time, so a
    top-level import here would be circular.
    """
    from .register_callbacks import _reauthenticate_after_expired_oauth

    return _reauthenticate_after_expired_oauth(model_name)


async def handle_retryable_exception(
    exception: Exception, *args: Any, **kwargs: Any
) -> bool:
    """``agent_retryable_exception`` hook: opt auth errors into the retry loop.

    Returning ``True`` hands the exception to the main agent retry loop
    (standard delays / attempt cap). Recovery work — the token refresh —
    happens here, *before* the loop's backoff sleep, so the next attempt
    goes out with fresh credentials.
    """
    model_name = kwargs.get("model_name") or ""
    if not model_name.startswith(CLAUDE_CODE_OAUTH_CONFIG["prefix"]):
        return False

    if not is_claude_auth_error(exception):
        return False

    tokens = load_stored_tokens()
    if not tokens or not tokens.get("refresh_token"):
        emit_warning(
            "Claude Code OAuth auth error, but no stored tokens to refresh. "
            "Run /claude-code-auth to sign in again."
        )
        return False

    # Cloudflare 400s that keep recurring are not cured by refresh-token
    # exchanges (field-proven); only a full interactive re-auth stops them.
    global _last_cloudflare_event_at
    if is_cloudflare_error(exception):
        now = time.monotonic()
        recurring = (
            _last_cloudflare_event_at > 0
            and (now - _last_cloudflare_event_at) < CLOUDFLARE_REAUTH_WINDOW_SECONDS
        )
        _last_cloudflare_event_at = now
        if recurring:
            emit_warning(
                "Cloudflare keeps rejecting requests and token refresh isn't "
                "curing it — escalating to full browser re-authentication…"
            )
            token = await asyncio.to_thread(_run_full_reauthentication, model_name)
            if token:
                _broadcast_token(token)
                _last_cloudflare_event_at = 0.0  # cured; future CF400s start fresh
                emit_info("Claude Code re-authentication complete; retrying.")
                return True
            emit_warning(
                "Re-authentication did not produce a usable token. "
                "Run /claude-code-auth manually."
            )
            return False

    emit_warning(
        "Claude Code OAuth rejected the request — ensuring a fresh token "
        "before the retry…"
    )

    # refresh_access_token does blocking network I/O; keep the loop free.
    # (It has a built-in cooldown: if a refresh just happened, it reuses the
    # still-warm token instead of burning another refresh-token rotation.)
    refreshed = await asyncio.to_thread(refresh_access_token, True)
    if refreshed:
        _broadcast_token(refreshed)
        emit_info("Claude Code OAuth token ready; retrying.")
    else:
        # Still opt in: the HTTP client gets a fresh shot at recovery on the
        # next attempt (including its interactive reauthentication fallback).
        emit_warning(
            "Token refresh failed; retrying anyway so the client can re-authenticate."
        )

    return True
