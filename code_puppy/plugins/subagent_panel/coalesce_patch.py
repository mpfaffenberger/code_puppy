"""Coalesce sub-agent stream_event callbacks from a user plugin.

PUP-301 briefly patched ``code_puppy.agents.subagent_stream_handler`` in core so
parallel sub-agents don't create one asyncio task per streamed token. That fixed
Ctrl+T steer-overlay lag under a sub-agent swarm, but the feature belongs in the
user plugin while this experiment stays out of the repo.

This module installs the same behavior as a small monkeypatch:

* replace ``subagent_stream_handler._fire_callback`` with a batched version;
* wrap ``subagent_stream_handler.subagent_stream_handler`` so stream-end flushes
  any trailing events (especially ``part_end``);
* pass through to the original callback whenever ``subagent_panel`` is
  runtime-disabled via ``/set subagent_panel off``.

All state is event-loop local in practice: core calls this from the stream
handler running on the main loop. No locks, no cute cleverness. Cute cleverness
is how puppies end up inside washing machines.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional

logger = logging.getLogger(__name__)

COALESCE_INTERVAL_S: float = 0.050
_MARKER = "_subagent_panel_coalesced"

Event = tuple[str, Any, Optional[str]]
EnabledChecker = Callable[[], bool]
FireCallback = Callable[[str, Any, Optional[str]], None]

_pending_events: list[Event] = []
_drain_scheduled = False
_last_drain_time = 0.0
_original_fire_callback: FireCallback | None = None
_original_stream_handler: Callable[..., Awaitable[None]] | None = None
_enabled_checker: EnabledChecker | None = None


def _enabled() -> bool:
    if _enabled_checker is None:
        return True
    try:
        return bool(_enabled_checker())
    except Exception:
        return True


def _fire_original(event_type: str, event_data: Any, session_id: Optional[str]) -> None:
    original = _original_fire_callback
    if original is None:
        return
    try:
        original(event_type, event_data, session_id)
    except Exception as exc:  # noqa: BLE001 - callback plumbing must not explode
        logger.debug("Original stream_event callback failed: %s", exc)


def _coalesced_fire_callback(
    event_type: str,
    event_data: Any,
    session_id: Optional[str],
) -> None:
    """Queue a stream-event callback for batched delivery.

    When runtime-disabled, this delegates to the exact original core callback so
    ``/set subagent_panel off`` really behaves like vanilla Mist.
    """
    global _drain_scheduled, _last_drain_time

    if not _enabled():
        _fire_original(event_type, event_data, session_id)
        return

    _pending_events.append((event_type, event_data, session_id))
    if _drain_scheduled:
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        clear_pending()
        return

    now = time.monotonic()
    elapsed = now - _last_drain_time
    _drain_scheduled = True
    if elapsed >= COALESCE_INTERVAL_S:
        loop.call_soon(_drain_pending_task, loop)
    else:
        loop.call_later(COALESCE_INTERVAL_S - elapsed, _drain_pending_task, loop)


def _drain_pending_task(loop: asyncio.AbstractEventLoop) -> None:
    """Drain pending events as one scheduled asyncio task."""
    global _drain_scheduled, _last_drain_time

    _drain_scheduled = False
    _last_drain_time = time.monotonic()
    if not _pending_events:
        return

    batch = list(_pending_events)
    _pending_events.clear()
    loop.create_task(_fire_batch(batch))


async def _fire_batch(batch: list[Event]) -> None:
    try:
        from code_puppy import callbacks
    except ImportError:
        logger.debug("Callbacks module not available for stream event")
        return

    for event_type, event_data, session_id in batch:
        try:
            await callbacks.on_stream_event(event_type, event_data, session_id)
        except Exception as exc:  # noqa: BLE001 - match core's fail-safe behavior
            logger.debug("Error in stream_event callback: %s", exc)


async def flush_pending_callbacks() -> None:
    """Synchronously drain any queued events.

    The stream-handler wrapper calls this in ``finally`` so terminal events do
    not sit behind the coalesce timer after a sub-agent stream completes.
    """
    global _drain_scheduled, _last_drain_time

    _drain_scheduled = False
    _last_drain_time = time.monotonic()
    if not _pending_events:
        return

    batch = list(_pending_events)
    _pending_events.clear()
    await _fire_batch(batch)


def clear_pending() -> None:
    """Drop pending events without firing them; used only for abnormal no-loop paths."""
    global _drain_scheduled

    _pending_events.clear()
    _drain_scheduled = False


def _make_stream_handler_wrapper(original: Callable[..., Awaitable[None]]):
    async def _wrapped(*args: Any, **kwargs: Any) -> None:
        try:
            await original(*args, **kwargs)
        finally:
            await flush_pending_callbacks()

    setattr(_wrapped, _MARKER, True)
    setattr(_wrapped, "_subagent_panel_original_stream_handler", original)
    return _wrapped


def install(enabled_checker: EnabledChecker | None = None) -> bool:
    """Install the coalescing monkeypatch idempotently.

    Returns ``True`` when installed/already installed, ``False`` if the core
    module is not importable. Import failure is okay during lightweight tests.
    """
    global _enabled_checker, _original_fire_callback, _original_stream_handler

    _enabled_checker = enabled_checker
    try:
        module = importlib.import_module("code_puppy.agents.subagent_stream_handler")
    except Exception as exc:  # noqa: BLE001 - plugin startup must be best-effort
        logger.debug("Could not import subagent_stream_handler: %s", exc)
        return False

    current_fire = getattr(module, "_fire_callback", None)
    if current_fire is None:
        return False
    if not getattr(current_fire, _MARKER, False):
        _original_fire_callback = current_fire
        setattr(_coalesced_fire_callback, _MARKER, True)
        setattr(
            _coalesced_fire_callback,
            "_subagent_panel_original_fire_callback",
            current_fire,
        )
        module._fire_callback = _coalesced_fire_callback
    elif _original_fire_callback is None:
        _original_fire_callback = getattr(
            current_fire, "_subagent_panel_original_fire_callback", None
        )

    current_handler = getattr(module, "subagent_stream_handler", None)
    if current_handler is None:
        return True
    if not getattr(current_handler, _MARKER, False):
        _original_stream_handler = current_handler
        module.subagent_stream_handler = _make_stream_handler_wrapper(current_handler)
    elif _original_stream_handler is None:
        _original_stream_handler = getattr(
            current_handler, "_subagent_panel_original_stream_handler", None
        )

    return True


def uninstall() -> None:
    """Restore original core callables when this plugin owns the patch."""
    global _original_fire_callback, _original_stream_handler, _enabled_checker

    try:
        module = importlib.import_module("code_puppy.agents.subagent_stream_handler")
    except Exception:
        clear_pending()
        return

    if getattr(getattr(module, "_fire_callback", None), _MARKER, False):
        if _original_fire_callback is not None:
            module._fire_callback = _original_fire_callback
    if getattr(getattr(module, "subagent_stream_handler", None), _MARKER, False):
        if _original_stream_handler is not None:
            module.subagent_stream_handler = _original_stream_handler

    clear_pending()
    _original_fire_callback = None
    _original_stream_handler = None
    _enabled_checker = None


__all__ = [
    "COALESCE_INTERVAL_S",
    "clear_pending",
    "flush_pending_callbacks",
    "install",
    "uninstall",
]
