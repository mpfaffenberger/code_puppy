"""Tests for the Claude Code OAuth agent-retry hook and main-loop integration.

Detection tests live in test_claude_oauth_auth_detection.py; the forced-
refresh cooldown tests live in test_claude_oauth_refresh_cooldown.py.
"""

from unittest.mock import Mock, patch

import pytest

from code_puppy.plugins.claude_code_oauth import auth_retry
from code_puppy.plugins.claude_code_oauth.auth_retry import (
    handle_retryable_exception,
    is_claude_auth_error,
    register_runtime_token_updater,
)
from tests.claude_oauth_helpers import (
    CLOUDFLARE_400_TEXT,
    StatusError as _StatusError,
)


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


# --- Cloudflare recurrence escalation -------------------------------------------


class TestCloudflareEscalation:
    """Recurring CF400s escalate to full re-auth; refresh is field-proven
    to only buy temporary recovery, while a browser sign-in durably cures it.
    """

    @pytest.fixture(autouse=True)
    def _reset_state(self):
        auth_retry._last_cloudflare_event_at = 0.0
        yield
        auth_retry._last_cloudflare_event_at = 0.0

    def _cf_exc(self):
        return _StatusError(CLOUDFLARE_400_TEXT, status_code=400)

    def _common_patches(self, reauth_return="reauth_token"):
        return (
            patch.object(
                auth_retry,
                "load_stored_tokens",
                return_value={"access_token": "old", "refresh_token": "r"},
            ),
            patch.object(auth_retry, "refresh_access_token", return_value="refreshed"),
            patch.object(
                auth_retry,
                "_run_full_reauthentication",
                return_value=reauth_return,
            ),
            patch.object(auth_retry, "emit_warning"),
            patch.object(auth_retry, "emit_info"),
        )

    @pytest.mark.asyncio
    async def test_first_cloudflare_400_uses_cheap_refresh(self):
        patches = self._common_patches()
        with (
            patches[0],
            patches[1] as mock_refresh,
            patches[2] as mock_reauth,
            patches[3],
            patches[4],
        ):
            result = await handle_retryable_exception(
                self._cf_exc(), model_name="claude-code-claude-fable-5"
            )

        assert result is True
        mock_refresh.assert_called_once()
        mock_reauth.assert_not_called()
        assert auth_retry._last_cloudflare_event_at > 0

    @pytest.mark.asyncio
    async def test_recurring_cloudflare_400_escalates_to_reauth(self):
        updater = Mock()
        register_runtime_token_updater(updater)
        # Simulate a CF400 handled moments ago (refresh didn't cure it).
        auth_retry._last_cloudflare_event_at = __import__("time").monotonic() - 30

        patches = self._common_patches()
        with (
            patches[0],
            patches[1] as mock_refresh,
            patches[2] as mock_reauth,
            patches[3],
            patches[4],
        ):
            result = await handle_retryable_exception(
                self._cf_exc(), model_name="claude-code-claude-fable-5"
            )

        assert result is True
        mock_reauth.assert_called_once_with("claude-code-claude-fable-5")
        mock_refresh.assert_not_called()
        updater.assert_called_once_with("reauth_token")
        # Cured: future CF400s start fresh with the cheap refresh path.
        assert auth_retry._last_cloudflare_event_at == 0.0

    @pytest.mark.asyncio
    async def test_cloudflare_outside_window_does_not_escalate(self):
        auth_retry._last_cloudflare_event_at = __import__("time").monotonic() - (
            auth_retry.CLOUDFLARE_REAUTH_WINDOW_SECONDS + 60
        )

        patches = self._common_patches()
        with (
            patches[0],
            patches[1] as mock_refresh,
            patches[2] as mock_reauth,
            patches[3],
            patches[4],
        ):
            result = await handle_retryable_exception(
                self._cf_exc(), model_name="claude-code-claude-fable-5"
            )

        assert result is True
        mock_refresh.assert_called_once()
        mock_reauth.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_reauth_does_not_retry(self):
        auth_retry._last_cloudflare_event_at = __import__("time").monotonic() - 30

        patches = self._common_patches(reauth_return=None)
        with patches[0], patches[1], patches[2] as mock_reauth, patches[3], patches[4]:
            result = await handle_retryable_exception(
                self._cf_exc(), model_name="claude-code-claude-fable-5"
            )

        assert result is False
        mock_reauth.assert_called_once()

    @pytest.mark.asyncio
    async def test_plain_401_never_escalates_even_when_recurring(self):
        auth_retry._last_cloudflare_event_at = __import__("time").monotonic() - 30

        patches = self._common_patches()
        with (
            patches[0],
            patches[1] as mock_refresh,
            patches[2] as mock_reauth,
            patches[3],
            patches[4],
        ):
            result = await handle_retryable_exception(
                _StatusError("unauthorized", status_code=401),
                model_name="claude-code-claude-fable-5",
            )

        assert result is True
        mock_refresh.assert_called_once()
        mock_reauth.assert_not_called()
