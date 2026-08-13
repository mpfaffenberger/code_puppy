"""Neutral provider seam for puppy_kennel memory recall.

Core never imports ``code_puppy.plugins.puppy_kennel`` directly. The plugin
registers a recall-block provider through the ``register_kennel_memory``
callback phase; token accounting consumes it through this module, so the
plugin can ship, toggle, or be removed without touching core.
"""

from __future__ import annotations

from typing import Callable, Optional

from code_puppy.callbacks import on_register_kennel_memory

KennelMemoryProvider = Callable[[], Optional[str]]


def get_kennel_memory_provider() -> Optional[KennelMemoryProvider]:
    """Return the first registered kennel memory provider (or None).

    Providers are resolved on every call so disabling the plugin takes
    effect immediately and no stale provider survives a config change.
    """
    for result in on_register_kennel_memory():
        if callable(result):
            return result
    return None


def get_kennel_recall_block() -> str:
    """Return the current recall block, or ``\"\"`` when none is available."""
    provider = get_kennel_memory_provider()
    if provider is None:
        return ""
    try:
        block = provider()
    except Exception:  # noqa: BLE001 - token accounting must never crash.
        return ""
    return block or ""
