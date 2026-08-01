from __future__ import annotations

import pytest

from code_puppy.plugins.computer_use.backend_types import ComputerUseError
from code_puppy.plugins.computer_use.geometry import CaptureGeometry, Rect
from code_puppy.plugins.computer_use.state import StateStore


def make_store():
    store = StateStore(max_age_seconds=120)
    state = store.create(
        application="Example",
        bundle_id="com.example.app",
        pid=1,
        window_id=2,
        window_title="Window",
        geometry=CaptureGeometry(Rect(-100, 50, 800, 600), 1600, 1200, 2),
        screenshot_path="/tmp/example.png",
        elements={7: object()},
    )
    return store, state


def test_retina_and_negative_display_coordinate_transform():
    geometry = CaptureGeometry(Rect(-100, 50, 800, 600), 1600, 1200, 2)
    assert geometry.screenshot_to_quartz(0, 0) == (-100, 50)
    assert geometry.screenshot_to_quartz(800, 600) == (300, 350)


def test_coordinate_transform_rejects_out_of_bounds():
    geometry = CaptureGeometry(Rect(0, 0, 800, 600), 1600, 1200, 2)
    with pytest.raises(ComputerUseError, match="outside"):
        geometry.screenshot_to_quartz(1600, 10)


def test_state_is_single_use_and_rejects_stale_revision():
    store, state = make_store()
    assert store.require(state.revision).window_id == 2
    store.require(state.revision, consume=True)
    with pytest.raises(ComputerUseError, match="changed after an action"):
        store.require(state.revision)
    with pytest.raises(ComputerUseError, match="Stale or unknown"):
        store.require("wrong")
