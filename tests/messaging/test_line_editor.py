"""Tests for code_puppy.messaging.line_editor - RunningLineEditor."""

import pytest

from code_puppy.messaging.line_editor import DEFAULT_ESC_TIMEOUT, RunningLineEditor

# =========================================================================
# Fakes
# =========================================================================


class FakeBar:
    """Records set_prompt_text calls (stand-in for the BottomBar)."""

    def __init__(self):
        self.paints = []

    def set_prompt_text(self, prefix, buffer, cursor_pos, prefix_sgrs=None):
        self.paints.append((prefix, buffer, cursor_pos))


class FakePauseController:
    """Records request_steer calls (stand-in for PauseController)."""

    def __init__(self):
        self.steers = []

    def request_steer(self, text, mode="now"):
        self.steers.append((text, mode))


class FakeHistory:
    """Inert history: no file I/O, records submits."""

    def __init__(self):
        self.submitted = []

    def up(self, _t):
        return None

    def down(self, _t):
        return None

    def reset(self):
        pass

    def record_submit(self, text):
        self.submitted.append(text)


class FakeRSearch:
    active = False

    def cancel(self):
        pass


class FakeClock:
    """Controllable monotonic clock for ESC-timeout tests."""

    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def bar():
    return FakeBar()


@pytest.fixture
def controller():
    return FakePauseController()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def editor(bar, controller, clock):
    return RunningLineEditor(
        prompt_prefix="> ",
        bar=bar,
        pause_controller=controller,
        now=clock,
        history=FakeHistory(),
        reverse_search=FakeRSearch(),
    )


def feed_all(editor, text):
    for ch in text:
        editor.feed(ch)


# =========================================================================
# Basic editing
# =========================================================================


def test_printable_chars_build_buffer(editor):
    feed_all(editor, "hello")
    assert editor.buffer == "hello"
    assert editor.cursor == 5


def test_every_edit_repaints(editor, bar):
    feed_all(editor, "ab")
    assert bar.paints == [("> ", "a", 1), ("> ", "ab", 2)]


def test_backspace_del_variant(editor):
    feed_all(editor, "abc")
    editor.feed("\x7f")
    assert editor.buffer == "ab"
    assert editor.cursor == 2


def test_backspace_bs_variant(editor):
    feed_all(editor, "abc")
    editor.feed("\x08")
    assert editor.buffer == "ab"


def test_backspace_on_empty_buffer_is_noop(editor, bar):
    editor.feed("\x7f")
    assert editor.buffer == ""
    assert bar.paints == []  # no-op edits don't repaint


def test_raw_ctrl_c_clears_buffer(editor):
    """Raw ^C (Windows+uvx: no SIGINT, byte reaches the editor) must
    behave like Ctrl+C-at-idle everywhere else: wipe the typed text."""
    feed_all(editor, "half-typed thought")
    editor.feed("\x03")
    assert editor.buffer == ""
    assert editor.cursor == 0


def test_raw_ctrl_c_on_empty_buffer_is_noop(editor):
    editor.feed("\x03")
    assert editor.buffer == ""
    assert editor.cursor == 0


def test_raw_ctrl_c_does_not_submit(editor, controller):
    feed_all(editor, "do not send this")
    editor.feed("\x03")
    assert controller.steers == []


def test_raw_ctrl_c_cancels_reverse_search(bar, controller, clock):
    class ActiveRSearch:
        def __init__(self):
            self.active = True
            self.cancelled = False

        def cancel(self):
            self.active = False
            self.cancelled = True

        def prompt_text(self):
            return "(reverse-i-search)`': "

    rsearch = ActiveRSearch()
    editor = RunningLineEditor(
        prompt_prefix="> ",
        bar=bar,
        pause_controller=controller,
        now=clock,
        history=FakeHistory(),
        reverse_search=rsearch,
    )
    editor.feed("\x03")
    assert rsearch.cancelled is True
    assert editor.buffer == ""


def test_ctrl_u_kills_line(editor):
    feed_all(editor, "kill me")
    editor.feed("\x15")
    assert editor.buffer == ""
    assert editor.cursor == 0


def test_unknown_control_chars_ignored(editor):
    feed_all(editor, "ok")
    editor.feed("\x01")  # Ctrl+A
    editor.feed("\x02")  # Ctrl+B
    assert editor.buffer == "ok"


def test_multichar_feed_processed_in_order(editor):
    editor.feed("abc")
    assert editor.buffer == "abc"


# =========================================================================
# Submit: Enter → mode="queue" (mid-turn injection is opt-in via /steer)
# =========================================================================


def test_enter_submits_mode_queue(editor, controller):
    feed_all(editor, "do the thing")
    editor.feed("\r")
    assert controller.steers == [("do the thing", "queue")]
    assert editor.buffer == ""
    assert editor.cursor == 0


def test_ctrl_j_inserts_newline_not_submit(editor, controller):
    """Phase B: \\n is Ctrl+J = newline insert (POSIX listener clears
    ICRNL so Enter arrives as \\r)."""
    feed_all(editor, "hi")
    editor.feed("\n")
    assert controller.steers == []
    assert editor.buffer == "hi\n"


def test_submit_repaints_cleared_prompt(editor, bar):
    feed_all(editor, "x")
    editor.feed("\r")
    assert bar.paints[-1] == ("> ", "", 0)


def test_empty_submit_is_ignored(editor, controller):
    editor.feed("\r")
    assert controller.steers == []
    assert editor.get_pending_command() is None


def test_whitespace_only_submit_is_ignored(editor, controller):
    feed_all(editor, "   ")
    editor.feed("\r")
    assert controller.steers == []


# =========================================================================
# Submit: Alt+Enter (ESC + Enter within timeout) → mode="queue"
# =========================================================================


def test_alt_enter_submits_mode_queue(editor, controller):
    feed_all(editor, "later please")
    editor.feed("\x1b")
    editor.feed("\r")  # within the 50ms window (fake clock frozen)
    assert controller.steers == [("later please", "queue")]


def test_slow_esc_then_enter_is_plain_enter(editor, controller, clock):
    feed_all(editor, "now actually")
    editor.feed("\x1b")
    clock.advance(DEFAULT_ESC_TIMEOUT * 2)  # ESC window expired
    editor.feed("\r")
    assert controller.steers == [("now actually", "queue")]


def test_check_timeout_clears_pending_esc(editor, controller, clock):
    feed_all(editor, "steer")
    editor.feed("\x1b")
    clock.advance(DEFAULT_ESC_TIMEOUT * 2)
    editor.check_timeout()
    editor.feed("\r")
    assert controller.steers == [("steer", "queue")]


def test_double_esc_keeps_second_pending(editor, controller):
    feed_all(editor, "q")
    editor.feed("\x1b")
    editor.feed("\x1b")
    editor.feed("\r")  # still within the second ESC's window
    assert controller.steers == [("q", "queue")]


def test_alt_other_key_is_swallowed(editor):
    feed_all(editor, "ab")
    editor.feed("\x1b")
    editor.feed("x")  # Alt+X — neither char reaches the buffer
    assert editor.buffer == "ab"


# =========================================================================
# Slash-command routing
# =========================================================================


def test_slash_command_goes_to_queue_not_controller(editor, controller):
    feed_all(editor, "/help")
    editor.feed("\r")
    assert controller.steers == []
    assert editor.get_pending_command() == "/help"
    assert editor.get_pending_command() is None


def test_slash_command_is_stripped(editor):
    feed_all(editor, "  /status  ")
    editor.feed("\r")
    assert editor.get_pending_command() == "/status"


def test_slash_commands_queue_in_order(editor):
    for cmd in ("/one", "/two"):
        feed_all(editor, cmd)
        editor.feed("\r")
    assert editor.get_pending_command() == "/one"
    assert editor.get_pending_command() == "/two"


# =========================================================================
# CSI / SS3 swallowing
# =========================================================================


def test_arrow_up_with_no_history_is_harmless(editor):
    feed_all(editor, "ab")
    feed_all(editor, "\x1b[A")  # up arrow -> history (empty) -> no-op
    assert editor.buffer == "ab"
    assert editor.cursor == 2


def test_multibyte_csi_is_swallowed(editor):
    feed_all(editor, "x")
    feed_all(editor, "\x1b[1;5C")  # Ctrl+Right
    assert editor.buffer == "x"


def test_ss3_up_with_no_history_is_harmless(editor):
    feed_all(editor, "y")
    feed_all(editor, "\x1bOA")  # SS3 up arrow (application cursor mode)
    assert editor.buffer == "y"


def test_typing_resumes_cleanly_after_csi(editor):
    feed_all(editor, "\x1b[B")
    feed_all(editor, "ok")
    assert editor.buffer == "ok"


# =========================================================================
# Submit listeners
# =========================================================================


def test_submit_listener_notified(editor):
    events = []
    editor.add_submit_listener(lambda text, mode: events.append((text, mode)))
    feed_all(editor, "ping")
    editor.feed("\r")
    assert events == [("ping", "queue")]


def test_submit_listener_sees_slash_commands(editor):
    events = []
    editor.add_submit_listener(lambda text, mode: events.append((text, mode)))
    feed_all(editor, "/cmd")
    editor.feed("\r")
    assert events == [("/cmd", "queue")]


def test_broken_listener_does_not_break_submit(editor, controller):
    def boom(text, mode):
        raise RuntimeError("bad listener")

    editor.add_submit_listener(boom)
    feed_all(editor, "resilient")
    editor.feed("\r")
    assert controller.steers == [("resilient", "queue")]


def test_remove_submit_listener(editor):
    events = []
    cb = lambda text, mode: events.append(text)  # noqa: E731
    editor.add_submit_listener(cb)
    editor.remove_submit_listener(cb)
    feed_all(editor, "silent")
    editor.feed("\r")
    assert events == []


# =========================================================================
# Repaint plumbing
# =========================================================================


def test_repaint_method_paints_current_state(editor, bar):
    feed_all(editor, "hi")
    bar.paints.clear()
    editor.repaint()
    assert bar.paints == [("> ", "hi", 2)]


# =========================================================================
# Submission feedback (transcript lines via emit_info)
# =========================================================================


@pytest.fixture
def emitted(monkeypatch):
    lines = []
    monkeypatch.setattr(
        "code_puppy.messaging.message_queue.emit_info",
        lambda text, **kwargs: lines.append(text),
    )
    return lines


def test_enter_submit_emits_queued_feedback(editor, emitted):
    # Enter queues by default now — queued steers get their ack at
    # submit time (there's no later confirmation for them).
    feed_all(editor, "fix the tests")
    editor.feed("\r")
    assert emitted == ["⏭ queued for next turn: fix the tests"]


def test_steer_command_emits_no_feedback(editor, emitted, controller):
    # /steer fast path stays silent at submit time — the steer history
    # processor emits the real "Injecting steer mid-turn" line when the
    # text actually reaches the model.
    feed_all(editor, "/steer fix the tests")
    editor.feed("\r")
    assert emitted == []
    assert controller.steers == [("fix the tests", "now")]
    assert editor.get_pending_command() is None  # never hits the drain


def test_bare_steer_command_emits_usage(editor, emitted, controller):
    feed_all(editor, "/steer")
    editor.feed("\r")
    assert emitted == ["Usage: /steer <message>"]
    assert controller.steers == []
    assert editor.get_pending_command() is None


def test_queue_submit_emits_queued_feedback(editor, emitted):
    feed_all(editor, "do this after")
    editor.feed("\x1b")
    editor.feed("\r")
    assert emitted == ["⏭ queued for next turn: do this after"]


def test_queue_feedback_preview_truncated_to_60_chars(editor, emitted):
    feed_all(editor, "x" * 100)
    editor.feed("\x1b")
    editor.feed("\r")
    assert emitted == [f"⏭ queued for next turn: {'x' * 60}"]


def test_slash_command_emits_no_feedback(editor, emitted):
    feed_all(editor, "/help")
    editor.feed("\r")
    assert emitted == []


def test_empty_submit_emits_no_feedback(editor, emitted):
    editor.feed("\r")
    assert emitted == []


def test_broken_controller_emits_no_feedback(bar, clock, emitted):
    class ExplodingController:
        def request_steer(self, text, mode="now"):
            raise RuntimeError("nope")

    editor = RunningLineEditor(
        bar=bar, pause_controller=ExplodingController(), now=clock
    )
    feed_all(editor, "hello")
    editor.feed("\r")
    assert emitted == []


def test_broken_bar_never_raises(controller, clock):
    class ExplodingBar:
        def set_prompt_text(self, *args):
            raise RuntimeError("no terminal for you")

    editor = RunningLineEditor(
        bar=ExplodingBar(), pause_controller=controller, now=clock
    )
    feed_all(editor, "still works")
    editor.feed("\r")
    assert controller.steers == [("still works", "queue")]


# =========================================================================
# Attachment display tags (editor_display wiring)
# =========================================================================


def test_image_path_paints_as_tag_but_buffer_keeps_path(editor, bar, tmp_path):
    """Classic parity: the prompt row shows [png image]; buffer keeps path."""
    png = tmp_path / "shot.png"
    png.write_bytes(b"\x89PNG fake")
    feed_all(editor, f"look at {png}")
    prefix, painted, cursor = bar.paints[-1]
    assert "[png image]" in painted
    assert str(png) not in painted
    assert cursor == len(painted)
    # The REAL buffer is untouched — submit-time resolution needs the path.
    assert editor.buffer == f"look at {png}"


def test_non_path_text_paints_verbatim(editor, bar):
    feed_all(editor, "just words")
    assert bar.paints[-1] == ("> ", "just words", 10)
