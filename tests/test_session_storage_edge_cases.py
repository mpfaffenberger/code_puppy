"""Edge case tests for JSON-only session storage."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from code_puppy import session_storage


class TestSessionPathEdgeCases:
    def test_get_session_file_path_with_special_characters(self, tmp_path: Path):
        session_name = "session-with_special.chars"
        path = session_storage.get_session_file_path(tmp_path, session_name)

        assert session_name in str(path)
        assert path.suffix == ".json"


class TestSessionSaveEdgeCases:
    def test_save_session_with_empty_history(self, tmp_path: Path):
        metadata = session_storage.save_session(
            history=[],
            session_name="empty",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=lambda _msg: 0,
        )

        assert metadata.message_count == 0
        assert metadata.total_tokens == 0
        assert (tmp_path / "empty.json").exists()

    def test_save_session_with_large_messages(self, tmp_path: Path):
        large_content = "x" * 10000
        history = [{"role": "user", "content": large_content}]

        metadata = session_storage.save_session(
            history=history,
            session_name="large",
            base_dir=tmp_path,
            token_estimator=lambda msg: len(msg.get("content", "")),
        )

        assert metadata.message_count == 1
        assert metadata.total_tokens == 10000

    def test_save_and_load_complex_nested_objects(self, tmp_path: Path):
        history = [
            {
                "role": "user",
                "content": "hello",
                "metadata": {
                    "nested": {"deeply": {"structured": "data"}},
                    "list": [1, 2, 3, {"key": "value"}],
                },
            }
        ]

        session_storage.save_session(
            history=history, session_name="complex", base_dir=tmp_path
        )
        loaded = session_storage.load_session("complex", tmp_path)

        assert loaded[0]["metadata"]["nested"]["deeply"]["structured"] == "data"


class TestSessionLoadEdgeCases:
    def test_load_session_with_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            session_storage.load_session("missing", tmp_path)

    def test_load_session_with_invalid_json_raises(self, tmp_path: Path):
        (tmp_path / "corrupted.json").write_text("{not valid json", encoding="utf-8")

        with pytest.raises(Exception):
            session_storage.load_session("corrupted", tmp_path)


class TestSessionListingEdgeCases:
    def test_list_sessions_ignores_non_json_files(self, tmp_path: Path):
        (tmp_path / "session_1.json").touch()
        (tmp_path / "session_2.json").touch()
        (tmp_path / "random.txt").touch()
        (tmp_path / "session_2.bak").touch()

        result = session_storage.list_sessions(tmp_path)

        assert len(result) == 2
        assert "session_1" in result
        assert "session_2" in result

    def test_list_sessions_returns_sorted_names(self, tmp_path: Path):
        names = ["z_session", "a_session", "m_session"]
        for name in names:
            (tmp_path / f"{name}.json").touch()

        assert session_storage.list_sessions(tmp_path) == [
            "a_session",
            "m_session",
            "z_session",
        ]


class TestSessionCleanupEdgeCases:
    def test_cleanup_sessions_respects_max_limit(self, tmp_path: Path):
        for i in range(10):
            session_path = tmp_path / f"session_{i:02d}.json"
            session_path.touch()
            os.utime(session_path, (i, i))

        removed = session_storage.cleanup_sessions(tmp_path, max_sessions=3)
        remaining = session_storage.list_sessions(tmp_path)

        assert len(removed) == 7
        assert len(remaining) == 3
