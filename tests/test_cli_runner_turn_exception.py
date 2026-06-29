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


def _model_api_error_with_cause() -> Exception:
    """Build the exact wrapper shape pydantic-ai 1.56's Anthropic adapter raises."""
    from pydantic_ai.exceptions import ModelAPIError

    wrapper = ModelAPIError(model_name="claude-x", message="Connection error.")
    wrapper.__cause__ = httpx.ConnectError("failed to establish connection")
    return wrapper


def _anthropic_upstream_idle_timeout() -> Exception:
    """Build the mid-stream gateway-stall shape we see in production."""
    from anthropic import APIStatusError

    err = APIStatusError.__new__(APIStatusError)
    err.status_code = 502
    err.body = {
        "error": {
            "message": "upstream_idle_timeout (rid=abc): no data for 60s",
            "type": "api_error",
        }
    }
    err.message = "upstream_idle_timeout (rid=abc): no data for 60s"
    return err


# Transient transport failures: friendly message, no traceback dump.
TRANSIENT_ERRORS = [
    httpx.ReadError("connection dropped mid-stream"),
    httpx.ConnectError("failed to establish connection"),
    httpx.ReadTimeout("read timed out"),
    httpx.ConnectTimeout("connect timed out"),
    httpx.RemoteProtocolError("peer closed connection"),
    httpcore.ReadError("connection dropped mid-stream"),
    httpcore.RemoteProtocolError("peer closed connection"),
    # Wrapper exceptions thrown by pydantic-ai + the Anthropic SDK that used
    # to escape the classifier (and so dumped a 60-line traceback for what is
    # genuinely a transient gateway blip).
    _model_api_error_with_cause(),
    _anthropic_upstream_idle_timeout(),
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


def test_transient_exception_is_persisted_to_error_log(monkeypatch):
    """Even when we hide the traceback behind a friendly one-liner, the underlying
    exception MUST still be written to ``~/.code_puppy/logs/errors.log`` so SRE
    / support can see the actual upstream blip and measure its frequency.
    """
    captured = []

    def fake_log_error(exc, context=None, include_traceback=True):
        captured.append((exc, context))

    monkeypatch.setattr(
        "code_puppy.error_logging.log_error", fake_log_error
    )

    with (
        patch("code_puppy.messaging.emit_error"),
        patch("code_puppy.messaging.queue_console.get_queue_console"),
    ):
        _render_turn_exception(_anthropic_upstream_idle_timeout())

    assert len(captured) == 1
    exc, context = captured[0]
    assert type(exc).__name__ == "APIStatusError"
    assert "friendly one-liner" in context


def test_non_transient_exception_is_persisted_to_error_log(monkeypatch):
    """Genuine bugs MUST also hit errors.log -- the on-screen traceback is
    transient (scrollback), but support needs durable records to triage later.
    """
    captured = []

    def fake_log_error(exc, context=None, include_traceback=True):
        captured.append((exc, context))

    monkeypatch.setattr(
        "code_puppy.error_logging.log_error", fake_log_error
    )

    with (
        patch("code_puppy.messaging.emit_error"),
        patch("code_puppy.messaging.queue_console.get_queue_console"),
    ):
        _render_turn_exception(ValueError("a genuine programming bug"))

    assert len(captured) == 1
    exc, context = captured[0]
    assert isinstance(exc, ValueError)
    assert str(exc) == "a genuine programming bug"
    assert "non-transient" in context
