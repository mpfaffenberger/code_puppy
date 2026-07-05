"""Renderer resilience: bar plumbing and render errors must not kill
rendering (wedge-forensics hardening after the 2026-07 stdin wedge)."""

from io import StringIO

from rich.console import Console

from code_puppy.messaging.message_queue import MessageQueue, MessageType, UIMessage
from code_puppy.messaging.renderers import (
    SynchronousInteractiveRenderer,
    _print_message,
)


def _msg(text: str) -> UIMessage:
    return UIMessage(type=MessageType.INFO, content=text, metadata={})


def test_consume_thread_survives_render_exception(capsys):
    """One poisoned message must not stop the consume loop: the next
    message still renders (previously an exception killed the daemon
    thread silently and output just... stopped)."""
    q = MessageQueue()
    r = SynchronousInteractiveRenderer(q, Console(file=StringIO()))
    calls = []

    def flaky(message):
        calls.append(message.content)
        if len(calls) == 1:
            raise RuntimeError("kaboom")
        r._running = False  # stop the loop after the second message

    r._render_message = flaky
    r._running = True
    q._queue.put_nowait(_msg("first (poisoned)"))
    q._queue.put_nowait(_msg("second (must render)"))
    r._consume_messages()  # runs inline until _running flips False
    assert calls == ["first (poisoned)", "second (must render)"]
    assert "kaboom" in capsys.readouterr().err


def test_print_message_survives_bar_notify_failure(monkeypatch):
    """A broken bottom bar must never break transcript printing."""
    import code_puppy.messaging.bottom_bar as bb

    class ExplodingBar:
        def notify_transcript_output(self):
            raise RuntimeError("bar geometry went sideways")

    monkeypatch.setattr(bb, "get_bottom_bar", lambda: ExplodingBar())
    out = StringIO()
    _print_message(Console(file=out), _msg("still prints"))
    assert "still prints" in out.getvalue()
