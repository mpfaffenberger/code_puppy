"""Tests for Claude Code OAuth token refresh heartbeat."""

import asyncio
from unittest.mock import patch

import pytest

from code_puppy.plugins.claude_code_oauth.token_refresh_heartbeat import (
    HEARTBEAT_INTERVAL_SECONDS,
    MIN_REFRESH_INTERVAL_SECONDS,
    TokenRefreshHeartbeat,
    force_token_refresh,
    get_current_heartbeat,
    is_heartbeat_running,
    token_refresh_heartbeat_context,
)


class TestTokenRefreshHeartbeat:
    """Tests for the TokenRefreshHeartbeat class."""

    @pytest.mark.asyncio
    async def test_heartbeat_starts_and_stops(self):
        """Heartbeat should start and stop cleanly."""
        heartbeat = TokenRefreshHeartbeat(interval=0.1)  # Fast interval for test

        assert not heartbeat.is_running

        await heartbeat.start()
        assert heartbeat.is_running

        await heartbeat.stop()
        assert not heartbeat.is_running

    @pytest.mark.asyncio
    async def test_heartbeat_double_start_is_safe(self):
        """Starting heartbeat twice should not create duplicate tasks."""
        heartbeat = TokenRefreshHeartbeat(interval=0.1)

        await heartbeat.start()
        first_task = heartbeat._task

        await heartbeat.start()  # Second start should be no-op
        assert heartbeat._task is first_task

        await heartbeat.stop()

    @pytest.mark.asyncio
    async def test_heartbeat_double_stop_is_safe(self):
        """Stopping heartbeat twice should not raise errors."""
        heartbeat = TokenRefreshHeartbeat(interval=0.1)

        await heartbeat.start()
        await heartbeat.stop()
        await heartbeat.stop()  # Should be safe

    @pytest.mark.asyncio
    async def test_heartbeat_refresh_count_starts_at_zero(self):
        """Refresh count should start at zero."""
        heartbeat = TokenRefreshHeartbeat()
        assert heartbeat.refresh_count == 0

    @pytest.mark.asyncio
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    @patch("code_puppy.plugins.claude_code_oauth.utils.is_token_expired")
    @patch("code_puppy.plugins.claude_code_oauth.utils.refresh_access_token")
    async def test_heartbeat_refreshes_expired_token(
        self, mock_refresh, mock_is_expired, mock_load_tokens
    ):
        """Heartbeat should refresh expired tokens."""
        mock_load_tokens.return_value = {
            "access_token": "old_token",
            "refresh_token": "refresh_token",
        }
        mock_is_expired.return_value = True
        mock_refresh.return_value = "new_token"

        heartbeat = TokenRefreshHeartbeat(
            interval=0.05,  # Very fast for testing
            min_refresh_interval=0,  # No min interval for test
        )

        await heartbeat.start()
        # Wait for at least one heartbeat cycle
        await asyncio.sleep(0.15)
        await heartbeat.stop()

        assert heartbeat.refresh_count > 0
        mock_refresh.assert_called()

    @pytest.mark.asyncio
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    @patch("code_puppy.plugins.claude_code_oauth.utils.is_token_expired")
    async def test_heartbeat_skips_refresh_if_not_expired(
        self, mock_is_expired, mock_load_tokens
    ):
        """Heartbeat should not refresh if token is not expired."""
        mock_load_tokens.return_value = {
            "access_token": "valid_token",
        }
        mock_is_expired.return_value = False

        heartbeat = TokenRefreshHeartbeat(
            interval=0.05,
            min_refresh_interval=0,
        )

        await heartbeat.start()
        await asyncio.sleep(0.15)
        await heartbeat.stop()

        # No refreshes should have occurred
        assert heartbeat.refresh_count == 0

    @pytest.mark.asyncio
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    async def test_heartbeat_handles_no_tokens_gracefully(self, mock_load_tokens):
        """Heartbeat should handle missing tokens gracefully."""
        mock_load_tokens.return_value = None

        heartbeat = TokenRefreshHeartbeat(
            interval=0.05,
            min_refresh_interval=0,
        )

        await heartbeat.start()
        await asyncio.sleep(0.1)
        await heartbeat.stop()

        # Should not crash, just no refreshes
        assert heartbeat.refresh_count == 0


class TestTokenRefreshHeartbeatContext:
    """Tests for the token_refresh_heartbeat_context context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_starts_and_stops_heartbeat(self):
        """Context manager should start heartbeat on enter and stop on exit."""
        assert not is_heartbeat_running()

        async with token_refresh_heartbeat_context(interval=0.1) as heartbeat:
            assert is_heartbeat_running()
            assert get_current_heartbeat() is heartbeat

        assert not is_heartbeat_running()
        assert get_current_heartbeat() is None

    @pytest.mark.asyncio
    async def test_context_manager_stops_on_exception(self):
        """Context manager should stop heartbeat even if exception is raised."""
        with pytest.raises(ValueError):
            async with token_refresh_heartbeat_context(interval=0.1):
                raise ValueError("Test error")

        # Heartbeat should be stopped despite exception
        assert not is_heartbeat_running()

    @pytest.mark.asyncio
    async def test_context_manager_yields_heartbeat(self):
        """Context manager should yield the heartbeat instance."""
        async with token_refresh_heartbeat_context(interval=0.1) as heartbeat:
            assert isinstance(heartbeat, TokenRefreshHeartbeat)
            assert heartbeat.is_running


class TestForceTokenRefresh:
    """Tests for the force_token_refresh function."""

    @pytest.mark.asyncio
    @patch("code_puppy.plugins.claude_code_oauth.utils.refresh_access_token")
    async def test_force_refresh_success(self, mock_refresh):
        """force_token_refresh should return True on success."""
        mock_refresh.return_value = "new_token"

        result = await force_token_refresh()

        assert result is True
        mock_refresh.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    @patch("code_puppy.plugins.claude_code_oauth.utils.refresh_access_token")
    async def test_force_refresh_failure(self, mock_refresh):
        """force_token_refresh should return False on failure."""
        mock_refresh.return_value = None

        result = await force_token_refresh()

        assert result is False

    @pytest.mark.asyncio
    @patch("code_puppy.plugins.claude_code_oauth.utils.refresh_access_token")
    async def test_force_refresh_handles_exception(self, mock_refresh):
        """force_token_refresh should handle exceptions gracefully."""
        mock_refresh.side_effect = Exception("Network error")

        result = await force_token_refresh()

        assert result is False


class TestConstants:
    """Tests for module constants."""

    def test_heartbeat_interval_is_reasonable(self):
        """Heartbeat interval should be reasonable (1-5 minutes)."""
        assert 60 <= HEARTBEAT_INTERVAL_SECONDS <= 300

    def test_min_refresh_interval_is_reasonable(self):
        """Min refresh interval should be reasonable (30-120 seconds)."""
        assert 30 <= MIN_REFRESH_INTERVAL_SECONDS <= 120

    def test_min_refresh_less_than_heartbeat(self):
        """Min refresh interval should be less than heartbeat interval."""
        assert MIN_REFRESH_INTERVAL_SECONDS < HEARTBEAT_INTERVAL_SECONDS


class TestCallbackIntegration:
    """Tests for the agent_run_start/agent_run_end callback integration."""

    @pytest.mark.asyncio
    async def test_agent_run_start_starts_heartbeat_for_claude_code(self):
        """agent_run_start should start heartbeat for claude-code models."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_start,
        )

        # Clear any existing heartbeats
        _active_heartbeats.clear()

        await _on_agent_run_start(
            agent_name="test-agent",
            model_name="claude-code-sonnet-4",
            session_id="test-session-123",
        )

        # Heartbeat should be stored
        assert "test-session-123" in _active_heartbeats
        heartbeat = _active_heartbeats["test-session-123"]
        assert heartbeat.is_running

        # Cleanup
        await heartbeat.stop()
        _active_heartbeats.clear()

    @pytest.mark.asyncio
    async def test_agent_run_start_ignores_non_claude_code_models(self):
        """agent_run_start should not start heartbeat for non-claude-code models."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_start,
        )

        _active_heartbeats.clear()

        await _on_agent_run_start(
            agent_name="test-agent",
            model_name="gpt-4o",
            session_id="test-session-456",
        )

        # No heartbeat should be stored
        assert "test-session-456" not in _active_heartbeats

    @pytest.mark.asyncio
    async def test_agent_run_end_stops_heartbeat(self):
        """agent_run_end should stop the heartbeat."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_end,
            _on_agent_run_start,
        )

        _active_heartbeats.clear()

        # Start heartbeat
        await _on_agent_run_start(
            agent_name="test-agent",
            model_name="claude-code-opus-4",
            session_id="test-session-789",
        )
        assert "test-session-789" in _active_heartbeats

        # End run (with new consolidated signature)
        await _on_agent_run_end(
            agent_name="test-agent",
            model_name="claude-code-opus-4",
            session_id="test-session-789",
            success=True,
            error=None,
            response_text="test response",
            metadata={},
        )

        # Heartbeat should be removed
        assert "test-session-789" not in _active_heartbeats

    @pytest.mark.asyncio
    async def test_agent_run_end_handles_missing_heartbeat_gracefully(self):
        """agent_run_end should not error if no heartbeat exists."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_end,
        )

        _active_heartbeats.clear()

        # This should not raise (with new consolidated signature)
        await _on_agent_run_end(
            agent_name="test-agent",
            model_name="claude-code-haiku",
            session_id="nonexistent-session",
            success=True,
            error=None,
            response_text=None,
            metadata=None,
        )
