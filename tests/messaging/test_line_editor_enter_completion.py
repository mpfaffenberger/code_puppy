"""Enter-key behavior when the completion menu is open (persistent editor).

Regression: typing a whole slash command (e.g. ``/help``) leaves the menu
open with the exact match auto-selected. Accepting it is a no-op, and the
editor used to swallow that first Enter (accept-and-close), forcing a
SECOND Enter to submit. Enter on a no-op completion must submit.
"""

from code_puppy.messaging.line_editor import RunningLineEditor


class _FakeCompletion:
    """Minimal stand-in for CompletionEngine: open menu + scripted accept."""

    def __init__(self, on_accept):
        self._open = True
        self._on_accept = on_accept  # called by accept(); mutates buffer or not

    def is_open(self):
        return self._open

    def on_edit(self, text, cursor):  # stay open while typing
        pass

    def on_tab(self, text, cursor):
        return True

    def move(self, delta):
        pass

    def set_suppressed(self, suppressed):
        if suppressed:
            self._open = False

    def close(self):
        self._open = False

    def accept(self):
        self._on_accept()
        self._open = False
        return True


def _make_editor():
    bar = type("B", (), {"set_prompt_text": staticmethod(lambda *a: None)})()
    return RunningLineEditor(bar=bar)


def test_enter_on_noop_completion_submits_immediately():
    editor = _make_editor()
    submitted = []
    editor.add_submit_listener(lambda text, mode: submitted.append(text))
    # accept() is a no-op (whole word already typed) -> buffer unchanged.
    editor.attach_completion(_FakeCompletion(on_accept=lambda: None))

    for ch in "/help":
        editor.feed(ch)
    editor.feed("\r")  # ONE enter

    assert submitted == ["/help"]  # submitted on the first Enter, no double-tap


def test_enter_on_real_completion_picks_then_submits():
    editor = _make_editor()
    submitted = []
    editor.add_submit_listener(lambda text, mode: submitted.append(text))

    # accept() applies a real change (partial -> full command).
    def _apply():
        editor.apply_completion(0, len(editor._buffer), "/model gpt-5")

    editor.attach_completion(_FakeCompletion(on_accept=_apply))

    for ch in "/mod":
        editor.feed(ch)
    editor.feed("\r")  # first Enter: picks the completion, does NOT submit
    assert submitted == []

    editor.feed("\r")  # second Enter: menu closed -> submits the picked text
    assert submitted == ["/model gpt-5"]
