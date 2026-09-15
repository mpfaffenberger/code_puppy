from __future__ import annotations

from code_puppy_core_plugins.computer_use.settle import wait_for_ui_settle


def test_wait_for_ui_settle_requires_repeated_fingerprint():
    calls = 0

    def snapshotter(app_name, max_nodes):
        nonlocal calls
        assert app_name == "Example"
        assert max_nodes == 120
        calls += 1
        value = "moving" if calls == 1 else "stable"
        return {"nodes": [{"role": "AXTextField", "value": value}]}

    result = wait_for_ui_settle(
        snapshotter,
        "Example",
        timeout=1,
        interval=0.001,
        stable_observations=2,
    )
    assert result["settled"] is True
    assert result["observations"] == 4
