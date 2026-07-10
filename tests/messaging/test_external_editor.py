"""Ctrl+X Ctrl+E: edit-and-return via $VISUAL/$EDITOR."""

import asyncio
import sys

import pytest

from code_puppy.messaging import chords, external_editor
from code_puppy.messaging.external_editor import (
    edit_text_blocking,
    make_external_edit_handler,
    resolve_editor_command,
)
from code_puppy.messaging.line_editor import RunningLineEditor

CTRL_X = "\x18"
CTRL_E = "\x05"


class FakeBar:
    def set_prompt_text(self, *a):
        pass


class FakeHistory:
    def up(self, _t):
        return None

    def down(self, _t):
        return None

    def reset(self):
        pass

    def record_submit(self, _t):
        pass


class FakeRSearch:
    active = False

    def cancel(self):
        pass


@pytest.fixture
def editor():
    return RunningLineEditor(
        prompt_prefix="> ",
        bar=FakeBar(),
        history=FakeHistory(),
        reverse_search=FakeRSearch(),
    )


@pytest.fixture(autouse=True)
def _clean_chords():
    chords.unregister_chord(CTRL_E)
    yield
    chords.unregister_chord(CTRL_E)


def bind_edit_chord(handler):
    """Bind Ctrl+X Ctrl+E the way run_ui does (chord registry)."""
    chords.register_chord(CTRL_E, handler, "Ctrl+E edit in $EDITOR")


# =========================================================================
# Chord handling in the editor
# =========================================================================


def test_ctrl_x_ctrl_e_invokes_handler(editor):
    calls = []
    bind_edit_chord(lambda: calls.append(1))
    editor.feed("hi")
    editor.feed(CTRL_X)
    editor.feed(CTRL_E)
    assert calls == [1]
    assert editor.buffer == "hi"  # chord itself never mutates the buffer


def test_ctrl_x_alone_is_inert(editor):
    editor.feed("ab")
    editor.feed(CTRL_X)
    assert editor.buffer == "ab"


def test_ctrl_x_then_other_key_drops_prefix_and_processes_key(editor):
    calls = []
    bind_edit_chord(lambda: calls.append(1))
    editor.feed(CTRL_X)
    editor.feed("a")
    assert editor.buffer == "a"
    assert calls == []
    # The prefix must not linger: a LATER Ctrl+E is plain end-of-line.
    editor.feed(CTRL_E)
    assert calls == []


def test_ctrl_e_without_prefix_is_end_of_line(editor):
    calls = []
    bind_edit_chord(lambda: calls.append(1))
    editor.feed("abc")
    editor.feed("\x01")  # Ctrl+A home
    assert editor.cursor == 0
    editor.feed(CTRL_E)
    assert editor.cursor == 3
    assert calls == []


def test_chord_without_handler_is_noop(editor):
    editor.feed("x")
    editor.feed(CTRL_X)
    editor.feed(CTRL_E)
    assert editor.buffer == "x"


def test_handler_exception_never_escapes_feed(editor):
    def boom():
        raise RuntimeError("editor exploded")

    bind_edit_chord(boom)
    editor.feed(CTRL_X)
    editor.feed(CTRL_E)
    editor.feed("k")
    assert editor.buffer == "k"


def test_clear_buffer_disarms_pending_chord(editor):
    calls = []
    bind_edit_chord(lambda: calls.append(1))
    editor.feed(CTRL_X)
    editor.clear_buffer()
    editor.feed(CTRL_E)  # plain end-of-line, not the chord
    assert calls == []


def test_replace_buffer_text(editor):
    closed = []

    class Engine:
        def is_open(self):
            return False

        def on_edit(self, *a):
            pass

        def close(self):
            closed.append(1)

        def set_suppressed(self, *_a):
            pass

    editor.attach_completion(Engine())
    editor.feed("old")
    editor.replace_buffer_text("brand new text")
    assert editor.buffer == "brand new text"
    assert editor.cursor == len("brand new text")
    assert closed  # programmatic replace closes any open completion


# =========================================================================
# resolve_editor_command
# =========================================================================


def test_visual_wins_over_editor(monkeypatch):
    monkeypatch.setenv("VISUAL", "vis-editor")
    monkeypatch.setenv("EDITOR", "plain-editor")
    assert resolve_editor_command() == ["vis-editor"]


def test_editor_used_when_visual_unset(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", "my-editor")
    assert resolve_editor_command() == ["my-editor"]


def test_editor_value_splits_arguments(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", "code --wait")
    assert resolve_editor_command() == ["code", "--wait"]


def test_fallback_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    argv = resolve_editor_command()
    assert argv  # notepad / nano / vi depending on platform
    assert argv[0] in ("notepad", "nano", "vi")


# =========================================================================
# edit_text_blocking (real subprocess round-trip)
# =========================================================================


def _fake_editor_argv(py_body: str) -> list:
    """An 'editor' that runs python code against the temp file path."""
    return [sys.executable, "-c", py_body]


UPPERCASER = (
    "import sys\n"
    "p = sys.argv[1]\n"
    "s = open(p, encoding='utf-8').read()\n"
    "open(p, 'w', encoding='utf-8').write(s.upper() + '\\n')\n"
)


def test_edit_round_trip_strips_single_trailing_newline(monkeypatch):
    monkeypatch.setattr(
        external_editor,
        "resolve_editor_command",
        lambda: _fake_editor_argv(UPPERCASER),
    )
    assert edit_text_blocking("fix the bug") == "FIX THE BUG"


def test_edit_preserves_intentional_blank_lines(monkeypatch):
    body = "import sys\nopen(sys.argv[1], 'w', encoding='utf-8').write('a\\n\\nb\\n')\n"
    monkeypatch.setattr(
        external_editor, "resolve_editor_command", lambda: _fake_editor_argv(body)
    )
    assert edit_text_blocking("ignored") == "a\n\nb"


def test_nonzero_exit_keeps_original(monkeypatch):
    monkeypatch.setattr(
        external_editor,
        "resolve_editor_command",
        lambda: _fake_editor_argv("import sys; sys.exit(3)"),
    )
    assert edit_text_blocking("precious") is None


def test_unlaunchable_editor_returns_none(monkeypatch):
    monkeypatch.setattr(
        external_editor,
        "resolve_editor_command",
        lambda: ["definitely-not-a-real-editor-woof"],
    )
    assert edit_text_blocking("precious") is None


# =========================================================================
# Async wiring (loop hop, like the Ctrl+V handler)
# =========================================================================


def _run_chord_scenario(editor, monkeypatch, edit_result):
    monkeypatch.setattr(
        external_editor, "_edit_with_suspended_ui", lambda _initial: edit_result
    )

    async def scenario():
        loop = asyncio.get_running_loop()
        bind_edit_chord(make_external_edit_handler(editor, lambda: loop))
        # Feed from an executor thread, like the real key listener.
        await loop.run_in_executor(None, editor.feed, CTRL_X + CTRL_E)
        await asyncio.sleep(0.2)

    asyncio.run(scenario())


def test_wiring_replaces_buffer_with_edited_text(editor, monkeypatch):
    editor.feed("draft")
    _run_chord_scenario(editor, monkeypatch, "polished prompt")
    assert editor.buffer == "polished prompt"


def test_wiring_keeps_buffer_on_failed_edit(editor, monkeypatch):
    editor.feed("draft")
    _run_chord_scenario(editor, monkeypatch, None)
    assert editor.buffer == "draft"


def test_handler_without_loop_is_noop(editor):
    bind_edit_chord(make_external_edit_handler(editor, lambda: None))
    editor.feed("safe")
    editor.feed(CTRL_X)
    editor.feed(CTRL_E)
    assert editor.buffer == "safe"
