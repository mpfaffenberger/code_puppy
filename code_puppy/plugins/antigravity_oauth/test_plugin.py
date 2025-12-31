"""Tests for the Antigravity OAuth plugin."""

from __future__ import annotations

import time

import pytest

from .accounts import AccountManager
from .config import ANTIGRAVITY_OAUTH_CONFIG
from .constants import ANTIGRAVITY_MODELS, ANTIGRAVITY_SCOPES
from .oauth import (
    _compute_code_challenge,
    _decode_state,
    _encode_state,
    _generate_code_verifier,
    prepare_oauth_context,
)
from .storage import (
    _migrate_v1_to_v2,
    _migrate_v2_to_v3,
)
from .token import (
    RefreshParts,
    format_refresh_parts,
    is_token_expired,
    parse_refresh_parts,
)


class TestPKCE:
    """Test PKCE code generation and verification."""

    def test_code_verifier_length(self):
        """Code verifier should be URL-safe base64 encoded."""
        verifier = _generate_code_verifier()
        assert len(verifier) > 40  # At least 43 chars for 32 bytes
        assert "=" not in verifier  # No padding
        assert " " not in verifier

    def test_code_challenge_is_sha256(self):
        """Code challenge should be S256 of verifier."""
        verifier = "test_verifier_string"
        challenge = _compute_code_challenge(verifier)
        assert len(challenge) > 20
        assert "=" not in challenge

    def test_different_verifiers_produce_different_challenges(self):
        """Each verifier should produce a unique challenge."""
        v1 = _generate_code_verifier()
        v2 = _generate_code_verifier()
        c1 = _compute_code_challenge(v1)
        c2 = _compute_code_challenge(v2)
        assert c1 != c2

    def test_prepare_oauth_context(self):
        """OAuth context should have all required fields."""
        ctx = prepare_oauth_context()
        assert ctx.state
        assert ctx.code_verifier
        assert ctx.code_challenge
        assert ctx.redirect_uri is None  # Not assigned yet


class TestStateEncoding:
    """Test OAuth state encoding/decoding."""

    def test_encode_decode_roundtrip(self):
        """State should survive encode/decode roundtrip."""
        verifier = "test-verifier-123"
        project_id = "my-project"

        encoded = _encode_state(verifier, project_id)
        decoded_verifier, decoded_project = _decode_state(encoded)

        assert decoded_verifier == verifier
        assert decoded_project == project_id

    def test_encode_without_project_id(self):
        """Should handle empty project ID."""
        verifier = "test-verifier"
        encoded = _encode_state(verifier, "")
        decoded_verifier, decoded_project = _decode_state(encoded)

        assert decoded_verifier == verifier
        assert decoded_project == ""

    def test_decode_invalid_state_raises(self):
        """Invalid state should raise ValueError."""
        with pytest.raises(ValueError):
            _decode_state("not-valid-base64!!!")


class TestRefreshParts:
    """Test refresh token parsing and formatting."""

    def test_parse_simple_token(self):
        """Parse a token without project IDs."""
        parts = parse_refresh_parts("my-refresh-token")
        assert parts.refresh_token == "my-refresh-token"
        assert parts.project_id is None
        assert parts.managed_project_id is None

    def test_parse_with_project_id(self):
        """Parse a token with project ID."""
        parts = parse_refresh_parts("my-token|project-123")
        assert parts.refresh_token == "my-token"
        assert parts.project_id == "project-123"
        assert parts.managed_project_id is None

    def test_parse_with_managed_project(self):
        """Parse a token with both project IDs."""
        parts = parse_refresh_parts("token|proj|managed")
        assert parts.refresh_token == "token"
        assert parts.project_id == "proj"
        assert parts.managed_project_id == "managed"

    def test_parse_empty_string(self):
        """Empty string should produce empty parts."""
        parts = parse_refresh_parts("")
        assert parts.refresh_token == ""
        assert parts.project_id is None

    def test_format_roundtrip(self):
        """Format and parse should be inverse operations."""
        original = RefreshParts(
            refresh_token="token",
            project_id="project",
            managed_project_id="managed",
        )
        formatted = format_refresh_parts(original)
        parsed = parse_refresh_parts(formatted)

        assert parsed.refresh_token == original.refresh_token
        assert parsed.project_id == original.project_id
        assert parsed.managed_project_id == original.managed_project_id


class TestTokenExpiry:
    """Test token expiry checking."""

    def test_none_expires_is_expired(self):
        """None expiry should be treated as expired."""
        assert is_token_expired(None) is True

    def test_past_time_is_expired(self):
        """Past time should be expired."""
        past = time.time() - 3600
        assert is_token_expired(past) is True

    def test_future_time_not_expired(self):
        """Future time should not be expired."""
        future = time.time() + 3600
        assert is_token_expired(future) is False

    def test_expiry_buffer(self):
        """Token expiring soon should be treated as expired (60s buffer)."""
        almost_expired = time.time() + 30  # 30 seconds from now
        assert is_token_expired(almost_expired) is True


class TestStorageMigration:
    """Test storage format migrations."""

    def test_migrate_v1_to_v2(self):
        """V1 format should migrate to V2."""
        v1_data = {
            "version": 1,
            "accounts": [
                {
                    "email": "test@example.com",
                    "refreshToken": "token123",
                    "addedAt": 1000,
                    "lastUsed": 2000,
                    "isRateLimited": False,
                }
            ],
            "activeIndex": 0,
        }

        v2_data = _migrate_v1_to_v2(v1_data)

        assert v2_data["version"] == 2
        assert len(v2_data["accounts"]) == 1
        assert v2_data["accounts"][0]["email"] == "test@example.com"

    def test_migrate_v2_to_v3(self):
        """V2 format should migrate to V3."""
        v2_data = {
            "version": 2,
            "accounts": [
                {
                    "email": "test@example.com",
                    "refreshToken": "token123",
                    "addedAt": 1000,
                    "lastUsed": 2000,
                    "rateLimitResetTimes": {"gemini": time.time() * 1000 + 60000},
                }
            ],
            "activeIndex": 0,
        }

        v3_data = _migrate_v2_to_v3(v2_data)

        assert v3_data["version"] == 3
        assert "activeIndexByFamily" in v3_data


class TestAccountManager:
    """Test multi-account management."""

    def test_empty_manager(self):
        """Empty manager should have no accounts."""
        manager = AccountManager()
        assert manager.account_count == 0

    def test_add_account(self):
        """Should be able to add accounts."""
        manager = AccountManager()
        acc = manager.add_account("token123", email="test@example.com")

        assert manager.account_count == 1
        assert acc.email == "test@example.com"

    def test_get_current_for_family(self):
        """Should get current account for family."""
        manager = AccountManager()
        manager.add_account("token1", email="user1@example.com")
        manager.add_account("token2", email="user2@example.com")

        acc = manager.get_current_or_next_for_family("claude")
        assert acc is not None
        assert acc.email in ["user1@example.com", "user2@example.com"]

    def test_rate_limit_switches_account(self):
        """Rate limiting should cause account switch."""
        manager = AccountManager()
        acc1 = manager.add_account("token1", email="user1@example.com")
        manager.add_account("token2", email="user2@example.com")

        # Mark first account as rate limited for Claude
        manager.mark_rate_limited(acc1, 60000, "claude")

        # Should get the second account
        current = manager.get_current_or_next_for_family("claude")
        assert current is not None
        assert current.email == "user2@example.com"

    def test_min_wait_time_calculation(self):
        """Should calculate minimum wait time correctly."""
        manager = AccountManager()
        acc = manager.add_account("token", email="test@example.com")

        # No rate limits = 0 wait time
        assert manager.get_min_wait_time_for_family("claude") == 0

        # Add rate limit
        manager.mark_rate_limited(acc, 5000, "claude")
        wait = manager.get_min_wait_time_for_family("claude")
        assert 0 < wait <= 5000

    def test_gemini_dual_quota(self):
        """Gemini should try both quota pools."""
        manager = AccountManager()
        acc = manager.add_account("token", email="test@example.com")

        # Initially, antigravity should be available
        style = manager.get_available_header_style(acc, "gemini")
        assert style == "antigravity"

        # Rate limit antigravity
        manager.mark_rate_limited(acc, 60000, "gemini", "antigravity")

        # Now gemini-cli should be available
        style = manager.get_available_header_style(acc, "gemini")
        assert style == "gemini-cli"

        # Rate limit gemini-cli too
        manager.mark_rate_limited(acc, 60000, "gemini", "gemini-cli")

        # No style available
        style = manager.get_available_header_style(acc, "gemini")
        assert style is None


class TestConstants:
    """Test plugin constants are properly configured."""

    def test_models_have_required_fields(self):
        """All models should have required configuration."""
        for model_id, config in ANTIGRAVITY_MODELS.items():
            assert "name" in config, f"{model_id} missing name"
            assert "family" in config, f"{model_id} missing family"
            assert "context_length" in config, f"{model_id} missing context_length"
            assert "max_output" in config, f"{model_id} missing max_output"

    def test_thinking_models_have_budget(self):
        """Thinking models should have thinking_budget."""
        for model_id, config in ANTIGRAVITY_MODELS.items():
            if "thinking" in model_id:
                assert "thinking_budget" in config, (
                    f"{model_id} missing thinking_budget"
                )

    def test_scopes_are_valid(self):
        """OAuth scopes should be valid URLs."""
        for scope in ANTIGRAVITY_SCOPES:
            assert scope.startswith("https://"), f"Invalid scope: {scope}"

    def test_config_has_required_fields(self):
        """Plugin config should have required fields."""
        assert "auth_url" in ANTIGRAVITY_OAUTH_CONFIG
        assert "token_url" in ANTIGRAVITY_OAUTH_CONFIG
        assert "callback_port_range" in ANTIGRAVITY_OAUTH_CONFIG
        assert "prefix" in ANTIGRAVITY_OAUTH_CONFIG


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
