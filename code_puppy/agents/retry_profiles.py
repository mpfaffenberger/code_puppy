"""Retry *policy* layer: named backoff profiles for streaming retries.

This module is the **policy** counterpart to the retry **mechanism** in
``_runtime.streaming_retry``. The mechanism knows how to loop, sleep, classify,
and log; this module decides *how many* attempts and *how long* to wait between
them -- as a small set of named, guard-railed profiles the user can select per
role (main agent vs sub-agent) and override per model.

Design guarantees (why you can't shoot your foot off)
-----------------------------------------------------
* Every delay is clamped to ``[MIN_DELAY_SECONDS, MAX_DELAY_SECONDS]`` -- the
  30s ceiling is a hard cap the user cannot exceed, and the 1s floor plus the
  exponential ramp make a pathological "10 retries in 10 seconds" impossible.
* Attempt counts are clamped to ``[1, MAX_ATTEMPTS_CEILING]``. A hand-edited
  config with ``retry_main_max_attempts = 999`` still resolves to the ceiling
  (100), whose worst-case backoff (~49.5 min) is bounded far below a runaway.
* Clamping happens at *read* time (:func:`resolve`), so a bad config value can
  never produce a pathological retry -- the guardrail isn't just in the UI.

The three strategies are all exponential-with-equal-jitter; they differ only in
how aggressively the exponent ramps toward the 30s cap:

* ``gentle``     -- eases up slowly; more early retries, later ones grow gradually.
* ``balanced``   -- classic doubling-ish ramp (the default).
* ``aggressive`` -- jumps to the 30s cap fast; best for hard rate limits where
  short waits are pointless and you want to sit at the max wait ASAP.

"Equal jitter" means each delay is ``half + random(0, half)`` of the capped
exponential value, so retries never synchronise into a thundering herd against a
shared gateway, yet never collapse below ``half`` of their intended spacing.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

# Hard bounds -- the user cannot escape these regardless of config.
MIN_DELAY_SECONDS: float = 1.0
MAX_DELAY_SECONDS: float = 30.0
# Ceiling on attempts. With the 30s delay cap, worst-case *sleep* time is
# ``(MAX_ATTEMPTS_CEILING - 1) * 30s`` = ~49.5 minutes at 100 attempts -- a
# generous budget for a stubborn rate limit, yet nowhere near a runaway (24h
# would need ~2880 retries). Bumping this stays safe as long as it's kept far
# below ``86400 / 30 = 2880``.
MAX_ATTEMPTS_CEILING: int = 100
MIN_ATTEMPTS_FLOOR: int = 1

# Absolute backstop on TOTAL retries within a single turn when progress-aware
# reset is active. The per-turn no-progress budget refreshes on genuine forward
# progress, so this only guards the pathological "one unit of progress, then
# die, forever" cycle. Kept far below the ~2880-retry/24h runaway line.
PROGRESS_RETRY_TOTAL_CEILING: int = 200

# Strategy name -> (base_seconds, exponent). All exponential-with-equal-jitter,
# all clamped to MAX_DELAY_SECONDS; they differ only in exponent aggressiveness.
STRATEGIES: Dict[str, Tuple[float, float]] = {
    "gentle": (2.0, 1.7),
    "balanced": (2.0, 2.2),
    "aggressive": (3.0, 3.0),
}
STRATEGY_NAMES: Tuple[str, ...] = tuple(STRATEGIES)

# Role -> (default_strategy, default_max_attempts). Sub-agents default to a much
# longer budget than the main loop because losing a sub-agent's accumulated work
# (a whole review, a whole plan) to a transient blip is never acceptable.
_ROLE_DEFAULTS: Dict[str, Tuple[str, int]] = {
    "main": ("balanced", 5),
    "subagent": ("balanced", 9),
}
ROLE_NAMES: Tuple[str, ...] = tuple(_ROLE_DEFAULTS)

_DEFAULT_STRATEGY = "balanced"


def _clamp_attempts(value: int) -> int:
    """Clamp an attempt count into ``[MIN_ATTEMPTS_FLOOR, MAX_ATTEMPTS_CEILING]``."""
    return max(MIN_ATTEMPTS_FLOOR, min(MAX_ATTEMPTS_CEILING, value))


def _normalise_strategy(name: Optional[str]) -> str:
    """Return a valid strategy name, falling back to ``balanced`` for junk.

    Tolerates non-string input (e.g. a misconfigured caller passing an int) by
    coercing before comparison -- a bad *type* must fall back, not raise.
    """
    if isinstance(name, str) and name.lower() in STRATEGIES:
        return name.lower()
    return _DEFAULT_STRATEGY


@dataclass(frozen=True)
class RetryProfile:
    """A resolved, guard-railed retry policy.

    ``strategy`` is always a valid key of :data:`STRATEGIES` and
    ``max_attempts`` is always within ``[MIN_ATTEMPTS_FLOOR, MAX_ATTEMPTS_CEILING]``
    -- the dataclass is only ever built by :func:`resolve` / :func:`make`, which
    clamp their inputs, so downstream code can trust these invariants.
    """

    role: str
    strategy: str
    max_attempts: int

    def compute_delays(self, rng: Optional[random.Random] = None) -> List[float]:
        """Return the ``max_attempts - 1`` inter-attempt delays, jittered.

        With N attempts only N-1 delays ever fire (the last attempt isn't
        followed by a sleep). Each delay is the capped exponential value with
        equal jitter applied, then clamped to the hard ``[MIN, MAX]`` bounds.
        A fresh ``rng`` is used per call so repeated runs don't retry in
        lock-step; pass a seeded ``random.Random`` in tests for determinism.
        """
        r = rng or random.Random()
        base, exponent = STRATEGIES[self.strategy]
        delays: List[float] = []
        capped = 0.0
        for i in range(max(0, self.max_attempts - 1)):
            # Short-circuit once we've reached the ceiling: never compute
            # ``exponent ** i`` for large ``i`` (it can OverflowError for big
            # attempt counts), and there's nothing left to grow toward anyway.
            if capped < MAX_DELAY_SECONDS:
                try:
                    raw = base * (exponent**i)
                except OverflowError:
                    raw = MAX_DELAY_SECONDS
                capped = min(raw, MAX_DELAY_SECONDS)
            half = capped / 2.0
            jittered = half + r.uniform(0.0, half)
            delays.append(
                round(max(MIN_DELAY_SECONDS, min(MAX_DELAY_SECONDS, jittered)), 2)
            )
        return delays


def make(
    role: str, strategy: Optional[str], max_attempts: Optional[int]
) -> RetryProfile:
    """Build a clamped :class:`RetryProfile` from raw (possibly invalid) inputs.

    Falls back to the role's defaults for anything missing or unknown, then
    clamps. Never raises -- an unknown ``role`` is treated as ``main``.
    """
    default_strategy, default_attempts = _ROLE_DEFAULTS.get(
        role, _ROLE_DEFAULTS["main"]
    )
    resolved_strategy = _normalise_strategy(strategy or default_strategy)
    resolved_attempts = _clamp_attempts(
        max_attempts if isinstance(max_attempts, int) else default_attempts
    )
    return RetryProfile(
        role=role, strategy=resolved_strategy, max_attempts=resolved_attempts
    )


# --- Config resolution -------------------------------------------------------
#
# Reads live in this module (not config.py) to keep the config surface small and
# avoid a circular import: config.py is imported by nearly everything, whereas
# this module is only pulled in lazily by the retry call sites.


def per_model_key(model_name: str, role: str, field: str) -> str:
    """Config key for a per-model, per-role retry override.

    ``role`` is ``"main"`` or ``"subagent"``; ``field`` is ``"strategy"`` or
    ``"max_attempts"``. Lives under a DEDICATED ``retry_model_<sanitized>_...``
    namespace -- deliberately NOT the shared ``model_settings_<model>_...``
    namespace, so it can never leak into the ``ModelSettings`` actually sent to
    the provider. Centralised here so the resolver and the /model settings UI
    agree on exactly one key format.
    """
    from code_puppy.config import _sanitize_model_name_for_key

    return f"retry_model_{_sanitize_model_name_for_key(model_name)}_{role}_{field}"


def _read_raw_setting(
    role: str, field: str, model_name: Optional[str]
) -> Optional[str]:
    """Resolve a single retry setting: per-model override -> global -> None.

    ``field`` is ``"strategy"`` or ``"max_attempts"``. Both the per-model override
    and the global fall back are role-SPECIFIC, so a model can be tuned to retry
    differently as the main agent vs. as a sub-agent.
    """
    from code_puppy.config import get_value

    if model_name:
        per_model = get_value(per_model_key(model_name, role, field))
        if per_model is not None and str(per_model).strip():
            return str(per_model).strip()

    global_val = get_value(f"retry_{role}_{field}")
    if global_val is not None and str(global_val).strip():
        return str(global_val).strip()
    return None


def _read_int(value: Optional[str]) -> Optional[int]:
    """Parse an int config string, or None if absent/garbage.

    Tolerates ``"5.0"``-style floats but rejects ``inf`` / ``-inf`` / ``nan``
    and out-of-range values (``int(inf)`` raises ``OverflowError``). Returning
    ``None`` for anything unparseable lets the caller fall back to the role
    default -- a garbage config value must NEVER crash the retry hot path.
    """
    if value is None:
        return None
    try:
        parsed = float(value)  # tolerate "5.0"
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):  # rejects inf / -inf / nan before int()
        return None
    try:
        return int(parsed)
    except (TypeError, ValueError, OverflowError):
        return None


def resolve(role: str, model_name: Optional[str] = None) -> RetryProfile:
    """Resolve the effective retry profile for ``role`` (optionally per-model).

    Precedence for each field: per-model override -> global setting -> role
    default. Everything is clamped by :func:`make`, so the returned profile is
    always safe to hand to the retry mechanism.
    """
    if role not in _ROLE_DEFAULTS:
        role = "main"
    strategy = _read_raw_setting(role, "strategy", model_name)
    max_attempts = _read_int(_read_raw_setting(role, "max_attempts", model_name))
    return make(role, strategy, max_attempts)


def make_streaming_retry(
    role: str,
    model_name: Optional[str] = None,
    rng: Optional[random.Random] = None,
    progress_fn: Optional[Callable[[], object]] = None,
) -> Callable[[Callable[[], object]], Callable[[], object]]:
    """Resolve the profile for ``role`` and return a configured retry decorator.

    Thin bridge between the policy layer (this module) and the mechanism layer
    (``_runtime.streaming_retry``). Call sites use this instead of hard-coding
    ``streaming_retry(...)`` so per-role / per-model config is honoured.

    ``progress_fn`` (optional) is a monotonic progress token source (e.g.
    ``lambda: len(agent._message_history)``). When supplied, the resolved
    ``max_attempts`` becomes the budget of consecutive *no-progress* retries,
    and an absolute backstop of ``PROGRESS_RETRY_TOTAL_CEILING`` (or the profile
    budget, whichever is larger) bounds a pathological "tiny progress then die"
    cycle. Without it, behaviour is the classic flat budget.

    Defensive by construction: if resolution or delay computation ever raises
    (a corrupt config, a future bug), we fall back to the role's default
    profile rather than letting a *retry-config* problem crash the very run
    the retry machinery exists to protect.
    """
    from code_puppy.agents._runtime import streaming_retry

    try:
        profile = resolve(role, model_name)
        delays = profile.compute_delays(rng)
        max_attempts = profile.max_attempts
    except Exception:
        fallback = make(role, None, None)
        try:
            delays = fallback.compute_delays(rng)
        except Exception:
            delays = [MIN_DELAY_SECONDS]
        max_attempts = fallback.max_attempts

    max_total_attempts = None
    if progress_fn is not None:
        max_total_attempts = max(max_attempts, PROGRESS_RETRY_TOTAL_CEILING)

    return streaming_retry(
        max_attempts=max_attempts,
        delays=delays,
        progress_fn=progress_fn,
        max_total_attempts=max_total_attempts,
    )
