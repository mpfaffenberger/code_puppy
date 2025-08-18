import asyncio
import json
import math
import time
from collections import deque
from typing import Any, Dict, Optional, Deque

import httpx

from code_puppy.tools.common import console


class RateLimiter:
    """Async rate limiter supporting RPM, min interval, max total requests,
    and token-per-minute limits.

    - requests_per_minute: max requests allowed per rolling 60s window
    - min_interval_seconds (aka rate_limit): minimum seconds between requests
    - max_requests_total: hard cap for total requests over the client's lifetime
    - tokens_per_minute: max estimated tokens allowed per rolling 60s window
    """

    def __init__(
        self,
        requests_per_minute: Optional[int] = None,
        min_interval_seconds: Optional[float] = None,
        max_requests_total: Optional[int] = None,
        tokens_per_minute: Optional[int] = None,
    ) -> None:
        self._rpm: Optional[int] = requests_per_minute
        self._min_interval: Optional[float] = min_interval_seconds
        self._max_total: Optional[int] = max_requests_total
        self._tpm: Optional[int] = tokens_per_minute

        self._lock = asyncio.Lock()
        # Per-request timestamps for RPM enforcement
        self._timestamps: Deque[float] = deque()
        # Token events (timestamp, tokens) for TPM enforcement
        self._token_events: Deque[tuple[float, int]] = deque()
        self._count: int = 0
        self._last_request_time: Optional[float] = None

    async def acquire(self, tokens: int = 0) -> None:
        while True:
            # Compute wait time inside lock based on current state
            async with self._lock:
                if self._max_total is not None and self._count >= self._max_total:
                    raise RuntimeError(
                        "Max requests limit reached (max_requests)."
                    )

                now = time.monotonic()
                wait_seconds = 0.0

                # Enforce min interval between requests
                if self._min_interval is not None and self._last_request_time is not None:
                    delta = now - self._last_request_time
                    if delta < self._min_interval:
                        wait_seconds = max(wait_seconds, self._min_interval - delta)

                # Enforce requests per rolling minute
                if self._rpm is not None and self._rpm > 0:
                    # Drop timestamps older than 60s
                    while self._timestamps and now - self._timestamps[0] >= 60.0:
                        self._timestamps.popleft()
                    if len(self._timestamps) >= self._rpm:
                        oldest = self._timestamps[0]
                        wait_seconds = max(wait_seconds, 60.0 - (now - oldest))

                # Enforce tokens per rolling minute
                if self._tpm is not None and self._tpm > 0 and tokens > 0:
                    # Drop token events older than 60s
                    while self._token_events and now - self._token_events[0][0] >= 60.0:
                        self._token_events.popleft()
                    current_tokens = sum(t for _, t in self._token_events)
                    if current_tokens + tokens > self._tpm and self._token_events:
                        oldest_ts, _ = self._token_events[0]
                        wait_seconds = max(wait_seconds, 60.0 - (now - oldest_ts))

                if wait_seconds <= 0.0:
                    # Record the request and proceed
                    self._count += 1
                    self._last_request_time = now
                    self._timestamps.append(now)
                    if self._tpm is not None and tokens > 0:
                        self._token_events.append((now, tokens))
                    return

            # Sleep outside the lock
            await asyncio.sleep(wait_seconds)


def _estimate_tokens_from_request(req: httpx.Request) -> int:
    """Estimate the number of tokens in a request based on its content."""
    try:
        # Only attempt parse for JSON bodies
        content_type = req.headers.get("content-type", "").lower()
        if "json" not in content_type:
            return 0
        body_bytes = req.content or b""
        if not body_bytes:
            return 0
        data = json.loads(body_bytes.decode("utf-8", errors="ignore"))
    except Exception:
        return 0

    texts: list[str] = []
    try:
        # OpenAI Chat-like schema
        if isinstance(data, dict):
            msgs = data.get("messages")
            if isinstance(msgs, list):
                for m in msgs:
                    if not isinstance(m, dict):
                        continue
                    c = m.get("content")
                    if isinstance(c, str):
                        texts.append(c)
                    elif isinstance(c, list):
                        for part in c:
                            if isinstance(part, dict) and isinstance(part.get("text"), str):
                                texts.append(part["text"])
            # Responses API / completion-like fields
            for key in ("input", "prompt", "text"):
                val = data.get(key)
                if isinstance(val, str):
                    texts.append(val)
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, str):
                            texts.append(item)
                        elif isinstance(item, dict) and isinstance(item.get("text"), str):
                            texts.append(item["text"])
    except Exception:
        return 0

    approx_tokens = 0
    if texts:
        combined = "\n".join(texts)
        # Very rough heuristic: ~4 characters per token for inputs
        approx_tokens = max(1, math.ceil(len(combined) / 4))

    # Also try to include declared output token caps if present
    try:
        if isinstance(data, dict):
            for out_key in ("max_output_tokens", "max_tokens"):
                out_val = data.get(out_key)
                if isinstance(out_val, int) and out_val > 0:
                    approx_tokens += out_val
                    break
    except Exception:
        pass

    return int(approx_tokens)


def create_rate_limited_client(client_args: Dict[str, Any], model_config: Dict[str, Any]) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient with rate limiting applied based on model_config.

    Supports keys at the model's top-level:
    - requests_per_minute (preferred)
    - max_requests_per_minute (backward-compatible alias)
    - rate_limit (interpreted as minimum seconds between requests)
    - max_requests (hard cap for the client lifetime)
    - max_token_limit_per_minute (token budget per rolling minute)
    """

    # Backward-compat alias for RPM
    rpm_val = model_config.get("requests_per_minute")
    if rpm_val is None:
        rpm_val = model_config.get("max_requests_per_minute")

    # Normalize/parse values if present
    def _to_int(val):
        try:
            return int(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def _to_float(val):
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    rpm = _to_int(rpm_val)
    min_interval = _to_float(model_config.get("rate_limit"))
    max_total = _to_int(model_config.get("max_requests"))
    tpm = _to_int(model_config.get("max_token_limit_per_minute"))

    if any(v is not None for v in (rpm, min_interval, max_total, tpm)):
        limiter = RateLimiter(
            requests_per_minute=rpm,
            min_interval_seconds=min_interval,
            max_requests_total=max_total,
            tokens_per_minute=tpm,
        )

        async def _on_request(request: httpx.Request) -> None:
            tokens = _estimate_tokens_from_request(request) if tpm else 0
            await limiter.acquire(tokens=tokens)

        # Merge with any existing event hooks provided via client_args
        existing_hooks = client_args.get("event_hooks") or {}
        # Ensure we don't mutate the original dicts
        merged_hooks = {k: list(v) for k, v in existing_hooks.items()}
        merged_hooks.setdefault("request", []).append(_on_request)
        client_args = dict(client_args)
        client_args["event_hooks"] = merged_hooks

        console.log(
            f"Enabled rate limiting - rpm={rpm}, min_interval={min_interval}, max_total={max_total}, tpm={tpm}"
        )

    # Build the AsyncClient with (possibly) augmented client_args
    return httpx.AsyncClient(**client_args)
