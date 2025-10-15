from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, List

import pytest

from code_puppy.session_storage import (
    cleanup_sessions,
    list_sessions,
    load_session,
    save_session,
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
    assert metadata.session_title is None

    with metadata.metadata_path.open() as meta_file:
        stored = json.load(meta_file)
    assert stored["session_name"] == session_name
    assert stored["auto_saved"] is False
    assert "session_title" not in stored

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


def test_save_session_with_title(tmp_path: Path, history: List[str], token_estimator):
    session_name = "titled_session"
    timestamp = "2024-01-01T00:00:00"
    session_title = "Test Session Title"
    
    metadata = save_session(
        history=history,
        session_name=session_name,
        base_dir=tmp_path,
        timestamp=timestamp,
        token_estimator=token_estimator,
        session_title=session_title,
    )
    
    assert metadata.session_title == session_title
    
    with metadata.metadata_path.open() as meta_file:
        stored = json.load(meta_file)
    assert stored["session_title"] == session_title
    
    # Verify title persists when saving again without providing it
    metadata2 = save_session(
        history=history + ["four"],
        session_name=session_name,
        base_dir=tmp_path,
        timestamp="2024-01-01T01:00:00",
        token_estimator=token_estimator,
    )
    
    assert metadata2.session_title == session_title
    with metadata2.metadata_path.open() as meta_file:
        stored2 = json.load(meta_file)
    assert stored2["session_title"] == session_title
