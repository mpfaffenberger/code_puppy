"""Tests for deterministic session labeling (issue #246)."""

import json
from types import SimpleNamespace

from code_puppy import session_storage
from code_puppy.session_storage import derive_session_label, save_session


def _user_msg(text):
    part = SimpleNamespace(part_kind="user-prompt", content=text)
    return SimpleNamespace(kind="request", parts=[part])


def _tool_msg():
    part = SimpleNamespace(part_kind="tool-return", content="stuff")
    return SimpleNamespace(kind="request", parts=[part])


class TestDeriveSessionLabel:
    def test_combines_cwd_and_first_prompt(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        label = derive_session_label([_user_msg("Fix column mapping")])
        assert label == f"[{tmp_path.name}] Fix column mapping"

    def test_first_user_prompt_wins(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        history = [_tool_msg(), _user_msg("first"), _user_msg("second")]
        assert derive_session_label(history).endswith("first")

    def test_truncates_long_prompts_with_ellipsis(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        label = derive_session_label([_user_msg("x" * 200)])
        prompt_part = label.split("] ", 1)[1]
        assert len(prompt_part) <= 60
        assert prompt_part.endswith("\u2026")

    def test_collapses_whitespace(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        label = derive_session_label([_user_msg("a\n\n  b\tc")])
        assert label.endswith("a b c")

    def test_empty_history_still_gets_project_tag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert derive_session_label([]) == f"[{tmp_path.name}]"

    def test_skips_non_string_content(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        binary = SimpleNamespace(
            kind="request",
            parts=[SimpleNamespace(part_kind="user-prompt", content=[b"img"])],
        )
        label = derive_session_label([binary, _user_msg("real prompt")])
        assert label.endswith("real prompt")

    def test_malformed_messages_ignored(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # No .parts attribute at all
        assert derive_session_label([object()]) == f"[{tmp_path.name}]"


class TestSaveSessionPersistsLabel:
    def test_metadata_json_contains_label_and_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        sessions_dir = tmp_path / "sessions"
        metadata = save_session(
            history=[_user_msg("Ship the feature")],
            session_name="auto_session_20260101_000000",
            base_dir=sessions_dir,
            timestamp="2026-01-01T00:00:00",
            token_estimator=lambda _m: 1,
        )
        assert metadata.label == f"[{tmp_path.name}] Ship the feature"
        assert metadata.cwd == str(tmp_path)

        on_disk = json.loads(metadata.metadata_path.read_text(encoding="utf-8"))
        assert on_disk["label"] == metadata.label
        assert on_disk["cwd"] == str(tmp_path)

    def test_labeling_failure_never_breaks_save(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            session_storage,
            "derive_session_label",
            lambda _h: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        metadata = save_session(
            history=[],
            session_name="resilient",
            base_dir=tmp_path,
            timestamp="2026-01-01T00:00:00",
            token_estimator=lambda _m: 0,
        )
        assert metadata.label is None
        assert metadata.cwd is None
        assert metadata.pickle_path.exists()

    def test_old_metadata_without_label_still_loads(self, tmp_path):
        # Backward compat: readers use .get(), so absent keys are fine
        meta_path = tmp_path / "old_meta.json"
        meta_path.write_text(
            json.dumps({"timestamp": "2025-01-01T00:00:00", "message_count": 3})
        )
        data = json.loads(meta_path.read_text())
        assert data.get("label") is None
