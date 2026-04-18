"""Fast mode support for Claude Code OAuth.

Fast mode adds two wire-level changes when enabled via the per-model
``fast`` setting:

1. ``speed: "fast"`` is injected into the ``/v1/messages`` request payload.
2. ``fast-mode-2026-02-01`` is appended to the ``anthropic-beta`` header.

The setting is read at request time (not model construction time) so that
toggling takes effect on the next call without a full agent reload for the
payload side. The beta header must still be present on the httpx client at
construction time, so we set that up once and rely on the existing
interleaved-thinking pattern for consistency.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, MutableMapping

# Anthropic beta marker for fast mode. Keep as a module-level constant so
# there's one source of truth for both header setup and tests.
FAST_MODE_BETA = "fast-mode-2026-02-01"

# The per-model setting key. Stored via code_puppy.config.set_model_setting
# as "true"/"false" strings and read back via get_all_model_settings.
#
# We intentionally DO NOT use get_effective_model_settings here: that helper
# filters values through model_supports_setting(), whose default allowlist for
# claude-* models is {temperature, extended_thinking, budget_tokens, effort}.
# ``fast`` is a plugin-owned setting, not a core setting, so it would be
# silently dropped. get_all_model_settings returns the raw per-model config,
# which is exactly what a plugin should own and read.
FAST_SETTING_KEY = "fast"


def is_fast_mode_enabled(model_name: str) -> bool:
    """Return True if the ``fast`` setting is on for ``model_name``."""
    # Imported lazily to avoid circular imports at module load.
    from code_puppy.config import get_all_model_settings

    settings = get_all_model_settings(model_name)
    return bool(settings.get(FAST_SETTING_KEY, False))


def ensure_fast_beta_header(headers: MutableMapping[str, str], enabled: bool) -> None:
    """Add or remove ``fast-mode-2026-02-01`` from the anthropic-beta header.

    Mutates ``headers`` in place. Mirrors the interleaved-thinking handling so
    beta markers stay comma-separated and de-duplicated.
    """
    existing = headers.get("anthropic-beta")
    if existing:
        parts = [p.strip() for p in existing.split(",") if p.strip()]
    else:
        parts = []

    has_marker = FAST_MODE_BETA in parts
    if enabled and not has_marker:
        parts.append(FAST_MODE_BETA)
    elif not enabled and has_marker:
        parts = [p for p in parts if p != FAST_MODE_BETA]

    if parts:
        headers["anthropic-beta"] = ",".join(parts)
    elif "anthropic-beta" in headers:
        del headers["anthropic-beta"]


def _inject_speed_in_payload(payload: Dict[str, Any]) -> None:
    """Inject ``speed: "fast"`` into a /v1/messages payload dict in place."""
    if not isinstance(payload, dict):
        return
    # Respect an explicit speed already present (don't clobber caller intent).
    if "speed" not in payload:
        payload["speed"] = "fast"


def make_fast_mode_wrapper(
    original_create: Callable[..., Any], model_name: str
) -> Callable[..., Any]:
    """Wrap ``messages.create`` to inject ``speed: fast`` when enabled.

    The setting is re-read on every call so toggling via ``/claude-code-fast``
    takes effect on the very next request (no agent reload needed for the
    payload side of the equation).
    """

    async def wrapped_create(*args: Any, **kwargs: Any):
        if is_fast_mode_enabled(model_name):
            if kwargs:
                _inject_speed_in_payload(kwargs)
            elif args:
                maybe_payload = args[-1]
                if isinstance(maybe_payload, dict):
                    _inject_speed_in_payload(maybe_payload)

        return await original_create(*args, **kwargs)

    return wrapped_create


def patch_anthropic_client_fast_mode(client: Any, model_name: str) -> None:
    """Monkey-patch ``messages.create`` (and ``beta.messages.create``).

    Must be called *after* ``patch_anthropic_client_messages`` so our wrapper
    sits outside the cache-control injector — order of wrappers doesn't matter
    for correctness here, but keeping fast-mode outermost makes it easy to
    reason about.
    """
    try:
        messages_obj = getattr(client, "messages", None)
        if messages_obj is not None and hasattr(messages_obj, "create"):
            messages_obj.create = make_fast_mode_wrapper(
                messages_obj.create, model_name
            )
    except Exception:  # pragma: no cover - defensive
        pass

    try:
        beta_obj = getattr(client, "beta", None)
        if beta_obj is not None:
            beta_messages_obj = getattr(beta_obj, "messages", None)
            if beta_messages_obj is not None and hasattr(beta_messages_obj, "create"):
                beta_messages_obj.create = make_fast_mode_wrapper(
                    beta_messages_obj.create, model_name
                )
    except Exception:  # pragma: no cover - defensive
        pass
