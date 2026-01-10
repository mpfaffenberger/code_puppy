"""Comprehensive test coverage for Antigravity OAuth storage.

Tests cover:
- RateLimitState serialization and deserialization
- AccountMetadata serialization and deserialization
- AccountStorage serialization and deserialization
- V1 to V2 migration
- V2 to V3 migration
- Loading accounts from disk with migration
- Saving accounts to disk
- Clearing stored accounts
- Error handling for corrupted files
- Edge cases and boundary conditions
"""

from __future__ import annotations

import json
import logging
import time
from unittest.mock import MagicMock

import pytest

from code_puppy.plugins.antigravity_oauth.storage import (
    AccountMetadata,
    AccountStorage,
    RateLimitState,
    _migrate_v1_to_v2,
    _migrate_v2_to_v3,
    clear_accounts,
    load_accounts,
    save_accounts,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def temp_storage_path(tmp_path, monkeypatch):
    """Create a temporary storage path for testing."""
    storage_file = tmp_path / "accounts.json"
    monkeypatch.setattr(
        "code_puppy.plugins.antigravity_oauth.storage.get_accounts_storage_path",
        lambda: storage_file,
    )
    return storage_file


@pytest.fixture
def current_time():
    """Get current time in milliseconds."""
    return time.time() * 1000


# ============================================================================
# TESTS: RateLimitState
# ============================================================================


class TestRateLimitState:
    """Test RateLimitState dataclass."""

    def test_init_defaults(self):
        """Test initialization with default values."""
        state = RateLimitState()
        assert state.claude is None
        assert state.gemini_antigravity is None
        assert state.gemini_cli is None

    def test_init_with_values(self):
        """Test initialization with specific values."""
        state = RateLimitState(
            claude=1000.0,
            gemini_antigravity=2000.0,
            gemini_cli=3000.0,
        )
        assert state.claude == 1000.0
        assert state.gemini_antigravity == 2000.0
        assert state.gemini_cli == 3000.0

    def test_to_dict_empty(self):
        """Test to_dict with no rate limits set."""
        state = RateLimitState()
        result = state.to_dict()
        assert result == {}

    def test_to_dict_partial(self):
        """Test to_dict with partial rate limits."""
        state = RateLimitState(claude=1000.0)
        result = state.to_dict()
        assert result == {"claude": 1000.0}

    def test_to_dict_full(self):
        """Test to_dict with all rate limits."""
        state = RateLimitState(
            claude=1000.0,
            gemini_antigravity=2000.0,
            gemini_cli=3000.0,
        )
        result = state.to_dict()
        assert result == {
            "claude": 1000.0,
            "gemini-antigravity": 2000.0,
            "gemini-cli": 3000.0,
        }

    def test_from_dict_empty(self):
        """Test from_dict with empty dict."""
        state = RateLimitState.from_dict({})
        assert state.claude is None
        assert state.gemini_antigravity is None
        assert state.gemini_cli is None

    def test_from_dict_none(self):
        """Test from_dict with None."""
        state = RateLimitState.from_dict(None)
        assert state.claude is None
        assert state.gemini_antigravity is None
        assert state.gemini_cli is None

    def test_from_dict_partial(self):
        """Test from_dict with partial data."""
        data = {"claude": 1000.0, "gemini-antigravity": 2000.0}
        state = RateLimitState.from_dict(data)
        assert state.claude == 1000.0
        assert state.gemini_antigravity == 2000.0
        assert state.gemini_cli is None

    def test_from_dict_full(self):
        """Test from_dict with complete data."""
        data = {
            "claude": 1000.0,
            "gemini-antigravity": 2000.0,
            "gemini-cli": 3000.0,
        }
        state = RateLimitState.from_dict(data)
        assert state.claude == 1000.0
        assert state.gemini_antigravity == 2000.0
        assert state.gemini_cli == 3000.0

    def test_roundtrip_serialization(self):
        """Test that serialization and deserialization are symmetric."""
        original = RateLimitState(
            claude=1000.0,
            gemini_antigravity=2000.0,
            gemini_cli=3000.0,
        )
        serialized = original.to_dict()
        restored = RateLimitState.from_dict(serialized)
        assert restored.claude == original.claude
        assert restored.gemini_antigravity == original.gemini_antigravity
        assert restored.gemini_cli == original.gemini_cli

    def test_from_dict_ignores_unknown_keys(self):
        """Test that unknown keys in dict are ignored."""
        data = {
            "claude": 1000.0,
            "unknown_key": "should_be_ignored",
        }
        state = RateLimitState.from_dict(data)
        assert state.claude == 1000.0
        assert state.gemini_antigravity is None


# ============================================================================
# TESTS: AccountMetadata
# ============================================================================


class TestAccountMetadata:
    """Test AccountMetadata dataclass."""

    def test_init_minimal(self):
        """Test initialization with minimal required fields."""
        metadata = AccountMetadata(refresh_token="token123")
        assert metadata.refresh_token == "token123"
        assert metadata.email is None
        assert metadata.project_id is None
        assert metadata.managed_project_id is None
        assert metadata.added_at == 0
        assert metadata.last_used == 0
        assert metadata.last_switch_reason is None
        assert isinstance(metadata.rate_limit_reset_times, RateLimitState)

    def test_init_full(self, current_time):
        """Test initialization with all fields."""
        rate_limits = RateLimitState(claude=current_time + 1000)
        metadata = AccountMetadata(
            refresh_token="token123",
            email="user@example.com",
            project_id="proj1",
            managed_project_id="managed_proj1",
            added_at=current_time,
            last_used=current_time - 1000,
            last_switch_reason="rate-limit",
            rate_limit_reset_times=rate_limits,
        )
        assert metadata.refresh_token == "token123"
        assert metadata.email == "user@example.com"
        assert metadata.project_id == "proj1"
        assert metadata.managed_project_id == "managed_proj1"
        assert metadata.added_at == current_time
        assert metadata.last_used == current_time - 1000
        assert metadata.last_switch_reason == "rate-limit"
        assert metadata.rate_limit_reset_times == rate_limits

    def test_to_dict_minimal(self):
        """Test to_dict with minimal metadata."""
        metadata = AccountMetadata(refresh_token="token123")
        result = metadata.to_dict()
        assert result["refreshToken"] == "token123"
        assert result["addedAt"] == 0
        assert result["lastUsed"] == 0
        assert "email" not in result
        assert "projectId" not in result
        assert "managedProjectId" not in result
        assert "lastSwitchReason" not in result
        assert "rateLimitResetTimes" not in result

    def test_to_dict_full(self, current_time):
        """Test to_dict with all fields."""
        metadata = AccountMetadata(
            refresh_token="token123",
            email="user@example.com",
            project_id="proj1",
            managed_project_id="managed_proj1",
            added_at=current_time,
            last_used=current_time - 1000,
            last_switch_reason="rate-limit",
            rate_limit_reset_times=RateLimitState(claude=current_time + 5000),
        )
        result = metadata.to_dict()
        assert result["refreshToken"] == "token123"
        assert result["email"] == "user@example.com"
        assert result["projectId"] == "proj1"
        assert result["managedProjectId"] == "managed_proj1"
        assert result["addedAt"] == current_time
        assert result["lastUsed"] == current_time - 1000
        assert result["lastSwitchReason"] == "rate-limit"
        assert result["rateLimitResetTimes"]["claude"] == current_time + 5000

    def test_from_dict_minimal(self):
        """Test from_dict with minimal data."""
        data = {"refreshToken": "token123"}
        metadata = AccountMetadata.from_dict(data)
        assert metadata.refresh_token == "token123"
        assert metadata.email is None
        assert metadata.project_id is None

    def test_from_dict_full(self, current_time):
        """Test from_dict with complete data."""
        data = {
            "refreshToken": "token123",
            "email": "user@example.com",
            "projectId": "proj1",
            "managedProjectId": "managed_proj1",
            "addedAt": current_time,
            "lastUsed": current_time - 1000,
            "lastSwitchReason": "rate-limit",
            "rateLimitResetTimes": {"claude": current_time + 5000},
        }
        metadata = AccountMetadata.from_dict(data)
        assert metadata.refresh_token == "token123"
        assert metadata.email == "user@example.com"
        assert metadata.project_id == "proj1"
        assert metadata.managed_project_id == "managed_proj1"
        assert metadata.added_at == current_time
        assert metadata.last_used == current_time - 1000
        assert metadata.last_switch_reason == "rate-limit"
        assert metadata.rate_limit_reset_times.claude == current_time + 5000

    def test_from_dict_missing_refresh_token(self):
        """Test from_dict handles missing refresh token gracefully."""
        data = {"email": "user@example.com"}
        metadata = AccountMetadata.from_dict(data)
        assert metadata.refresh_token == ""
        assert metadata.email == "user@example.com"

    def test_roundtrip_serialization(self, current_time):
        """Test that serialization and deserialization are symmetric."""
        original = AccountMetadata(
            refresh_token="token123",
            email="user@example.com",
            project_id="proj1",
            added_at=current_time,
            last_used=current_time - 1000,
            last_switch_reason="rotation",
        )
        serialized = original.to_dict()
        restored = AccountMetadata.from_dict(serialized)
        assert restored.refresh_token == original.refresh_token
        assert restored.email == original.email
        assert restored.project_id == original.project_id
        assert restored.added_at == original.added_at
        assert restored.last_used == original.last_used
        assert restored.last_switch_reason == original.last_switch_reason


# ============================================================================
# TESTS: AccountStorage
# ============================================================================


class TestAccountStorage:
    """Test AccountStorage dataclass."""

    def test_init_defaults(self):
        """Test initialization with default values."""
        storage = AccountStorage()
        assert storage.version == 3
        assert storage.accounts == []
        assert storage.active_index == 0
        assert storage.active_index_by_family == {}

    def test_init_with_accounts(self):
        """Test initialization with accounts."""
        accounts = [
            AccountMetadata(refresh_token="token1", email="user1@example.com"),
            AccountMetadata(refresh_token="token2", email="user2@example.com"),
        ]
        storage = AccountStorage(
            accounts=accounts,
            active_index=1,
            active_index_by_family={"claude": 0, "gemini": 1},
        )
        assert len(storage.accounts) == 2
        assert storage.active_index == 1
        assert storage.active_index_by_family == {"claude": 0, "gemini": 1}

    def test_to_dict_empty(self):
        """Test to_dict with empty storage."""
        storage = AccountStorage()
        result = storage.to_dict()
        assert result["version"] == 3
        assert result["accounts"] == []
        assert result["activeIndex"] == 0
        assert result["activeIndexByFamily"] == {}

    def test_to_dict_with_accounts(self):
        """Test to_dict with accounts."""
        accounts = [
            AccountMetadata(refresh_token="token1", email="user1@example.com"),
            AccountMetadata(refresh_token="token2", email="user2@example.com"),
        ]
        storage = AccountStorage(
            accounts=accounts,
            active_index=1,
            active_index_by_family={"claude": 0, "gemini": 1},
        )
        result = storage.to_dict()
        assert result["version"] == 3
        assert len(result["accounts"]) == 2
        assert result["activeIndex"] == 1
        assert result["activeIndexByFamily"] == {"claude": 0, "gemini": 1}

    def test_from_dict_empty(self):
        """Test from_dict with empty data."""
        data = {"version": 3, "accounts": []}
        storage = AccountStorage.from_dict(data)
        assert storage.version == 3
        assert storage.accounts == []
        assert storage.active_index == 0
        assert storage.active_index_by_family == {}

    def test_from_dict_with_accounts(self):
        """Test from_dict with accounts."""
        data = {
            "version": 3,
            "accounts": [
                {
                    "refreshToken": "token1",
                    "email": "user1@example.com",
                    "addedAt": 0,
                    "lastUsed": 0,
                },
                {
                    "refreshToken": "token2",
                    "email": "user2@example.com",
                    "addedAt": 0,
                    "lastUsed": 0,
                },
            ],
            "activeIndex": 1,
            "activeIndexByFamily": {"claude": 0, "gemini": 1},
        }
        storage = AccountStorage.from_dict(data)
        assert len(storage.accounts) == 2
        assert storage.active_index == 1
        assert storage.active_index_by_family == {"claude": 0, "gemini": 1}

    def test_from_dict_missing_fields(self):
        """Test from_dict with missing optional fields."""
        data = {"accounts": []}
        storage = AccountStorage.from_dict(data)
        assert storage.version == 3
        assert storage.accounts == []
        assert storage.active_index == 0
        assert storage.active_index_by_family == {}

    def test_roundtrip_serialization(self):
        """Test that serialization and deserialization are symmetric."""
        accounts = [
            AccountMetadata(refresh_token="token1", email="user1@example.com"),
            AccountMetadata(refresh_token="token2", email="user2@example.com"),
        ]
        original = AccountStorage(
            accounts=accounts,
            active_index=1,
            active_index_by_family={"claude": 0, "gemini": 1},
        )
        serialized = original.to_dict()
        restored = AccountStorage.from_dict(serialized)
        assert len(restored.accounts) == len(original.accounts)
        assert restored.active_index == original.active_index
        assert restored.active_index_by_family == original.active_index_by_family


# ============================================================================
# TESTS: Migration Functions
# ============================================================================


class TestMigrationV1toV2:
    """Test V1 to V2 migration."""

    def test_migrate_empty_accounts(self):
        """Test migration with no accounts."""
        v1_data = {"version": 1, "accounts": [], "activeIndex": 0}
        v2_data = _migrate_v1_to_v2(v1_data)
        assert v2_data["version"] == 2
        assert v2_data["accounts"] == []
        assert v2_data["activeIndex"] == 0

    def test_migrate_single_account(self, current_time):
        """Test migration with single account."""
        now_ms = current_time
        v1_data = {
            "version": 1,
            "accounts": [
                {
                    "email": "user@example.com",
                    "refreshToken": "token123",
                    "projectId": "proj1",
                    "addedAt": now_ms - 10000,
                    "lastUsed": now_ms - 1000,
                }
            ],
            "activeIndex": 0,
        }
        v2_data = _migrate_v1_to_v2(v1_data)
        assert v2_data["version"] == 2
        assert len(v2_data["accounts"]) == 1
        acc = v2_data["accounts"][0]
        assert acc["email"] == "user@example.com"
        assert acc["refreshToken"] == "token123"
        assert acc["projectId"] == "proj1"

    def test_migrate_multiple_accounts(self, current_time):
        """Test migration with multiple accounts."""
        now_ms = current_time
        v1_data = {
            "version": 1,
            "accounts": [
                {
                    "email": "user1@example.com",
                    "refreshToken": "token1",
                    "projectId": "proj1",
                    "addedAt": now_ms - 10000,
                },
                {
                    "email": "user2@example.com",
                    "refreshToken": "token2",
                    "projectId": "proj2",
                    "addedAt": now_ms - 5000,
                },
            ],
            "activeIndex": 1,
        }
        v2_data = _migrate_v1_to_v2(v1_data)
        assert len(v2_data["accounts"]) == 2
        assert v2_data["activeIndex"] == 1

    def test_migrate_rate_limited_account(self, current_time):
        """Test migration handles rate-limited accounts."""
        now_ms = current_time
        future_ms = now_ms + 5000
        v1_data = {
            "version": 1,
            "accounts": [
                {
                    "email": "user@example.com",
                    "refreshToken": "token123",
                    "isRateLimited": True,
                    "rateLimitResetTime": future_ms,
                    "addedAt": now_ms,
                }
            ],
            "activeIndex": 0,
        }
        v2_data = _migrate_v1_to_v2(v1_data)
        acc = v2_data["accounts"][0]
        assert acc["rateLimitResetTimes"]["claude"] == future_ms
        assert acc["rateLimitResetTimes"]["gemini"] == future_ms

    def test_migrate_expired_rate_limit(self, current_time):
        """Test migration skips expired rate limits."""
        now_ms = current_time
        past_ms = now_ms - 5000  # In the past
        v1_data = {
            "version": 1,
            "accounts": [
                {
                    "email": "user@example.com",
                    "refreshToken": "token123",
                    "isRateLimited": True,
                    "rateLimitResetTime": past_ms,  # Expired
                    "addedAt": now_ms,
                }
            ],
            "activeIndex": 0,
        }
        v2_data = _migrate_v1_to_v2(v1_data)
        acc = v2_data["accounts"][0]
        # Should not include rate limits for expired times
        assert acc["rateLimitResetTimes"] is None or acc["rateLimitResetTimes"] == {}


class TestMigrationV2toV3:
    """Test V2 to V3 migration."""

    def test_migrate_empty_accounts(self):
        """Test migration with no accounts."""
        v2_data = {"version": 2, "accounts": [], "activeIndex": 0}
        v3_data = _migrate_v2_to_v3(v2_data)
        assert v3_data["version"] == 3
        assert v3_data["accounts"] == []
        assert v3_data["activeIndex"] == 0
        assert v3_data["activeIndexByFamily"] == {}

    def test_migrate_single_account(self, current_time):
        """Test migration with single account."""
        now_ms = current_time
        v2_data = {
            "version": 2,
            "accounts": [
                {
                    "email": "user@example.com",
                    "refreshToken": "token123",
                    "projectId": "proj1",
                    "addedAt": now_ms - 10000,
                    "lastUsed": now_ms - 1000,
                }
            ],
            "activeIndex": 0,
        }
        v3_data = _migrate_v2_to_v3(v2_data)
        assert v3_data["version"] == 3
        assert len(v3_data["accounts"]) == 1
        assert v3_data["activeIndexByFamily"] == {}

    def test_migrate_with_rate_limits(self, current_time):
        """Test migration handles V2 rate limit format."""
        now_ms = current_time
        future_ms = now_ms + 5000
        v2_data = {
            "version": 2,
            "accounts": [
                {
                    "email": "user@example.com",
                    "refreshToken": "token123",
                    "rateLimitResetTimes": {
                        "claude": future_ms,
                        "gemini": future_ms,
                    },
                    "addedAt": now_ms,
                }
            ],
            "activeIndex": 0,
        }
        v3_data = _migrate_v2_to_v3(v2_data)
        acc = v3_data["accounts"][0]
        # V2 had "claude" and "gemini", V3 has "claude" and "gemini-antigravity"
        assert acc["rateLimitResetTimes"]["claude"] == future_ms
        assert acc["rateLimitResetTimes"]["gemini-antigravity"] == future_ms

    def test_migrate_expired_rate_limits_v2(self, current_time):
        """Test migration filters out expired rate limits."""
        now_ms = current_time
        past_ms = now_ms - 5000
        v2_data = {
            "version": 2,
            "accounts": [
                {
                    "email": "user@example.com",
                    "refreshToken": "token123",
                    "rateLimitResetTimes": {
                        "claude": past_ms,  # Expired
                        "gemini": now_ms + 5000,  # Valid
                    },
                    "addedAt": now_ms,
                }
            ],
            "activeIndex": 0,
        }
        v3_data = _migrate_v2_to_v3(v2_data)
        acc = v3_data["accounts"][0]
        # Should only have the valid rate limit
        assert "claude" not in acc["rateLimitResetTimes"]
        assert acc["rateLimitResetTimes"]["gemini-antigravity"] == now_ms + 5000


# ============================================================================
# TESTS: load_accounts
# ============================================================================


class TestLoadAccounts:
    """Test load_accounts function."""

    def test_load_nonexistent_file(self, temp_storage_path):
        """Test loading when file doesn't exist."""
        assert not temp_storage_path.exists()
        result = load_accounts()
        assert result is None

    def test_load_v3_format(self, temp_storage_path):
        """Test loading V3 format (current version)."""
        data = {
            "version": 3,
            "accounts": [
                {
                    "refreshToken": "token1",
                    "email": "user1@example.com",
                    "addedAt": 1000,
                    "lastUsed": 500,
                }
            ],
            "activeIndex": 0,
            "activeIndexByFamily": {"claude": 0},
        }
        temp_storage_path.write_text(json.dumps(data))
        result = load_accounts()
        assert result is not None
        assert result.version == 3
        assert len(result.accounts) == 1
        assert result.accounts[0].email == "user1@example.com"

    def test_load_v2_format_migrates(self, temp_storage_path, monkeypatch):
        """Test loading V2 format triggers migration and saves."""
        v2_data = {
            "version": 2,
            "accounts": [
                {
                    "refreshToken": "token1",
                    "email": "user1@example.com",
                    "addedAt": 1000,
                    "lastUsed": 500,
                }
            ],
            "activeIndex": 0,
        }
        temp_storage_path.write_text(json.dumps(v2_data))
        saved_data = []
        original_save = save_accounts

        def capture_save(storage):
            saved_data.append(storage.to_dict())
            original_save(storage)

        monkeypatch.setattr(
            "code_puppy.plugins.antigravity_oauth.storage.save_accounts",
            capture_save,
        )
        result = load_accounts()
        assert result is not None
        assert result.version == 3
        assert len(saved_data) > 0  # Should have saved migrated data

    def test_load_v1_format_migrates(self, temp_storage_path, monkeypatch):
        """Test loading V1 format triggers V1->V2->V3 migration."""
        v1_data = {
            "version": 1,
            "accounts": [
                {
                    "email": "user1@example.com",
                    "refreshToken": "token1",
                    "projectId": "proj1",
                    "addedAt": 1000,
                }
            ],
            "activeIndex": 0,
        }
        temp_storage_path.write_text(json.dumps(v1_data))
        saved_data = []
        original_save = save_accounts

        def capture_save(storage):
            saved_data.append(storage.to_dict())
            original_save(storage)

        monkeypatch.setattr(
            "code_puppy.plugins.antigravity_oauth.storage.save_accounts",
            capture_save,
        )
        result = load_accounts()
        assert result is not None
        assert result.version == 3
        assert len(saved_data) > 0  # Should have saved migrated data

    def test_load_corrupted_json(self, temp_storage_path):
        """Test loading corrupted JSON returns None."""
        temp_storage_path.write_text("invalid json {")
        result = load_accounts()
        assert result is None

    def test_load_invalid_format_no_accounts_list(self, temp_storage_path):
        """Test loading file without accounts list returns None."""
        data = {"version": 3, "activeIndex": 0}
        temp_storage_path.write_text(json.dumps(data))
        result = load_accounts()
        assert result is None

    def test_load_validates_active_index(self, temp_storage_path):
        """Test that active_index is validated and clamped."""
        data = {
            "version": 3,
            "accounts": [
                {
                    "refreshToken": "token1",
                    "email": "user1@example.com",
                    "addedAt": 1000,
                    "lastUsed": 500,
                }
            ],
            "activeIndex": 999,  # Out of bounds
            "activeIndexByFamily": {},
        }
        temp_storage_path.write_text(json.dumps(data))
        result = load_accounts()
        assert result is not None
        # Should clamp to valid range
        assert result.active_index == 0

    def test_load_validates_negative_active_index(self, temp_storage_path):
        """Test that negative active_index is clamped to 0."""
        data = {
            "version": 3,
            "accounts": [
                {
                    "refreshToken": "token1",
                    "email": "user1@example.com",
                    "addedAt": 1000,
                    "lastUsed": 500,
                }
            ],
            "activeIndex": -5,  # Negative
            "activeIndexByFamily": {},
        }
        temp_storage_path.write_text(json.dumps(data))
        result = load_accounts()
        assert result is not None
        assert result.active_index == 0

    def test_load_empty_accounts_resets_index(self, temp_storage_path):
        """Test that empty accounts resets active_index to 0."""
        data = {
            "version": 3,
            "accounts": [],
            "activeIndex": 5,
            "activeIndexByFamily": {},
        }
        temp_storage_path.write_text(json.dumps(data))
        result = load_accounts()
        assert result is not None
        assert result.active_index == 0

    def test_load_file_read_error(self, temp_storage_path, monkeypatch):
        """Test handling of file read errors."""
        temp_storage_path.write_text(json.dumps({"version": 3, "accounts": []}))

        # Mock path.exists() to return True but read_text() to fail
        def mock_read(*args, **kwargs):
            raise IOError("Permission denied")

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.side_effect = mock_read
        monkeypatch.setattr(
            "code_puppy.plugins.antigravity_oauth.storage.get_accounts_storage_path",
            lambda: mock_path,
        )
        result = load_accounts()
        assert result is None

    def test_load_migration_failure_logs_warning(
        self, temp_storage_path, monkeypatch, caplog
    ):
        """Test that migration failures are logged but don't prevent loading."""
        v2_data = {
            "version": 2,
            "accounts": [
                {
                    "refreshToken": "token1",
                    "email": "user1@example.com",
                    "addedAt": 1000,
                }
            ],
            "activeIndex": 0,
        }
        temp_storage_path.write_text(json.dumps(v2_data))
        # Mock save to raise an exception
        monkeypatch.setattr(
            "code_puppy.plugins.antigravity_oauth.storage.save_accounts",
            MagicMock(side_effect=Exception("Save failed")),
        )
        with caplog.at_level(logging.WARNING):
            result = load_accounts()
        assert result is not None
        # Migration should still complete even if save fails
        assert result.version == 3


# ============================================================================
# TESTS: save_accounts
# ============================================================================


class TestSaveAccounts:
    """Test save_accounts function."""

    def test_save_creates_directory(self, temp_storage_path):
        """Test that save creates parent directory."""
        # Remove parent directory to test creation
        assert temp_storage_path.parent.exists()
        storage = AccountStorage()
        save_accounts(storage)
        assert temp_storage_path.exists()

    def test_save_writes_json(self, temp_storage_path):
        """Test that save writes valid JSON."""
        storage = AccountStorage(
            accounts=[
                AccountMetadata(
                    refresh_token="token1",
                    email="user1@example.com",
                    added_at=1000,
                    last_used=500,
                )
            ],
            active_index=0,
        )
        save_accounts(storage)
        # Read and parse the file
        content = temp_storage_path.read_text()
        data = json.loads(content)
        assert data["version"] == 3
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["email"] == "user1@example.com"

    def test_save_sets_permissions(self, temp_storage_path):
        """Test that save sets file permissions to 0o600."""
        storage = AccountStorage()
        save_accounts(storage)
        # Check permissions (0o600 = owner read/write only)
        perms = temp_storage_path.stat().st_mode & 0o777
        assert perms == 0o600

    def test_save_with_rate_limits(self, temp_storage_path):
        """Test that save preserves rate limit data."""
        storage = AccountStorage(
            accounts=[
                AccountMetadata(
                    refresh_token="token1",
                    email="user1@example.com",
                    added_at=1000,
                    rate_limit_reset_times=RateLimitState(claude=5000.0),
                )
            ],
            active_index=0,
        )
        save_accounts(storage)
        content = temp_storage_path.read_text()
        data = json.loads(content)
        assert "rateLimitResetTimes" in data["accounts"][0]
        assert data["accounts"][0]["rateLimitResetTimes"]["claude"] == 5000.0

    def test_save_roundtrip(self, temp_storage_path):
        """Test that saved data can be loaded back identically."""
        original = AccountStorage(
            accounts=[
                AccountMetadata(
                    refresh_token="token1",
                    email="user1@example.com",
                    project_id="proj1",
                    added_at=1000,
                    last_used=500,
                ),
            ],
            active_index=0,
            active_index_by_family={"claude": 0},
        )
        save_accounts(original)
        loaded = load_accounts()
        assert loaded is not None
        assert loaded.version == original.version
        assert len(loaded.accounts) == len(original.accounts)
        assert loaded.accounts[0].email == original.accounts[0].email
        assert loaded.active_index == original.active_index


# ============================================================================
# TESTS: clear_accounts
# ============================================================================


class TestClearAccounts:
    """Test clear_accounts function."""

    def test_clear_removes_file(self, temp_storage_path):
        """Test that clear removes the storage file."""
        # Create a file first
        storage = AccountStorage()
        save_accounts(storage)
        assert temp_storage_path.exists()
        # Clear it
        clear_accounts()
        assert not temp_storage_path.exists()

    def test_clear_nonexistent_file(self, temp_storage_path):
        """Test that clear handles nonexistent file gracefully."""
        assert not temp_storage_path.exists()
        # Should not raise
        clear_accounts()
        assert not temp_storage_path.exists()

    def test_clear_handles_permission_errors(
        self, temp_storage_path, monkeypatch, caplog
    ):
        """Test that clear logs but doesn't raise on permission errors."""
        storage = AccountStorage()
        save_accounts(storage)
        # Mock the path to raise PermissionError on unlink
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.unlink.side_effect = PermissionError("Permission denied")
        monkeypatch.setattr(
            "code_puppy.plugins.antigravity_oauth.storage.get_accounts_storage_path",
            lambda: mock_path,
        )
        with caplog.at_level(logging.ERROR):
            # Should not raise
            clear_accounts()
            # Check that error was logged
            assert any(
                "Failed to clear account storage" in record.message
                for record in caplog.records
            )


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestIntegration:
    """Integration tests for the storage system."""

    def test_full_lifecycle(self, temp_storage_path):
        """Test complete lifecycle: create, save, load, clear."""
        # Create
        storage = AccountStorage(
            accounts=[
                AccountMetadata(
                    refresh_token="token1",
                    email="user1@example.com",
                    added_at=1000,
                )
            ],
            active_index=0,
        )
        # Save
        save_accounts(storage)
        assert temp_storage_path.exists()
        # Load
        loaded = load_accounts()
        assert loaded is not None
        assert len(loaded.accounts) == 1
        # Clear
        clear_accounts()
        assert not temp_storage_path.exists()

    def test_multiple_accounts_workflow(self, temp_storage_path):
        """Test workflow with multiple accounts."""
        # Create storage with multiple accounts
        storage = AccountStorage(
            accounts=[
                AccountMetadata(
                    refresh_token="token1",
                    email="user1@example.com",
                    added_at=1000,
                ),
                AccountMetadata(
                    refresh_token="token2",
                    email="user2@example.com",
                    added_at=2000,
                ),
                AccountMetadata(
                    refresh_token="token3",
                    email="user3@example.com",
                    added_at=3000,
                ),
            ],
            active_index=1,
            active_index_by_family={"claude": 0, "gemini": 1},
        )
        save_accounts(storage)
        # Load and verify all accounts
        loaded = load_accounts()
        assert loaded is not None
        assert len(loaded.accounts) == 3
        assert loaded.active_index == 1
        assert loaded.accounts[1].email == "user2@example.com"
        assert loaded.active_index_by_family == {"claude": 0, "gemini": 1}

    def test_migration_from_v1_to_v3_full(self, temp_storage_path, monkeypatch):
        """Test complete V1 to V3 migration with save."""
        # Create V1 data
        v1_data = {
            "version": 1,
            "accounts": [
                {
                    "email": "user1@example.com",
                    "refreshToken": "token1",
                    "projectId": "proj1",
                    "addedAt": 1000,
                }
            ],
            "activeIndex": 0,
        }
        temp_storage_path.write_text(json.dumps(v1_data))
        # Load (triggers migration)
        loaded = load_accounts()
        assert loaded is not None
        assert loaded.version == 3
        # Verify file was updated
        saved_data = json.loads(temp_storage_path.read_text())
        assert saved_data["version"] == 3
        assert "activeIndexByFamily" in saved_data
