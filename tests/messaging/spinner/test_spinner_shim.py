"""Tests for the deprecated messaging.spinner compat shim.

The real spinner died in Phase 3 of the bottom-bar rewrite; the shim must
keep old imports working (no-ops) and forward context info to the bottom
bar's status line.
"""

import io

from code_puppy.messaging import bottom_bar as bottom_bar_mod
from code_puppy.messaging.spinner import (
    ConsoleSpinner,
    _active_spinners,
    clear_spinner_context,
    format_context_info,
    pause_all_spinners,
    register_spinner,
    resume_all_spinners,
    unregister_spinner,
    update_spinner_context,
)


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


# =========================================================================
# No-op surface
# =========================================================================


def test_pause_resume_are_noops():
    pause_all_spinners()
    resume_all_spinners()  # must not raise


def test_register_unregister_are_noops():
    sentinel = object()
    register_spinner(sentinel)
    assert _active_spinners == []  # nothing is tracked anymore
    unregister_spinner(sentinel)  # must not raise


def test_console_spinner_stub_is_inert_context_manager():
    with ConsoleSpinner(console="anything") as spinner:
        spinner.start()
        spinner.pause()
        spinner.resume()
        spinner.stop()
    assert spinner.console == "anything"


# =========================================================================
# Context forwarding → bottom bar status line
# =========================================================================


def test_update_spinner_context_forwards_to_bottom_bar_status():
    tty = FakeTTY()
    bar = bottom_bar_mod.BottomBar(stream=tty, get_size=lambda: (80, 24))
    bottom_bar_mod.reset_bottom_bar()
    bottom_bar_mod._bottom_bar = bar
    try:
        bar.start()
        update_spinner_context("Tokens: 1,000/10,000 (10.0% used)")
        assert "Tokens: 1,000/10,000 (10.0% used)" in tty.getvalue()
    finally:
        bottom_bar_mod.reset_bottom_bar()


def test_clear_spinner_context_clears_status():
    tty = FakeTTY()
    bar = bottom_bar_mod.BottomBar(stream=tty, get_size=lambda: (80, 24))
    bottom_bar_mod.reset_bottom_bar()
    bottom_bar_mod._bottom_bar = bar
    try:
        bar.start()
        update_spinner_context("something")
        clear_spinner_context()
        assert bar._status == ""
    finally:
        bottom_bar_mod.reset_bottom_bar()


def test_update_spinner_context_dropped_for_subagents(monkeypatch):
    """Sub-agent compaction must NOT stomp the main agent's status row."""
    tty = FakeTTY()
    bar = bottom_bar_mod.BottomBar(stream=tty, get_size=lambda: (80, 24))
    bottom_bar_mod.reset_bottom_bar()
    bottom_bar_mod._bottom_bar = bar
    monkeypatch.setattr("code_puppy.tools.subagent_context.is_subagent", lambda: True)
    try:
        bar.start()
        bar.set_status("main agent context")
        update_spinner_context("subagent context")
        assert bar._status == "main agent context"  # unchanged
    finally:
        bottom_bar_mod.reset_bottom_bar()


def test_update_spinner_context_never_raises(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.messaging.bottom_bar.get_bottom_bar",
        lambda: (_ for _ in ()).throw(RuntimeError("no bar")),
    )
    update_spinner_context("info")  # must not raise


# =========================================================================
# format_context_info (moved from SpinnerBase)
# =========================================================================


def test_format_context_info_normal():
    result = format_context_info(5000, 10000, 0.5)
    assert result == "5k/10k tokens (50%)"


def test_format_context_info_compact_counts():
    assert format_context_info(150_329, 500_000, 0.301) == ("150.3k/500k tokens (30%)")
    assert format_context_info(999, 1_500_000, 0.001) == "999/1.5M tokens (0%)"


def test_format_context_info_zero_or_negative_capacity():
    assert format_context_info(100, 0, 0.0) == ""
    assert format_context_info(100, -5, 0.0) == ""
