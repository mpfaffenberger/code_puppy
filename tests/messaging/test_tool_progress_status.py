"""Streaming progress owns a separate status slot, never transcript output."""

from io import StringIO

from code_puppy.messaging.bottom_bar import BottomBar


def test_progress_preserves_other_slots_and_clears():
    bar = BottomBar(stream=StringIO())
    bar.set_status("context")
    bar.set_status_prefix("spinner ")
    bar.set_status_suffix(" queued")
    bar.set_tool_progress("read_file · ~42 tokens")
    assert bar._combined_status() == "spinner | context | read_file · ~42 tokens queued"
    bar.set_tool_progress("")
    assert bar._combined_status() == "spinner | context queued"


def test_progress_alone_controls_status_visibility():
    bar = BottomBar(stream=StringIO())
    assert not bar._status_visible()
    bar.set_tool_progress("grep · ~3 tokens")
    assert bar._status_visible()
    bar.set_tool_progress("")
    assert not bar._status_visible()
