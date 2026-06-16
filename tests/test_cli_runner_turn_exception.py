"""Tests for ``_render_turn_exception`` -- the REPL's turn-level error renderer.

A connection-management hiccup must never look like (or behave like) a crash.
Transient/connection errors should surface as a friendly one-liner; genuine
bugs should still get the full, debuggable traceback. These tests pin both
halves of that contract so we never regress back to dumping a 60-line stack
trace for a dropped socket.
"""

from unittest.mock import MagicMock, patch

import httpcore
import httpx
import pytest

from code_puppy.cli_runner import _render_turn_exception

# Transient transport failures: friendly message, no traceback dump.
TRANSIENT_ERRORS = [
    httpx.ReadError("connection dropped mid-stream"),
    httpx.ConnectError("failed to establish connection"),
    httpx.ReadTimeout("read timed out"),
    httpx.ConnectTimeout("connect timed out"),
    httpx.RemoteProtocolError("peer closed connection"),
    httpcore.ReadError("connection dropped mid-stream"),
    httpcore.RemoteProtocolError("peer closed connection"),
]


@pytest.mark.parametrize("exc", TRANSIENT_ERRORS, ids=lambda e: type(e).__name__)
def test_transient_errors_get_friendly_message_no_traceback(exc):
    with (
        patch("code_puppy.messaging.emit_error") as mock_emit,
        patch("code_puppy.messaging.queue_console.get_queue_console") as mock_console,
    ):
        _render_turn_exception(exc)

    # Friendly message emitted, full traceback dump NOT triggered.
    assert mock_emit.call_count == 1
    msg = mock_emit.call_args.args[0]
    assert type(exc).__name__ in msg
    assert "re-run" in msg
    mock_console.assert_not_called()


def test_genuine_bug_gets_full_traceback():
    fake_console = MagicMock()
    with (
        patch("code_puppy.messaging.emit_error") as mock_emit,
        patch(
            "code_puppy.messaging.queue_console.get_queue_console",
            return_value=fake_console,
        ),
    ):
        _render_turn_exception(ValueError("this is a real bug"))

    # No friendly hand-waving for genuine bugs -- show the stack trace.
    mock_emit.assert_not_called()
    fake_console.print_exception.assert_called_once()
