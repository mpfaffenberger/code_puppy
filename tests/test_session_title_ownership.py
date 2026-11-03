"""User-owned session titles survive saves, merges, and title derivation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from code_puppy import session_storage
from code_puppy.command_line.session_browser_data import SessionEntry, ensure_titles
from code_puppy.session_storage import (
    TITLE_SOURCE_KEY,
    USER_TITLE_SOURCE,
    has_user_title,
    merge_sidecar,
    read_sidecar,
    save_session,
    set_user_title,
)

USER = {TITLE_SOURCE_KEY: USER_TITLE_SOURCE}
AUTO_UPDATE = {
    "title": "AI title",
    "subtitle": "ai sub",
    "tags": ["ai"],
    "ai_named_at": 9,
}


def _history(pairs: int = 1) -> list:
    messages = []
    for index in range(pairs):
        messages.append(ModelRequest(parts=[UserPromptPart(content=f"ask {index}")]))
        messages.append(ModelResponse(parts=[TextPart(content=f"answer {index}")]))
    return messages


def _save(base_dir: Path, pairs: int = 1):
    return save_session(
        history=_history(pairs),
        session_name="s",
        base_dir=base_dir,
        timestamp="2026-01-02T00:00:00",
        token_estimator=lambda _message: 1,
        auto_saved=True,
    )


def _write_sidecar(base_dir: Path, data) -> Path:
    path = base_dir / "s_meta.json"
    path.write_text(
        data if isinstance(data, str) else json.dumps(data), encoding="utf-8"
    )
    return path


def _sidecar(base_dir: Path) -> dict:
    return json.loads((base_dir / "s_meta.json").read_text(encoding="utf-8"))


class TestSaveSessionKeepsEnrichment:
    def test_preserves_enrichment_and_rebuilds_core_keys(self, tmp_path):
        enrichment = {
            "title": "Mine",
            "subtitle": "sub",
            "tags": ["a"],
            "ai_named_at": 4,
            **USER,
        }
        _write_sidecar(
            tmp_path,
            {**enrichment, "message_count": 1, "timestamp": "2000-01-01", "stale": 1},
        )
        metadata = _save(tmp_path, pairs=2)
        assert _sidecar(tmp_path) == {**metadata.as_serialisable(), **enrichment}

    @pytest.mark.parametrize(
        ("existing", "kept"),
        [
            ({"title": "derived", "subtitle": "derived"}, {}),
            ({"title": "t", "ai_named_at": 2}, {"title": "t", "ai_named_at": 2}),
            ({"title": "t", **USER}, {"title": "t", **USER}),
        ],
        ids=["browser-derived-rebuilt", "namer-kept", "user-kept"],
    )
    def test_only_owned_titles_are_carried_over(self, tmp_path, existing, kept):
        _write_sidecar(tmp_path, existing)
        metadata = _save(tmp_path)
        assert _sidecar(tmp_path) == {**metadata.as_serialisable(), **kept}

    @pytest.mark.parametrize(
        "contents",
        [None, "{broken", "[1, 2]", ""],
        ids=["missing", "corrupt", "list", "empty"],
    )
    def test_missing_or_unreadable_sidecar_is_rewritten_fresh(self, tmp_path, contents):
        if contents is not None:
            _write_sidecar(tmp_path, contents)
        metadata = _save(tmp_path)
        assert _sidecar(tmp_path) == metadata.as_serialisable()


class TestReadSidecar:
    @pytest.mark.parametrize("contents", [None, "{broken", "[1, 2]", "null", '"text"'])
    def test_missing_corrupt_or_non_object_reads_as_empty(self, tmp_path, contents):
        if contents is not None:
            _write_sidecar(tmp_path, contents)
        assert read_sidecar(tmp_path, "s") == {}

    @pytest.mark.parametrize(
        ("meta", "expected"),
        [
            ({}, False),
            (USER, True),
            ({TITLE_SOURCE_KEY: "auto"}, False),
            ({TITLE_SOURCE_KEY: None}, False),
        ],
    )
    def test_has_user_title(self, meta, expected):
        assert has_user_title(meta) is expected


class TestMergeSidecarOwnership:
    @pytest.mark.parametrize(
        ("current", "updates", "title", "source"),
        [
            pytest.param(
                {"title": "Mine", **USER},
                AUTO_UPDATE,
                "Mine",
                USER_TITLE_SOURCE,
                id="automatic-keeps-user-title",
            ),
            pytest.param(
                {"title": "Mine", **USER},
                {"title": "AI", TITLE_SOURCE_KEY: None},
                "Mine",
                USER_TITLE_SOURCE,
                id="automatic-cannot-unpin",
            ),
            pytest.param(
                {"title": "Mine", **USER},
                {"title": "Newer", **USER},
                "Newer",
                USER_TITLE_SOURCE,
                id="rename-replaces-rename",
            ),
            pytest.param(
                {"title": "Old"},
                AUTO_UPDATE,
                "AI title",
                None,
                id="unflagged-unchanged-behavior",
            ),
        ],
    )
    def test_title_ownership(self, tmp_path, current, updates, title, source):
        _write_sidecar(tmp_path, {"message_count": 2, **current})
        assert merge_sidecar(tmp_path, "s", updates) is True
        sidecar = _sidecar(tmp_path)
        assert (
            sidecar["title"],
            sidecar.get(TITLE_SOURCE_KEY),
            sidecar["message_count"],
        ) == (title, source, 2)

    def test_non_title_enrichment_still_merges_over_user_title(self, tmp_path):
        _write_sidecar(tmp_path, {"title": "Mine", **USER})
        assert merge_sidecar(tmp_path, "s", AUTO_UPDATE) is True
        assert _sidecar(tmp_path) == {
            "title": "Mine",
            **USER,
            "subtitle": "ai sub",
            "tags": ["ai"],
            "ai_named_at": 9,
        }

    @pytest.mark.parametrize("contents", ["{broken", "[1, 2]", ""])
    def test_unreadable_sidecar_fails_closed(self, tmp_path, contents):
        path = _write_sidecar(tmp_path, contents)
        assert merge_sidecar(tmp_path, "s", AUTO_UPDATE) is False
        assert set_user_title(tmp_path, "s", "Mine") is False
        assert path.read_text(encoding="utf-8") == contents

    def test_missing_sidecar_is_created(self, tmp_path):
        assert merge_sidecar(tmp_path, "s", {"title": "T"}) is True
        assert _sidecar(tmp_path) == {"title": "T"}

    def test_empty_object_sidecar_is_valid_not_corrupt(self, tmp_path):
        _write_sidecar(tmp_path, {})
        assert set_user_title(tmp_path, "s", "Mine") is True
        assert _sidecar(tmp_path) == {"title": "Mine", **USER}

    def test_stale_automatic_write_after_rename_keeps_user_title(self, tmp_path):
        # Namer race at the core layer: rename lands, then an in-flight writer commits.
        _save(tmp_path)
        assert set_user_title(tmp_path, "s", "Mine") is True
        merge_sidecar(tmp_path, "s", AUTO_UPDATE)
        _save(tmp_path, pairs=2)
        sidecar = _sidecar(tmp_path)
        assert (
            sidecar["title"],
            has_user_title(sidecar),
            sidecar["message_count"],
        ) == ("Mine", True, 4)


@pytest.mark.parametrize(
    "write",
    [
        lambda d: _save(d),
        lambda d: merge_sidecar(d, "s", {"tags": []}),
        lambda d: set_user_title(d, "s", "T"),
    ],
    ids=["save_session", "merge_sidecar", "set_user_title"],
)
def test_sidecar_writes_hold_the_sidecar_lock(tmp_path, write):
    seen = []
    real_write = session_storage._write_json_atomically

    def spy(path, data):
        if path.name.endswith("_meta.json"):
            seen.append(session_storage._SIDECAR_LOCK.locked())
        real_write(path, data)

    with patch.object(session_storage, "_write_json_atomically", spy):
        write(tmp_path)
    assert seen == [True]


@pytest.mark.parametrize("title", ["Mine", ""])
def test_ensure_titles_never_derives_over_user_title(tmp_path, title):
    path = _write_sidecar(tmp_path, {"title": title, **USER})
    before = path.read_bytes()
    entry = SessionEntry.from_pair("s", {"title": title, **USER})
    with patch(
        "code_puppy.command_line.session_browser_data.load_session",
        side_effect=AssertionError("derived"),
    ):
        assert ensure_titles(tmp_path, entry) is False
    assert entry.meta["title"] == title
    assert path.read_bytes() == before


LOG_ERROR = "code_puppy.error_logging.log_error"
_real_open = Path.open


def _deny_sidecar_read(self, mode="r", *args, **kwargs):
    if self.name.endswith("_meta.json") and "r" in mode:
        raise PermissionError("denied")
    return _real_open(self, mode, *args, **kwargs)


class TestStorageErrorLogging:
    def test_unreadable_owned_sidecar_survives_autosave(self, tmp_path):
        path = _write_sidecar(tmp_path, {"title": "Secret title", **USER})
        before = path.read_bytes()
        with (
            patch.object(Path, "open", _deny_sidecar_read),
            patch(LOG_ERROR) as log_error,
        ):
            metadata = _save(tmp_path)
        assert path.read_bytes() == before
        assert "Secret title" not in str(log_error.call_args)
        assert _sidecar(tmp_path)[TITLE_SOURCE_KEY] == USER_TITLE_SOURCE
        assert log_error.call_count == 1
        assert metadata.session_name == "s"
        assert metadata.json_path.exists()

    def test_failed_write_logs_once_and_releases_lock(self, tmp_path):
        with (
            patch.object(
                session_storage, "_write_json_atomically", side_effect=OSError("disk")
            ),
            patch(LOG_ERROR) as log_error,
        ):
            assert set_user_title(tmp_path, "s", "Secret title") is False
        assert log_error.call_count == 1
        assert "Secret title" not in str(log_error.call_args)
        assert session_storage._SIDECAR_LOCK.acquire(blocking=False)
        session_storage._SIDECAR_LOCK.release()
        assert set_user_title(tmp_path, "s", "Mine") is True

    def test_read_sidecar_logs_unexpected_error_once(self, tmp_path):
        _write_sidecar(tmp_path, {"title": "Mine", **USER})
        with (
            patch.object(Path, "open", _deny_sidecar_read),
            patch(LOG_ERROR) as log_error,
        ):
            assert read_sidecar(tmp_path, "s") == {}
        assert log_error.call_count == 1

    @pytest.mark.parametrize("contents", [None, "{broken", "[1, 2]"])
    def test_expected_conditions_are_not_logged(self, tmp_path, contents):
        if contents is not None:
            _write_sidecar(tmp_path, contents)
        with patch(LOG_ERROR) as log_error:
            merge_sidecar(tmp_path, "s", {"tags": []})
            read_sidecar(tmp_path, "s")
            _save(tmp_path)
        assert log_error.call_count == 0
        assert _sidecar(tmp_path)["message_count"] == 2

    def test_failing_logger_does_not_change_results(self, tmp_path):
        with (
            patch(LOG_ERROR, side_effect=RuntimeError("logger down")),
            patch.object(
                session_storage, "_write_json_atomically", side_effect=OSError("disk")
            ),
        ):
            assert set_user_title(tmp_path, "s", "Mine") is False
        _write_sidecar(tmp_path, {"title": "Mine", **USER})
        with (
            patch(LOG_ERROR, side_effect=RuntimeError("logger down")),
            patch.object(Path, "open", _deny_sidecar_read),
        ):
            assert _save(tmp_path).session_name == "s"
