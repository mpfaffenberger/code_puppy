"""Security regression tests for session persistence (JSON-only, no default pickle)."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Callable, List
from unittest.mock import patch

import pytest

from code_puppy.session_storage import (
    cleanup_sessions,
    list_sessions,
    load_session,
    save_session,
)
from code_puppy.tools.agent_tools import (
    _load_session_history,
    _save_session_history,
)
from pydantic_ai.messages import ModelRequest, UserPromptPart


@pytest.fixture
def token_estimator() -> Callable[[object], int]:
    return lambda message: len(str(message))


class TestSessionJsonPersistence:
    """Main session storage uses JSON and rejects pickle by default."""

    def test_save_session_writes_json_schema(self, tmp_path: Path, token_estimator):
        history: List[str] = ["msg1", "msg2"]
        metadata = save_session(
            history=history,
            session_name="test",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=token_estimator,
        )
        assert metadata.pickle_path.exists()
        raw = json.loads(metadata.pickle_path.read_text())
        assert raw.get("schema") == "code_puppy.session.v1"
        assert raw.get("format") == "pydantic-ai-model-messages-json"
        assert raw.get("messages") == history

    def test_load_session_rejects_pickle_by_default(self, tmp_path: Path):
        pkl = tmp_path / "legacy.pkl"
        pkl.write_bytes(b"\x80\x04}.")
        with pytest.raises(FileNotFoundError):
            load_session("legacy", tmp_path)

    def test_list_sessions_ignores_pickle(self, tmp_path: Path, token_estimator):
        save_session(
            history=["a"],
            session_name="json_session",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=token_estimator,
        )
        (tmp_path / "old.pkl").write_bytes(b"\x80\x04}.")
        names = list_sessions(tmp_path)
        assert names == ["json_session"]

    def test_cleanup_sessions_removes_json_and_metadata(
        self, tmp_path: Path, token_estimator
    ):
        for name in ["first", "second"]:
            save_session(
                history=[name],
                session_name=name,
                base_dir=tmp_path,
                timestamp="2024-01-01T00:00:00",
                token_estimator=token_estimator,
            )
        removed = cleanup_sessions(tmp_path, max_sessions=1)
        assert removed == ["first"]
        assert not (tmp_path / "first.json").exists()
        assert not (tmp_path / "first_meta.json").exists()
        assert (tmp_path / "second.json").exists()

    def test_legacy_pickle_import_requires_explicit_flag(self, tmp_path: Path):
        pkl = tmp_path / "legacy.pkl"
        pkl.write_bytes(b"\x80\x04}.")

        with pytest.raises(FileNotFoundError):
            load_session("legacy", tmp_path, allow_legacy=False)

        with patch(
            "code_puppy.session_storage._unsafe_pickle_loads_for_explicit_legacy_migration_only",
            return_value=["legacy"],
        ) as mock_load:
            with warnings.catch_warnings():
                warnings.simplefilter("always")
                result = load_session("legacy", tmp_path, allow_legacy=True)
            mock_load.assert_called_once()
            assert result == ["legacy"]


class TestSubagentSessionJson:
    """Subagent sessions use JSON with atomic private writes."""

    def test_round_trip(self, tmp_path: Path):
        sessions_dir = tmp_path / "subagent_sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=sessions_dir,
        ):
            msg = ModelRequest(parts=[UserPromptPart(content="hello")])
            _save_session_history(
                session_id="test-session",
                message_history=[msg],
                agent_name="test-agent",
                initial_prompt="hi",
            )
            loaded = _load_session_history("test-session")
            assert len(loaded) == 1
            assert loaded[0].parts[0].content == "hello"

            # Verify JSON schema wrapper
            json_path = sessions_dir / "test-session.json"
            raw = json.loads(json_path.read_text())
            assert raw.get("schema") == "code_puppy.subagent.session.v1"
            assert raw.get("format") == "pydantic-ai-model-messages-json"
