from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, List

import pytest

from code_puppy.session_storage import (
    cleanup_sessions,
    is_pinned,
    list_sessions,
    load_pins,
    load_session,
    save_pins,
    save_session,
    toggle_pin,
)


@pytest.fixture()
def history() -> List[str]:
    return ["one", "two", "three"]


@pytest.fixture()
def token_estimator() -> Callable[[object], int]:
    return lambda message: len(str(message))


def test_save_and_load_session(tmp_path: Path, history: List[str], token_estimator):
    session_name = "demo_session"
    timestamp = "2024-01-01T00:00:00"
    metadata = save_session(
        history=history,
        session_name=session_name,
        base_dir=tmp_path,
        timestamp=timestamp,
        token_estimator=token_estimator,
    )

    assert metadata.session_name == session_name
    assert metadata.message_count == len(history)
    assert metadata.total_tokens == sum(token_estimator(m) for m in history)
    assert metadata.pickle_path.exists()
    assert metadata.metadata_path.exists()

    with metadata.metadata_path.open() as meta_file:
        stored = json.load(meta_file)
    assert stored["session_name"] == session_name
    assert stored["auto_saved"] is False

    loaded_history = load_session(session_name, tmp_path)
    assert loaded_history == history


def test_list_sessions(tmp_path: Path, history: List[str], token_estimator):
    names = ["beta", "alpha", "gamma"]
    for name in names:
        save_session(
            history=history,
            session_name=name,
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=token_estimator,
        )

    assert list_sessions(tmp_path) == sorted(names)


def test_cleanup_sessions(tmp_path: Path, history: List[str], token_estimator):
    session_names = ["session_earliest", "session_middle", "session_latest"]
    for index, name in enumerate(session_names):
        metadata = save_session(
            history=history,
            session_name=name,
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=token_estimator,
        )
        os.utime(metadata.pickle_path, (0, index))

    removed = cleanup_sessions(tmp_path, 2)
    assert removed == ["session_earliest"]
    remaining = list_sessions(tmp_path)
    assert sorted(remaining) == sorted(["session_middle", "session_latest"])


def test_load_pins_empty_when_no_file(tmp_path: Path):
    assert load_pins(tmp_path) == set()


def test_toggle_pin_round_trip(tmp_path: Path, history: List[str], token_estimator):
    # toggle_pin only pins sessions that actually exist on disk.
    save_session(
        history=history,
        session_name="sess",
        base_dir=tmp_path,
        timestamp="2024-01-01T00:00:00",
        token_estimator=token_estimator,
    )

    assert is_pinned(tmp_path, "sess") is False

    # First toggle pins it.
    assert toggle_pin(tmp_path, "sess") is True
    assert is_pinned(tmp_path, "sess") is True
    assert load_pins(tmp_path) == {"sess"}

    # Second toggle unpins it.
    assert toggle_pin(tmp_path, "sess") is False
    assert is_pinned(tmp_path, "sess") is False
    assert load_pins(tmp_path) == set()


def test_toggle_pin_refuses_missing_session(tmp_path: Path):
    # Pinning a session that doesn't exist is a no-op (no ghost pins).
    assert toggle_pin(tmp_path, "does_not_exist") is False
    assert load_pins(tmp_path) == set()


def test_toggle_pin_prunes_stale_pins(
    tmp_path: Path, history: List[str], token_estimator
):
    # A pin left over for a now-deleted session gets pruned on next toggle.
    save_session(
        history=history,
        session_name="real",
        base_dir=tmp_path,
        timestamp="2024-01-01T00:00:00",
        token_estimator=token_estimator,
    )
    # Seed the registry with a ghost entry directly.
    save_pins(tmp_path, {"ghost", "real"})

    # Toggling the real session prunes the ghost in the same write.
    toggle_pin(tmp_path, "real")  # was pinned -> now unpinned
    assert load_pins(tmp_path) == set()


def test_save_and_load_pins(tmp_path: Path):
    save_pins(tmp_path, {"a", "b", "c"})
    assert load_pins(tmp_path) == {"a", "b", "c"}


def test_load_pins_handles_corrupt_file(tmp_path: Path):
    from code_puppy.session_storage import get_pins_path

    get_pins_path(tmp_path).write_text("not valid json{{", encoding="utf-8")
    assert load_pins(tmp_path) == set()


def test_cleanup_sessions_protects_pinned(
    tmp_path: Path, history: List[str], token_estimator
):
    session_names = ["session_earliest", "session_middle", "session_latest"]
    for index, name in enumerate(session_names):
        metadata = save_session(
            history=history,
            session_name=name,
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=token_estimator,
        )
        os.utime(metadata.pickle_path, (0, index))

    # Pin the oldest session - it must survive cleanup.
    toggle_pin(tmp_path, "session_earliest")

    removed = cleanup_sessions(tmp_path, 2)
    assert "session_earliest" not in removed
    remaining = list_sessions(tmp_path)
    assert "session_earliest" in remaining
