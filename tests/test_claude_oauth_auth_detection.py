"""Tests for Claude Code OAuth auth-error detection (is_claude_auth_error)."""

from code_puppy.plugins.claude_code_oauth.auth_retry import is_claude_auth_error
from tests.claude_oauth_helpers import (
    CLOUDFLARE_400_TEXT,
    HttpxishError,
    StatusError,
)


class TestAuthErrorDetection:
    def test_401_status_code(self):
        assert is_claude_auth_error(StatusError("unauthorized", status_code=401))

    def test_403_status_code(self):
        assert is_claude_auth_error(StatusError("forbidden", status_code=403))

    def test_401_on_response_attribute(self):
        assert is_claude_auth_error(HttpxishError("boom", status_code=401))

    def test_cloudflare_400_in_message(self):
        exc = StatusError(CLOUDFLARE_400_TEXT, status_code=400)
        assert is_claude_auth_error(exc)

    def test_cloudflare_400_in_body(self):
        exc = StatusError("bad request", status_code=400, body=CLOUDFLARE_400_TEXT)
        assert is_claude_auth_error(exc)

    def test_cloudflare_markers_without_status(self):
        assert is_claude_auth_error(Exception(CLOUDFLARE_400_TEXT))

    def test_plain_400_is_not_auth(self):
        exc = StatusError("invalid_request_error: bad tool schema", status_code=400)
        assert not is_claude_auth_error(exc)

    def test_500_is_not_auth(self):
        assert not is_claude_auth_error(StatusError("server error", status_code=500))

    def test_generic_exception_is_not_auth(self):
        assert not is_claude_auth_error(ValueError("nope"))

    def test_wrapped_cause_chain_is_walked(self):
        inner = StatusError("unauthorized", status_code=401)
        outer = RuntimeError("model call failed")
        outer.__cause__ = inner
        assert is_claude_auth_error(outer)

    def test_context_chain_is_walked(self):
        inner = StatusError("forbidden", status_code=403)
        outer = RuntimeError("wrapper")
        outer.__context__ = inner
        assert is_claude_auth_error(outer)

    def test_cyclic_chain_terminates(self):
        exc = RuntimeError("loop")
        exc.__cause__ = exc
        assert not is_claude_auth_error(exc)

    def test_real_model_http_error_401_with_none_body(self):
        """Regression: the exact production shape from the streaming path.

        pydantic-ai raised ``ModelHTTPError(status_code=401,
        model_name='claude-fable-5', body=None)`` and the run died. Detection
        must work on status_code alone — no body, no helpful message.
        """
        from pydantic_ai.exceptions import ModelHTTPError

        exc = ModelHTTPError(status_code=401, model_name="claude-fable-5", body=None)
        assert is_claude_auth_error(exc)

    def test_real_model_http_error_plain_400_is_not_auth(self):
        from pydantic_ai.exceptions import ModelHTTPError

        exc = ModelHTTPError(
            status_code=400,
            model_name="claude-fable-5",
            body={"error": {"type": "invalid_request_error"}},
        )
        assert not is_claude_auth_error(exc)
