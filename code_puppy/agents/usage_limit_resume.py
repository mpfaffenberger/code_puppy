"""Opt-in auto-resume when a provider usage cap says "try again in N minutes".

Normal transient retries (``_runtime.streaming_retry``) back off for seconds and
give up after a handful of attempts -- right for a per-minute 429 blip, useless
against a quota window that resets in 47 minutes. When the user opts in
(``/set auto_resume_on_usage_limit true``) the retry loop asks this module how
long the provider wants us to wait, sleeps until then, and re-runs the turn from
its last checkpoint -- no "continue" prompt needed.

Detection is deliberately text-based so small changes to the error JSON shape
don't break it: every exception in the cause chain (and ExceptionGroup members)
is stringified together with its ``body`` / ``message`` / response text, and we
look for a "try again in <duration>" phrase alongside a rate-limit signal (HTTP
429, ``rate_limit_error``, "rate limit", "usage limit", "quota").
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timedelta
from typing import Any, Iterable, Iterator, Optional

# ---- Settings ---------------------------------------------------------------

ENABLED_KEY = "auto_resume_on_usage_limit"
MAX_WAIT_KEY = "auto_resume_max_wait_minutes"
MAX_RESUMES_KEY = "auto_resume_max_resumes"

DEFAULT_MAX_WAIT_MINUTES = 300
DEFAULT_MAX_RESUMES = 3
#: Extra seconds slept past the advertised reset so we don't retry a hair early.
RESET_BUFFER_SECONDS = 30.0
#: Shorter waits are ordinary 429 blips -- left to the normal backoff path.
MIN_USAGE_LIMIT_WAIT_SECONDS = 60.0
#: Wall-clock poll interval; keeps the deadline correct across laptop sleep.
_SLEEP_CHUNK_SECONDS = 15.0


def _read_int(key: str, default: int, minimum: int) -> int:
    try:
        from code_puppy.config import get_value

        raw = get_value(key)
        if raw is None or str(raw).strip() == "":
            return default
        return max(minimum, int(str(raw).strip()))
    except Exception:
        return default


def is_enabled() -> bool:
    """Opt-in switch; off unless the user sets it. Never raises."""
    try:
        from code_puppy.config import get_truthy_bool_value

        return get_truthy_bool_value(ENABLED_KEY, False)
    except Exception:
        return False


def get_max_wait_minutes() -> int:
    """Longest reset window we're willing to sleep through (minutes)."""
    return _read_int(MAX_WAIT_KEY, DEFAULT_MAX_WAIT_MINUTES, 1)


def get_max_resumes() -> int:
    """Back-to-back auto-resumes allowed within one turn."""
    return _read_int(MAX_RESUMES_KEY, DEFAULT_MAX_RESUMES, 1)


# ---- Parsing ----------------------------------------------------------------

_LEAD_RE = re.compile(
    r"(?:try\s+again|retry|resets?)\s+(?:in|after)\s+"
    r"(?:about\s+|approximately\s+|around\s+|roughly\s+|~\s*)?",
    re.IGNORECASE,
)
_PART_RE = re.compile(
    r"\s*(?:,\s*|and\s+)?(\d+(?:\.\d+)?)\s*"
    r"(hours|hour|hrs|hr|h|minutes|minute|mins|min|m|seconds|second|secs|sec|s)"
    r"(?![a-z])",
    re.IGNORECASE,
)
_UNIT_SECONDS = {"h": 3600.0, "m": 60.0, "s": 1.0}
_RATE_LIMIT_SIGNAL_RE = re.compile(
    r"rate[\s_-]?limit|usage[\s_-]?limit|quota|too\s+many\s+requests|\b429\b",
    re.IGNORECASE,
)
_MAX_CHAIN_DEPTH = 6


def parse_wait_seconds(text: str) -> Optional[float]:
    """Seconds from a "try again in 1h 30m" style phrase, or ``None``.

    Accepts hours/minutes/seconds in long or short form, combined
    ("1h30m", "2 hours and 5 minutes", "1 hour, 10 minutes") and fractional
    ("4.5 minutes"). Returns the first phrase that parses.
    """
    if not text:
        return None
    for lead in _LEAD_RE.finditer(text):
        pos = lead.end()
        total = 0.0
        matched = False
        while True:
            part = _PART_RE.match(text, pos)
            if part is None:
                break
            matched = True
            total += float(part.group(1)) * _UNIT_SECONDS[part.group(2)[0].lower()]
            pos = part.end()
        if matched:
            return total
    return None


def _safe_str(value: Any) -> str:
    try:
        return "" if value is None else str(value)
    except Exception:
        return ""


def _walk(exc: BaseException) -> Iterator[BaseException]:
    """Cause/context chain plus ExceptionGroup members, cycle-safe."""
    seen: set[int] = set()
    stack: list[tuple[BaseException, int]] = [(exc, 0)]
    while stack:
        node, depth = stack.pop()
        if node is None or id(node) in seen or depth > _MAX_CHAIN_DEPTH:
            continue
        seen.add(id(node))
        yield node
        members = getattr(node, "exceptions", None)
        if isinstance(members, (list, tuple)):
            stack.extend((m, depth + 1) for m in members)
        for nxt in (node.__cause__, node.__context__):
            if nxt is not None:
                stack.append((nxt, depth + 1))


def _texts(link: BaseException) -> Iterable[str]:
    yield _safe_str(link)
    for attr in ("body", "message"):
        yield _safe_str(getattr(link, attr, None))
    response = getattr(link, "response", None)
    if response is not None:
        try:
            yield _safe_str(response.text)
        except Exception:
            pass


def _status_code(link: BaseException) -> Optional[int]:
    status = getattr(link, "status_code", None)
    if status is None:
        status = getattr(getattr(link, "response", None), "status_code", None)
    return status if isinstance(status, int) else None


def _retry_after_seconds(headers: Any) -> Optional[float]:
    try:
        raw = headers.get("retry-after") if headers is not None else None
        return float(raw) if raw is not None else None
    except Exception:
        return None


def wait_from_text(text: str, status_code: Optional[int] = None) -> Optional[float]:
    """Usage-cap wait for one blob of error text (needs a rate-limit signal)."""
    seconds = parse_wait_seconds(text)
    if seconds is None:
        return None
    if status_code == 429 or _RATE_LIMIT_SIGNAL_RE.search(text):
        return seconds
    return None


def usage_limit_wait_seconds(exc: BaseException) -> Optional[float]:
    """How long the provider asked us to wait, if ``exc`` is a usage cap.

    ``None`` means "not a usage-cap error" -- fall through to normal retries.
    """
    try:
        links = list(_walk(exc))
        blob = "\n".join(t for link in links for t in _texts(link) if t)
        is_429 = any(_status_code(link) == 429 for link in links)
        seconds = wait_from_text(blob, 429 if is_429 else None)
        if seconds is not None:
            return seconds if seconds >= MIN_USAGE_LIMIT_WAIT_SECONDS else None
        # No phrase in the text: honour a long Retry-After on a real 429.
        for link in links:
            if _status_code(link) != 429:
                continue
            headers = getattr(getattr(link, "response", None), "headers", None)
            after = _retry_after_seconds(headers)
            if after is not None and after >= MIN_USAGE_LIMIT_WAIT_SECONDS:
                return after
    except Exception:
        return None
    return None


async def response_is_usage_limit(response: Any) -> bool:
    """For HTTP retry layers: should this 429 skip the short-backoff loop?

    Only when the feature is on -- then the turn-level retry handles the long
    wait instead of burning attempts on 1-60s sleeps. Reads the (small) body;
    httpx caches it so the SDK can still build its error. Never raises.
    """
    try:
        if getattr(response, "status_code", None) != 429 or not is_enabled():
            return False
        after = _retry_after_seconds(getattr(response, "headers", None))
        if after is not None and after >= MIN_USAGE_LIMIT_WAIT_SECONDS:
            return True
        body = await response.aread()
        text = body.decode("utf-8", "replace") if isinstance(body, bytes) else ""
        seconds = wait_from_text(text, 429)
        return seconds is not None and seconds >= MIN_USAGE_LIMIT_WAIT_SECONDS
    except Exception:
        return False


# ---- Waiting ----------------------------------------------------------------


def _format_duration(seconds: float) -> str:
    seconds = int(max(0, round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    return f"{secs}s"


async def wait_for_reset(seconds: float, attempt: int, max_resumes: int) -> None:
    """Sleep until the reset (+buffer) against the wall clock; cancellable.

    ``asyncio.sleep`` runs on a monotonic clock that pauses while the machine
    is suspended, so we sleep in short chunks and re-check ``time.time()``.
    """
    from code_puppy.i18n import t
    from code_puppy.messaging import emit_warning

    total = max(0.0, seconds) + RESET_BUFFER_SECONDS
    deadline = time.time() + total
    resume_at = (datetime.now() + timedelta(seconds=total)).strftime("%H:%M")
    emit_warning(
        t(
            "agent.usage_limit.waiting",
            resume_at=resume_at,
            duration=_format_duration(total),
            attempt=attempt,
            max_resumes=max_resumes,
        )
    )
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        await asyncio.sleep(min(_SLEEP_CHUNK_SECONDS, remaining))
    emit_warning(t("agent.usage_limit.resuming"))


def describe_too_long(seconds: float) -> str:
    """User-facing note when the reset is beyond the configured max wait."""
    from code_puppy.i18n import t

    return t(
        "agent.usage_limit.too_long",
        duration=_format_duration(seconds),
        max_minutes=get_max_wait_minutes(),
        key=MAX_WAIT_KEY,
    )
