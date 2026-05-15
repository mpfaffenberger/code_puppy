"""Tests for shell-output silencing in RichConsoleRenderer during pause.

When the PauseController is paused (Ctrl+T steering), the bus renderer
must drop shell-related messages on the floor instead of letting them
trash the steering prompt. Non-shell messages render normally — buffering
those is the legacy ``SynchronousInteractiveRenderer``'s responsibility.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.messages import (
    MessageLevel,
    ShellLineMessage,
    ShellOutputMessage,
    ShellStartMessage,
    TextMessage,
)
from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)
from code_puppy.messaging.rich_renderer import RichConsoleRenderer


@pytest.fixture(autouse=True)
def _reset_pause_singleton():
    reset_pause_controller()
    yield
    reset_pause_controller()


@pytest.fixture
def buffer_io() -> io.StringIO:
    return io.StringIO()


@pytest.fixture
def renderer(buffer_io):
    """A RichConsoleRenderer wired to an in-memory console.

    We deliberately don't ``start()`` it — we want to drive ``_render_sync``
    directly to keep tests deterministic (no background thread races).
    """
    console = Console(file=buffer_io, force_terminal=False, width=200)
    return RichConsoleRenderer(MessageBus(), console=console)


# =============================================================================
# Helpers
# =============================================================================


def _text(content: str) -> TextMessage:
    return TextMessage(level=MessageLevel.INFO, text=content)


def _shell_start(cmd: str = "echo hi") -> ShellStartMessage:
    return ShellStartMessage(command=cmd, cwd="/tmp")


def _shell_line(line: str = "hello") -> ShellLineMessage:
    return ShellLineMessage(line=line, stream="stdout")


def _shell_output(stdout: str = "result") -> ShellOutputMessage:
    return ShellOutputMessage(
        command="echo hi",
        stdout=stdout,
        stderr="",
        exit_code=0,
        duration_seconds=0.1,
    )


# =============================================================================
# Paused: shell messages dropped, non-shell rendered
# =============================================================================


def test_shell_line_dropped_while_paused(renderer, buffer_io):
    get_pause_controller().pause()
    renderer._render_sync(_shell_line("should not appear"))
    assert "should not appear" not in buffer_io.getvalue()
    assert buffer_io.getvalue() == ""


def test_shell_start_dropped_while_paused(renderer, buffer_io):
    get_pause_controller().pause()
    renderer._render_sync(_shell_start("rm -rf /tmp/junk"))
    assert "rm -rf" not in buffer_io.getvalue()


def test_shell_output_dropped_while_paused(renderer, buffer_io):
    get_pause_controller().pause()
    renderer._render_sync(_shell_output("paused-stdout"))
    assert "paused-stdout" not in buffer_io.getvalue()


def test_non_shell_message_still_renders_while_paused(renderer, buffer_io):
    """Buffering non-shell messages during pause is the legacy renderer's
    concern; this renderer must NOT silently swallow them."""
    get_pause_controller().pause()
    renderer._render_sync(_text("important-info"))
    assert "important-info" in buffer_io.getvalue()


# =============================================================================
# Not paused: shell messages render as usual
# =============================================================================


def test_shell_line_rendered_when_not_paused(renderer, buffer_io):
    renderer._render_sync(_shell_line("visible-line"))
    assert "visible-line" in buffer_io.getvalue()


def test_shell_output_dispatched_when_not_paused(renderer):
    """``_render_shell_output`` itself only emits a trailing newline (full
    output goes to the LLM via tool responses, not the UI). What we care
    about is that the dispatch happens — verify _do_render is called."""
    from unittest.mock import patch

    with patch.object(renderer, "_do_render") as mock_do_render:
        renderer._render_sync(_shell_output("anything"))
        mock_do_render.assert_called_once()


# =============================================================================
# Async path must NOT bypass the silencer
# =============================================================================


@pytest.mark.asyncio
async def test_async_render_path_drops_shell_messages_while_paused(renderer, buffer_io):
    """Regression test: the async ``render()`` path used to call
    ``_do_render`` directly, end-running the sync-only pause filter and
    leaking shell banners onto the steering prompt. Lock that down."""
    get_pause_controller().pause()
    await renderer.render(_shell_start("echo ghost"))
    await renderer.render(_shell_line("ghost-line"))
    await renderer.render(_shell_output("ghost-stdout"))
    out = buffer_io.getvalue()
    assert "ghost" not in out
    assert "SHELL COMMAND" not in out
    assert out == ""


@pytest.mark.asyncio
async def test_async_render_path_renders_non_shell_while_paused(renderer, buffer_io):
    """Async path must still render non-shell messages during pause —
    pause-buffering those is the legacy renderer's job, not ours."""
    get_pause_controller().pause()
    await renderer.render(_text("async-text-info"))
    assert "async-text-info" in buffer_io.getvalue()


def test_resume_after_pause_re_enables_shell_output(renderer, buffer_io):
    pc = get_pause_controller()
    pc.pause()
    renderer._render_sync(_shell_line("hidden"))
    pc.resume()
    renderer._render_sync(_shell_line("visible-again"))

    out = buffer_io.getvalue()
    assert "hidden" not in out
    assert "visible-again" in out


# =============================================================================
# Robustness
# =============================================================================


def test_is_paused_helper_never_raises(monkeypatch):
    """The ``_is_paused`` helper must swallow any internal failure and
    return a bool — a broken pause-controller singleton must never take
    down the renderer's hot path."""
    from code_puppy.messaging import rich_renderer as rr

    def _boom():
        raise RuntimeError("pause controller exploded")

    monkeypatch.setattr(rr, "get_pause_controller", _boom, raising=False)
    # Import path inside the helper resolves at call time, so monkey-patching
    # the module-level reference doesn't directly affect the lazy import.
    # Instead, simulate a hard failure by patching the helper's import target.
    import sys

    class _BrokenModule:
        def __getattr__(self, name):
            raise RuntimeError("broken")

    monkeypatch.setitem(
        sys.modules, "code_puppy.messaging.pause_controller", _BrokenModule()
    )

    # Should still return a bool, never raise.
    result = rr._is_paused()
    assert isinstance(result, bool)
    assert result is False
