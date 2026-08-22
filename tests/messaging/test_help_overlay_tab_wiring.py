"""Tab-on-empty-buffer wiring for the help overlay (PUP-352).

Covers the raw-terminal editor path (``RunningLineEditor``). The
prompt_toolkit fallback path's equivalent branch is covered in
``tests/test_prompt_toolkit_completion.py``.
"""

from code_puppy.messaging.line_editor import RunningLineEditor


class FakeBar:
    def set_prompt_text(self, *a):
        pass


class FakeCompletion:
    def __init__(self):
        self.calls = []

    def on_tab(self, buffer, cursor):
        self.calls.append((buffer, cursor))


def make_editor():
    editor = RunningLineEditor(bar=FakeBar())
    completion = FakeCompletion()
    editor.attach_completion(completion)
    return editor, completion


def test_tab_on_empty_buffer_invokes_help_handler_not_completion():
    editor, completion = make_editor()
    handler_calls = []
    editor.set_help_overlay_handler(lambda: handler_calls.append(1))

    editor.feed("\t")

    assert handler_calls == [1]
    assert completion.calls == []


def test_tab_on_nonempty_buffer_invokes_completion_not_help_handler():
    editor, completion = make_editor()
    handler_calls = []
    editor.set_help_overlay_handler(lambda: handler_calls.append(1))
    editor.feed("hello")

    editor.feed("\t")

    assert handler_calls == []
    assert completion.calls == [("hello", 5)]


def test_tab_on_empty_buffer_without_handler_falls_back_to_completion():
    """No handler installed (e.g. headless/test contexts) -- Tab on an
    empty buffer must never crash, and should behave exactly as before
    this feature: hand off to completion."""
    editor, completion = make_editor()

    editor.feed("\t")

    assert completion.calls == [("", 0)]


def test_tab_on_whitespace_only_buffer_invokes_completion_not_help_handler():
    """A lone space is a non-empty buffer -- must not trigger the overlay
    (only a truly empty buffer does)."""
    editor, completion = make_editor()
    handler_calls = []
    editor.set_help_overlay_handler(lambda: handler_calls.append(1))
    editor.feed(" ")

    editor.feed("\t")

    assert handler_calls == []
    assert completion.calls == [(" ", 1)]


def test_set_help_overlay_handler_can_be_cleared():
    editor, _completion = make_editor()
    calls = []
    editor.set_help_overlay_handler(lambda: calls.append(1))
    editor.set_help_overlay_handler(None)

    editor.feed("\t")

    assert calls == []
