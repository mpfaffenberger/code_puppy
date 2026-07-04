"""Tests for agent-level auto-retry on Claude Code OAuth auth errors."""

from unittest.mock import Mock, patch

import pytest

from code_puppy.plugins.claude_code_oauth import auth_retry
from code_puppy.plugins.claude_code_oauth.auth_retry import (
    handle_retryable_exception,
    is_claude_auth_error,
    register_runtime_token_updater,
)

CLOUDFLARE_400_TEXT = (
    "<html><head><title>400 Bad Request</title></head>"
    "<body><center><h1>400 Bad Request</h1></center>"
    "<hr><center>cloudflare</center></body></html>"
)


class _StatusError(Exception):
    """Stand-in for anthropic APIStatusError / pydantic-ai ModelHTTPError."""

    def __init__(self, message: str, status_code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class _HttpxishError(Exception):
    """Stand-in for httpx.HTTPStatusError (status lives on .response)."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.response = Mock(status_code=status_code)


# --- is_claude_auth_error ---------------------------------------------------


class TestAuthErrorDetection:
    def test_401_status_code(self):
        assert is_claude_auth_error(_StatusError("unauthorized", status_code=401))

    def test_403_status_code(self):
        assert is_claude_auth_error(_StatusError("forbidden", status_code=403))

    def test_401_on_response_attribute(self):
        assert is_claude_auth_error(_HttpxishError("boom", status_code=401))

    def test_cloudflare_400_in_message(self):
        exc = _StatusError(CLOUDFLARE_400_TEXT, status_code=400)
        assert is_claude_auth_error(exc)

    def test_cloudflare_400_in_body(self):
        exc = _StatusError("bad request", status_code=400, body=CLOUDFLARE_400_TEXT)
        assert is_claude_auth_error(exc)

    def test_cloudflare_markers_without_status(self):
        assert is_claude_auth_error(Exception(CLOUDFLARE_400_TEXT))

    def test_plain_400_is_not_auth(self):
        exc = _StatusError("invalid_request_error: bad tool schema", status_code=400)
        assert not is_claude_auth_error(exc)

    def test_500_is_not_auth(self):
        assert not is_claude_auth_error(_StatusError("server error", status_code=500))

    def test_generic_exception_is_not_auth(self):
        assert not is_claude_auth_error(ValueError("nope"))

    def test_wrapped_cause_chain_is_walked(self):
        inner = _StatusError("unauthorized", status_code=401)
        outer = RuntimeError("model call failed")
        outer.__cause__ = inner
        assert is_claude_auth_error(outer)

    def test_context_chain_is_walked(self):
        inner = _StatusError("forbidden", status_code=403)
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


# --- handle_retryable_exception ----------------------------------------------


AUTH_EXC = _StatusError("unauthorized", status_code=401)


@pytest.mark.asyncio
async def test_non_claude_code_model_is_ignored():
    with patch.object(auth_retry, "refresh_access_token") as mock_refresh:
        result = await handle_retryable_exception(AUTH_EXC, model_name="gpt-5")

    assert result is False
    mock_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_non_auth_error_is_ignored():
    result = await handle_retryable_exception(
        ValueError("boring"), model_name="claude-code-claude-opus-4-8"
    )
    assert result is False


@pytest.mark.asyncio
async def test_no_stored_tokens_does_not_retry():
    with (
        patch.object(auth_retry, "load_stored_tokens", return_value=None),
        patch.object(auth_retry, "refresh_access_token") as mock_refresh,
        patch.object(auth_retry, "emit_warning"),
    ):
        result = await handle_retryable_exception(
            AUTH_EXC, model_name="claude-code-claude-opus-4-8"
        )

    assert result is False
    mock_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_auth_error_refreshes_token_and_opts_into_retry():
    updater = Mock()
    register_runtime_token_updater(updater)

    with (
        patch.object(
            auth_retry,
            "load_stored_tokens",
            return_value={"access_token": "old", "refresh_token": "r"},
        ),
        patch.object(
            auth_retry, "refresh_access_token", return_value="fresh_token"
        ) as mock_refresh,
        patch.object(auth_retry, "emit_warning"),
        patch.object(auth_retry, "emit_info"),
    ):
        result = await handle_retryable_exception(
            AUTH_EXC, model_name="claude-code-claude-opus-4-8"
        )

    assert result is True
    mock_refresh.assert_called_once_with(True)
    updater.assert_called_once_with("fresh_token")


@pytest.mark.asyncio
async def test_refresh_failure_still_opts_into_retry():
    with (
        patch.object(
            auth_retry,
            "load_stored_tokens",
            return_value={"access_token": "old", "refresh_token": "r"},
        ),
        patch.object(auth_retry, "refresh_access_token", return_value=None),
        patch.object(auth_retry, "emit_warning"),
    ):
        result = await handle_retryable_exception(
            AUTH_EXC, model_name="claude-code-claude-opus-4-8"
        )

    assert result is True


@pytest.mark.asyncio
async def test_broken_token_updater_does_not_crash_retry():
    bad_updater = Mock(side_effect=RuntimeError("dead client"))
    register_runtime_token_updater(bad_updater)

    with (
        patch.object(
            auth_retry,
            "load_stored_tokens",
            return_value={"access_token": "old", "refresh_token": "r"},
        ),
        patch.object(auth_retry, "refresh_access_token", return_value="fresh"),
        patch.object(auth_retry, "emit_warning"),
        patch.object(auth_retry, "emit_info"),
    ):
        result = await handle_retryable_exception(
            AUTH_EXC, model_name="claude-code-claude-opus-4-8"
        )

    assert result is True
    bad_updater.assert_called_once_with("fresh")


# --- main-loop integration ----------------------------------------------------


@pytest.mark.asyncio
async def test_hook_gates_on_configured_name_not_exception_model_name():
    """Regression: ModelHTTPError carries the bare API model name
    ('claude-fable-5'), NOT the prefixed config name. Gating must use the
    model_name kwarg supplied by the runtime (agent.get_model_name()).
    """
    from pydantic_ai.exceptions import ModelHTTPError

    exc = ModelHTTPError(status_code=401, model_name="claude-fable-5", body=None)

    with (
        patch.object(
            auth_retry,
            "load_stored_tokens",
            return_value={"access_token": "old", "refresh_token": "r"},
        ),
        patch.object(auth_retry, "refresh_access_token", return_value="fresh"),
        patch.object(auth_retry, "emit_warning"),
        patch.object(auth_retry, "emit_info"),
    ):
        # Configured claude-code-* model → opt in, even though the
        # exception's own model_name attribute has no prefix.
        assert (
            await handle_retryable_exception(
                exc, model_name="claude-code-claude-fable-5"
            )
            is True
        )
        # Same exception on a vanilla Anthropic model → not our circus.
        assert (
            await handle_retryable_exception(exc, model_name="claude-fable-5") is False
        )


@pytest.mark.asyncio
async def test_streaming_retry_recovers_from_production_401(monkeypatch):
    """Full loop: the exact ModelHTTPError from the field, plugin hook
    registered, token refreshed, run retried and recovered.
    """
    from pydantic_ai.exceptions import ModelHTTPError

    from code_puppy.agents._runtime import streaming_retry
    from code_puppy.callbacks import register_callback, unregister_callback

    monkeypatch.setattr(
        auth_retry,
        "load_stored_tokens",
        lambda: {"access_token": "old", "refresh_token": "r"},
    )
    monkeypatch.setattr(auth_retry, "refresh_access_token", lambda force: "fresh")
    monkeypatch.setattr(auth_retry, "emit_warning", lambda *a, **k: None)
    monkeypatch.setattr(auth_retry, "emit_info", lambda *a, **k: None)

    register_callback("agent_retryable_exception", handle_retryable_exception)
    try:
        calls = {"n": 0}

        async def factory():
            calls["n"] += 1
            if calls["n"] == 1:
                raise ModelHTTPError(
                    status_code=401, model_name="claude-fable-5", body=None
                )
            return "recovered"

        runner = streaming_retry(
            max_attempts=3,
            delays=(0, 0, 0),
            model_name="claude-code-claude-fable-5",
        )(factory)
        result = await runner()
    finally:
        unregister_callback("agent_retryable_exception", handle_retryable_exception)

    assert result == "recovered"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_streaming_retry_consults_hook_and_retries_auth_error():
    """End-to-end: the main agent retry loop retries when our hook says so."""
    from code_puppy.agents._runtime import streaming_retry
    from code_puppy.callbacks import register_callback, unregister_callback

    seen_kwargs = {}

    async def hook(exception, *args, **kwargs):
        seen_kwargs.update(kwargs)
        return is_claude_auth_error(exception)

    register_callback("agent_retryable_exception", hook)
    try:
        calls = {"n": 0}

        async def factory():
            calls["n"] += 1
            if calls["n"] == 1:
                raise _StatusError("unauthorized", status_code=401)
            return "recovered"

        runner = streaming_retry(
            max_attempts=3, delays=(0, 0, 0), model_name="claude-code-opus"
        )(factory)
        result = await runner()
    finally:
        unregister_callback("agent_retryable_exception", hook)

    assert result == "recovered"
    assert calls["n"] == 2
    assert seen_kwargs["model_name"] == "claude-code-opus"
    assert seen_kwargs["attempt"] == 1
    assert seen_kwargs["max_attempts"] == 3


@pytest.mark.asyncio
async def test_streaming_retry_still_raises_when_no_hook_claims_it():
    """Without a hook opting in, auth errors keep failing fast."""
    from code_puppy.agents._runtime import streaming_retry

    async def factory():
        raise _StatusError("unauthorized", status_code=401)

    runner = streaming_retry(
        max_attempts=3, delays=(0, 0, 0), model_name="claude-code-opus"
    )(factory)
    with pytest.raises(_StatusError):
        await runner()


@pytest.mark.asyncio
async def test_streaming_retry_streak_resets_when_attempt_made_progress():
    """Regression: a long run with scattered blips must not exhaust the cap.

    In the field, three Cloudflare 400s spread across minutes of successful
    work killed the run because the attempt counter counted TOTAL failures.
    An attempt that survives past ``progress_window`` clearly made progress,
    so its failure starts a fresh streak.
    """
    import asyncio as aio

    from code_puppy.agents._runtime import streaming_retry
    from code_puppy.callbacks import register_callback, unregister_callback

    async def hook(exception, *args, **kwargs):
        return True

    register_callback("agent_retryable_exception", hook)
    try:
        calls = {"n": 0}

        async def factory():
            calls["n"] += 1
            # Failures 1-2: instant (streak builds to 2 of 3).
            # Failure 3: after "real work" (> progress_window) -> streak
            #   resets and this failure starts a fresh streak at 1.
            # Failure 4: instant (streak 2 of 3).
            # Call 5: success. Four total failures survived with
            #   max_attempts=3 -- impossible under the old total-count cap.
            if calls["n"] == 3:
                await aio.sleep(0.06)
            if calls["n"] <= 4:
                raise _StatusError("unauthorized", status_code=401)
            return "survived the flappy edge"

        runner = streaming_retry(
            max_attempts=3,
            delays=(0, 0, 0),
            model_name="claude-code-opus",
            progress_window=0.05,
        )(factory)
        result = await runner()
    finally:
        unregister_callback("agent_retryable_exception", hook)

    assert result == "survived the flappy edge"
    assert calls["n"] == 5


@pytest.mark.asyncio
async def test_streaming_retry_exhausts_attempts_when_error_persists():
    """A hook that keeps opting in is still bounded by max_attempts."""
    from code_puppy.agents._runtime import streaming_retry
    from code_puppy.callbacks import register_callback, unregister_callback

    async def hook(exception, *args, **kwargs):
        return True

    register_callback("agent_retryable_exception", hook)
    try:
        calls = {"n": 0}

        async def factory():
            calls["n"] += 1
            raise _StatusError("unauthorized", status_code=401)

        runner = streaming_retry(
            max_attempts=3, delays=(0, 0, 0), model_name="claude-code-opus"
        )(factory)
        with pytest.raises(_StatusError):
            await runner()
    finally:
        unregister_callback("agent_retryable_exception", hook)

    assert calls["n"] == 3


# --- forced-refresh cooldown ----------------------------------------------------


class TestForceRefreshCooldown:
    """Repeated force-refreshes must not spam refresh-token rotations."""

    def _valid_tokens(self, refreshed_ago: float) -> dict:
        import time

        return {
            "access_token": "current_token",
            "refresh_token": "r",
            "expires_in": 3600,
            "expires_at": time.time() + 3000,
            "refreshed_at": time.time() - refreshed_ago,
        }

    def test_force_refresh_within_cooldown_reuses_token(self):
        from code_puppy.plugins.claude_code_oauth import utils

        with (
            patch.object(
                utils, "load_stored_tokens", return_value=self._valid_tokens(5)
            ),
            patch.object(utils.requests, "post") as mock_post,
        ):
            result = utils.refresh_access_token(force=True)

        assert result == "current_token"
        mock_post.assert_not_called()

    def test_force_refresh_after_cooldown_does_exchange(self):
        from code_puppy.plugins.claude_code_oauth import utils

        response = Mock(status_code=200)
        response.headers = {"content-type": "application/json"}
        response.json.return_value = {
            "access_token": "brand_new",
            "refresh_token": "r2",
            "expires_in": 3600,
        }

        with (
            patch.object(
                utils, "load_stored_tokens", return_value=self._valid_tokens(120)
            ),
            patch.object(utils.requests, "post", return_value=response) as mock_post,
            patch.object(utils, "save_tokens", return_value=True) as mock_save,
            patch.object(utils, "update_claude_code_model_tokens"),
        ):
            result = utils.refresh_access_token(force=True)

        assert result == "brand_new"
        mock_post.assert_called_once()
        saved = mock_save.call_args.args[0]
        assert saved["refreshed_at"] == pytest.approx(__import__("time").time(), abs=5)

    def test_expired_token_ignores_cooldown(self):
        """An actually-expired token must always attempt the exchange."""
        import time

        from code_puppy.plugins.claude_code_oauth import utils

        tokens = self._valid_tokens(1)
        tokens["expires_at"] = time.time() - 10  # expired despite recent refresh

        response = Mock(status_code=200)
        response.headers = {"content-type": "application/json"}
        response.json.return_value = {
            "access_token": "brand_new",
            "refresh_token": "r2",
            "expires_in": 3600,
        }

        with (
            patch.object(utils, "load_stored_tokens", return_value=tokens),
            patch.object(utils.requests, "post", return_value=response) as mock_post,
            patch.object(utils, "save_tokens", return_value=True),
            patch.object(utils, "update_claude_code_model_tokens"),
        ):
            result = utils.refresh_access_token(force=True)

        assert result == "brand_new"
        mock_post.assert_called_once()
