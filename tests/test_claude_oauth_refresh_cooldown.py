"""Tests for the forced-refresh cooldown in Claude Code OAuth token utils.

Every refresh-token exchange rotates the refresh token; repeated forced
refreshes during a flappy episode risk invalidating the token family.
"""

import time
from unittest.mock import Mock, patch

import pytest

from code_puppy.plugins.claude_code_oauth import utils


def _valid_tokens(refreshed_ago: float) -> dict:
    return {
        "access_token": "current_token",
        "refresh_token": "r",
        "expires_in": 3600,
        "expires_at": time.time() + 3000,
        "refreshed_at": time.time() - refreshed_ago,
    }


def _exchange_response() -> Mock:
    response = Mock(status_code=200)
    response.headers = {"content-type": "application/json"}
    response.json.return_value = {
        "access_token": "brand_new",
        "refresh_token": "r2",
        "expires_in": 3600,
    }
    return response


class TestForceRefreshCooldown:
    """Repeated force-refreshes must not spam refresh-token rotations."""

    def test_force_refresh_within_cooldown_reuses_token(self):
        with (
            patch.object(utils, "load_stored_tokens", return_value=_valid_tokens(5)),
            patch.object(utils.requests, "post") as mock_post,
        ):
            result = utils.refresh_access_token(force=True)

        assert result == "current_token"
        mock_post.assert_not_called()

    def test_force_refresh_after_cooldown_does_exchange(self):
        with (
            patch.object(utils, "load_stored_tokens", return_value=_valid_tokens(120)),
            patch.object(
                utils.requests, "post", return_value=_exchange_response()
            ) as mock_post,
            patch.object(utils, "save_tokens", return_value=True) as mock_save,
            patch.object(utils, "update_claude_code_model_tokens"),
        ):
            result = utils.refresh_access_token(force=True)

        assert result == "brand_new"
        mock_post.assert_called_once()
        saved = mock_save.call_args.args[0]
        assert saved["refreshed_at"] == pytest.approx(time.time(), abs=5)

    def test_expired_token_ignores_cooldown(self):
        """An actually-expired token must always attempt the exchange."""
        tokens = _valid_tokens(1)
        tokens["expires_at"] = time.time() - 10  # expired despite recent refresh

        with (
            patch.object(utils, "load_stored_tokens", return_value=tokens),
            patch.object(
                utils.requests, "post", return_value=_exchange_response()
            ) as mock_post,
            patch.object(utils, "save_tokens", return_value=True),
            patch.object(utils, "update_claude_code_model_tokens"),
        ):
            result = utils.refresh_access_token(force=True)

        assert result == "brand_new"
        mock_post.assert_called_once()
