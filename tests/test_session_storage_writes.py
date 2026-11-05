"""Session files survive concurrent writers; damaged ones fail loudly, intact."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from code_puppy.session_storage import load_session, save_session

# Raw controls, ANSI, backslash, line separator and non-BMP text: the writer
# must escape all of them so the file never holds a raw control byte.
TRICKY = "nul\x00 bel\x07 esc\x1b[31mred\x1b[0m tab\t lf\n cr\r back\\slash \u2028 \U0001f436"


def _history(text: str) -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content=text)]),
        ModelResponse(parts=[TextPart(content=f"echo: {text}")]),
    ]


def _save(base_dir: Path, history: list) -> None:
    save_session(
        history=history,
        session_name="s",
        base_dir=base_dir,
        timestamp="2026-01-01T00:00:00",
        token_estimator=lambda _message: 1,
    )


def test_writer_escapes_every_control_character(tmp_path):
    _save(tmp_path, _history(TRICKY))

    raw = (tmp_path / "s.json").read_bytes()
    assert raw.isascii()
    assert {byte for byte in raw if byte < 0x20} == {ord("\n")}
    assert load_session("s", tmp_path)[0].parts[0].content == TRICKY


@pytest.mark.parametrize("target", ["s.json", "s_meta.json"])
def test_stale_writer_on_legacy_temp_path_cannot_splice_session(tmp_path, target):
    # An older process mid-autosave of the same session still holds the
    # fixed ``<name>.tmp`` it was writing and flushes after our save lands.
    stale_tmp = (tmp_path / target).with_suffix(".tmp")
    with stale_tmp.open("w", encoding="utf-8") as stale_writer:
        _save(tmp_path, _history("kept " * 2000))
        stale_writer.write('{"format": 2, "messages": [{"stale": "')
        stale_writer.flush()

    assert load_session("s", tmp_path)[0].parts[0].content == "kept " * 2000
    meta = json.loads((tmp_path / "s_meta.json").read_text(encoding="utf-8"))
    assert meta["message_count"] == 2


def test_damaged_session_names_file_and_is_left_untouched(tmp_path):
    _save(tmp_path, _history("hello world"))
    session_file = tmp_path / "s.json"
    # External damage: a raw newline lands inside a string value.
    damaged = session_file.read_bytes().replace(b"hello world", b"hello\nworld")
    session_file.write_bytes(damaged)

    for _attempt in range(2):
        with pytest.raises(ValueError, match="Invalid control character") as err:
            load_session("s", tmp_path)
        assert str(session_file) in str(err.value)
        assert "hello" not in str(err.value)
    assert session_file.read_bytes() == damaged
