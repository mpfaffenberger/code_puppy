"""Tests for the ``banner_notice`` observation phase.

The phase is an extension point for frontends (ACP) that forward plugin notices.
These tests pin the properties a subscriber depends on: the wire dict arrives
unchanged, one misbehaving subscriber cannot silence the others, and the sync
dispatch is safe to call from inside a running event loop.
"""

from __future__ import annotations

import asyncio
from typing import get_args

import pytest

from code_puppy import callbacks


@pytest.fixture
def isolated_phase():
    """Clear the phase's subscribers for one test and restore them afterwards."""
    original = list(callbacks._callbacks.get("banner_notice", []))
    callbacks._callbacks["banner_notice"] = []
    yield
    callbacks._callbacks["banner_notice"] = original


def test_phase_is_declared_in_literal_and_registry() -> None:
    assert "banner_notice" in get_args(callbacks.PhaseType)
    assert "banner_notice" in callbacks._callbacks


def test_subscriber_receives_the_wire_dict_unchanged(isolated_phase) -> None:
    seen: list[dict] = []
    callbacks.register_callback("banner_notice", seen.append)
    banner = {"v": 1, "event": "notice", "name": "plugin.done", "label": "DONE"}

    callbacks.on_banner_notice(banner)

    assert seen == [banner]
    assert seen[0] is banner


def test_raising_subscriber_is_isolated(isolated_phase) -> None:
    seen: list[dict] = []

    def broken(banner: dict) -> None:
        raise RuntimeError("subscriber exploded")

    callbacks.register_callback("banner_notice", broken)
    callbacks.register_callback("banner_notice", seen.append)
    banner = {"v": 1, "event": "notice"}

    callbacks.on_banner_notice(banner)

    assert seen == [banner]


def test_sync_dispatch_inside_running_loop_does_not_raise(isolated_phase) -> None:
    seen: list[dict] = []
    callbacks.register_callback("banner_notice", seen.append)
    banner = {"v": 1, "event": "notice"}

    async def emit_from_async_code() -> None:
        callbacks.on_banner_notice(banner)

    asyncio.run(emit_from_async_code())

    assert seen == [banner]


def test_no_subscriber_returns_empty_list(isolated_phase) -> None:
    assert callbacks.on_banner_notice({"v": 1, "event": "notice"}) == []
