"""Deterministic UI settling based on accessibility-state stability."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable


def _fingerprint(snapshot: dict[str, Any]) -> str:
    normalized = [
        {
            key: node.get(key)
            for key in (
                "role",
                "title",
                "description",
                "value",
                "enabled",
                "focused",
                "actions",
            )
        }
        for node in snapshot.get("nodes", [])
    ]
    encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def wait_for_ui_settle(
    snapshotter: Callable[[str, int], dict[str, Any]],
    app_name: str,
    timeout: float = 3.0,
    interval: float = 0.1,
    stable_observations: int = 3,
) -> dict[str, Any]:
    """Return after the focused accessibility state repeats consecutively."""
    deadline = time.monotonic() + max(0.1, timeout)
    previous = None
    stable = 0
    observations = 0
    while time.monotonic() < deadline:
        snapshot = snapshotter(app_name, 120)
        observations += 1
        fingerprint = _fingerprint(snapshot)
        if fingerprint == previous:
            stable += 1
            if stable >= stable_observations:
                return {
                    "settled": True,
                    "observations": observations,
                    "fingerprint": fingerprint,
                }
        else:
            previous = fingerprint
            stable = 0
        time.sleep(max(0.01, interval))
    return {
        "settled": False,
        "observations": observations,
        "fingerprint": previous,
        "reason": "timeout",
    }
