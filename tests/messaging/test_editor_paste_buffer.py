"""Large pastes accumulate without repeatedly copying the payload."""

from io import StringIO
from unittest.mock import Mock

import pytest

from code_puppy.messaging.editor_paste import PASTE_END, PasteBuffer
from code_puppy.messaging.line_editor import RunningLineEditor


@pytest.mark.parametrize("chunk_size", [1, 2, 5, 6, 7, 4096])
def test_large_unicode_paste_split_across_reads(chunk_size):
    payload = "🐶 café 日誌\r\n\x1b[201x not the closer\n" * 5000
    stream = payload + PASTE_END
    paste = PasteBuffer()
    paste.start()
    result = None
    for offset in range(0, len(stream), chunk_size):
        result = paste.feed(stream[offset : offset + chunk_size])
    assert result == payload
    assert not paste.active
    assert paste.abort() == ""


def test_append_only_storage_and_bounded_marker_tail():
    # Structural regression rather than a flaky wall-clock assertion: the
    # payload must never again be accumulated with string-attribute +=.
    paste = PasteBuffer()
    paste.start()
    for ch in "long paste\n" * 1000:
        paste.feed(ch)
        assert isinstance(paste._buf, StringIO)
        assert len(paste._tail) <= len(PASTE_END)
    assert paste.abort() == "long paste\n" * 1000


def test_abort_restart_empty_and_inactive_feed():
    paste = PasteBuffer()
    assert paste.feed("ignored") is None
    paste.start()
    paste.feed("unfinished\x1b[20")
    assert paste.abort() == "unfinished\x1b[20"
    paste.start()
    assert paste.feed(PASTE_END) == ""
    paste.start()
    paste.feed("discarded")
    paste.start()
    assert paste.feed("new" + PASTE_END) == "new"


def test_editor_inserts_once_without_completion_or_submit():
    bar, completion = Mock(), Mock()
    completion.is_open.return_value = False
    editor = RunningLineEditor(prompt_prefix="> ", bar=bar)
    editor._completion = completion
    payload = "pasted source code\r\n" * 10000
    editor.feed("\x1b[200~")
    bar.reset_mock()
    for offset in range(0, len(payload), 4096):
        editor.feed(payload[offset : offset + 4096])
    assert editor.buffer == ""
    bar.set_prompt_text.assert_not_called()
    editor.feed(PASTE_END)
    assert editor.buffer == payload.replace("\r\n", "\n")
    completion.on_edit.assert_not_called()
    bar.set_prompt_text.assert_called_once()
