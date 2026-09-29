"""Typing must invalidate acceptance without flashing unchanged popup rows."""

import io
from unittest.mock import Mock

from code_puppy.messaging.bottom_bar import BottomBar
from tests.messaging.test_editor_completion import make_engine, settle


async def test_edit_keeps_popup_visible_but_not_acceptable():
    editor, engine = make_engine(["/help"])
    editor.feed("/h")
    await settle()
    rows = engine.popup_rows()
    repaint = Mock()
    engine._repaint = repaint

    editor.feed("e")
    assert engine.popup_rows() == rows
    repaint.assert_not_called()
    assert not engine.accept()
    assert editor.buffer == "/he"

    await settle()
    assert engine.popup_rows() == rows
    assert engine.accept()
    assert editor.buffer == "/help"


async def test_no_matches_eventually_clears_previous_popup():
    editor, engine = make_engine(["/help"])
    editor.feed("/h")
    await settle()
    editor.feed("z")
    assert not engine.accept()
    await settle()
    assert engine.popup_rows() == ([], -1)


def test_unchanged_popup_does_not_invoke_painter():
    bar = BottomBar(stream=io.StringIO(), get_size=lambda: (80, 24))
    bar._sync_reserved = Mock()
    bar.set_popup_lines([" /help", " /history"], 0)
    bar._sync_reserved.reset_mock()
    for _ in range(10):
        bar.set_popup_lines([" /help", " /history"], 0)
    bar._sync_reserved.assert_not_called()

    bar.set_popup_lines([" /help", " /history"], 1)
    bar._sync_reserved.assert_called_once()
    bar._sync_reserved.reset_mock()
    bar.set_popup_lines([" /help"], 0)
    bar._sync_reserved.assert_called_once()
