"""Comprehensive test coverage for Antigravity multi-account manager."""

from __future__ import annotations

import time

import pytest

from code_puppy.plugins.antigravity_oauth.accounts import (
    AccountManager,
    ManagedAccount,
    _clear_expired_rate_limits,
    _get_quota_key,
    _is_rate_limited_for_family,
    _is_rate_limited_for_quota_key,
    _now_ms,
)
from code_puppy.plugins.antigravity_oauth.storage import (
    AccountMetadata,
    AccountStorage,
    RateLimitState,
)
from code_puppy.plugins.antigravity_oauth.token import RefreshParts

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_now(monkeypatch):
    """Mock the current time for consistent testing."""
    base_time = 1000000.0  # Arbitrary base time
    call_count = [0]

    def mock_time():
        call_count[0] += 1
        return base_time + (call_count[0] * 0.01)  # Increment slightly each call

    monkeypatch.setattr(
        "code_puppy.plugins.antigravity_oauth.accounts.time.time", mock_time
    )
    return base_time


@pytest.fixture
def sample_storage():
    """Create a sample AccountStorage with multiple accounts."""
    now = time.time() * 1000
    return AccountStorage(
        version=3,
        accounts=[
            AccountMetadata(
                refresh_token="token1|proj1",
                email="user1@example.com",
                project_id="proj1",
                added_at=now - 10000,
                last_used=now - 1000,
                rate_limit_reset_times=RateLimitState(),
            ),
            AccountMetadata(
                refresh_token="token2|proj2",
                email="user2@example.com",
                project_id="proj2",
                added_at=now - 5000,
                last_used=now - 500,
                rate_limit_reset_times=RateLimitState(),
            ),
            AccountMetadata(
                refresh_token="token3|proj3",
                email="user3@example.com",
                project_id="proj3",
                added_at=now,
                last_used=0,
                rate_limit_reset_times=RateLimitState(),
            ),
        ],
        active_index=0,
        active_index_by_family={"claude": 0, "gemini": 1},
    )


@pytest.fixture
def mock_load_accounts(sample_storage, monkeypatch):
    """Mock load_accounts to return sample storage."""

    def fake_load():
        return sample_storage

    monkeypatch.setattr(
        "code_puppy.plugins.antigravity_oauth.accounts.load_accounts",
        fake_load,
    )
    return sample_storage


@pytest.fixture
def mock_save_accounts(monkeypatch):
    """Mock save_accounts to do nothing."""

    def fake_save(storage):
        pass

    monkeypatch.setattr(
        "code_puppy.plugins.antigravity_oauth.accounts.save_accounts",
        fake_save,
    )


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


class TestHelperFunctions:
    """Test internal helper functions."""

    def test_now_ms_returns_milliseconds(self):
        """Test that _now_ms returns time in milliseconds."""
        now_ms = _now_ms()
        # Should be around current time * 1000
        assert now_ms > 0
        assert now_ms > 1000000000000  # Should be in milliseconds since epoch

    def test_get_quota_key_claude(self):
        """Test quota key for Claude models."""
        key = _get_quota_key("claude", "antigravity")
        assert key == "claude"

    def test_get_quota_key_gemini_antigravity(self):
        """Test quota key for Gemini with antigravity header style."""
        key = _get_quota_key("gemini", "antigravity")
        assert key == "gemini-antigravity"

    def test_get_quota_key_gemini_cli(self):
        """Test quota key for Gemini with CLI header style."""
        key = _get_quota_key("gemini", "gemini-cli")
        assert key == "gemini-cli"

    def test_is_rate_limited_for_quota_key_not_limited(self):
        """Test account that is not rate limited."""
        account = ManagedAccount(
            index=0,
            email="test@example.com",
            added_at=_now_ms(),
            last_used=0,
            parts=RefreshParts(refresh_token="token"),
            rate_limit_reset_times={},
        )
        assert not _is_rate_limited_for_quota_key(account, "claude")

    def test_is_rate_limited_for_quota_key_limited(self):
        """Test account that is rate limited."""
        now = _now_ms()
        account = ManagedAccount(
            index=0,
            email="test@example.com",
            added_at=now,
            last_used=0,
            parts=RefreshParts(refresh_token="token"),
            rate_limit_reset_times={"claude": now + 5000},  # 5 seconds in future
        )
        assert _is_rate_limited_for_quota_key(account, "claude")

    def test_is_rate_limited_for_quota_key_expired(self):
        """Test account with expired rate limit."""
        now = _now_ms()
        account = ManagedAccount(
            index=0,
            email="test@example.com",
            added_at=now,
            last_used=0,
            parts=RefreshParts(refresh_token="token"),
            rate_limit_reset_times={"claude": now - 1000},  # 1 second in past
        )
        assert not _is_rate_limited_for_quota_key(account, "claude")

    def test_is_rate_limited_for_family_claude(self):
        """Test rate limiting for Claude model family."""
        now = _now_ms()
        # Claude is rate limited when claude key is limited
        account = ManagedAccount(
            index=0,
            email="test@example.com",
            added_at=now,
            last_used=0,
            parts=RefreshParts(refresh_token="token"),
            rate_limit_reset_times={"claude": now + 5000},
        )
        assert _is_rate_limited_for_family(account, "claude")

    def test_is_rate_limited_for_family_gemini_both_required(self):
        """Test that both Gemini pools must be rate limited to block account."""
        now = _now_ms()

        # Only gemini-antigravity limited - should not be blocked
        account = ManagedAccount(
            index=0,
            email="test@example.com",
            added_at=now,
            last_used=0,
            parts=RefreshParts(refresh_token="token"),
            rate_limit_reset_times={"gemini-antigravity": now + 5000},
        )
        assert not _is_rate_limited_for_family(account, "gemini")

        # Both limited - should be blocked
        account.rate_limit_reset_times["gemini-cli"] = now + 5000
        assert _is_rate_limited_for_family(account, "gemini")

    def test_clear_expired_rate_limits(self):
        """Test clearing expired rate limits."""
        now = _now_ms()
        account = ManagedAccount(
            index=0,
            email="test@example.com",
            added_at=now,
            last_used=0,
            parts=RefreshParts(refresh_token="token"),
            rate_limit_reset_times={
                "claude": now - 1000,  # Expired
                "gemini-antigravity": now + 5000,  # Not expired
            },
        )

        _clear_expired_rate_limits(account)

        assert "claude" not in account.rate_limit_reset_times
        assert "gemini-antigravity" in account.rate_limit_reset_times


# ============================================================================
# ACCOUNT MANAGER INITIALIZATION TESTS
# ============================================================================


class TestAccountManagerInitialization:
    """Test AccountManager initialization scenarios."""

    def test_init_with_empty_storage(self):
        """Test initialization with no storage."""
        manager = AccountManager(initial_refresh_token="token|proj", stored=None)
        assert manager.account_count == 1
        account = manager.get_current_account_for_family("claude")
        assert account is not None
        assert account.parts.refresh_token == "token"
        assert account.parts.project_id == "proj"

    def test_init_with_no_token_no_storage(self):
        """Test initialization with no token and no storage."""
        manager = AccountManager(initial_refresh_token="", stored=None)
        assert manager.account_count == 0

    def test_init_from_storage_with_accounts(self, sample_storage):
        """Test initialization from storage with accounts."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        assert manager.account_count == 3

        # Verify accounts are loaded
        for i, account in enumerate(manager.get_accounts_snapshot()):
            assert account.index == i
            assert account.email in [
                "user1@example.com",
                "user2@example.com",
                "user3@example.com",
            ]

    def test_init_from_storage_preserves_active_indices(self, sample_storage):
        """Test that active indices are preserved from storage."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)

        assert manager._current_index_by_family["claude"] == 0
        assert manager._current_index_by_family["gemini"] == 1

    def test_init_from_storage_loads_rate_limits(self):
        """Test that rate limits are loaded from storage."""
        now = time.time() * 1000
        storage = AccountStorage(
            version=3,
            accounts=[
                AccountMetadata(
                    refresh_token="token|proj",
                    email="test@example.com",
                    added_at=now,
                    last_used=0,
                    rate_limit_reset_times=RateLimitState(
                        claude=now + 5000,
                        gemini_antigravity=now + 3000,
                    ),
                )
            ],
            active_index=0,
        )

        manager = AccountManager(initial_refresh_token="", stored=storage)
        account = manager.get_current_account_for_family("claude")
        assert account is not None
        assert account.rate_limit_reset_times["claude"] == now + 5000
        assert account.rate_limit_reset_times["gemini-antigravity"] == now + 3000

    def test_load_from_disk(self, mock_load_accounts, mock_save_accounts):
        """Test loading from disk."""
        manager = AccountManager.load_from_disk()
        assert manager.account_count == 3


# ============================================================================
# ACCOUNT SELECTION TESTS
# ============================================================================


class TestAccountSelection:
    """Test account selection and rotation logic."""

    def test_get_current_account_for_family(self, sample_storage):
        """Test getting the current account for a model family."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)

        claude_account = manager.get_current_account_for_family("claude")
        assert claude_account is not None
        assert claude_account.index == 0

        gemini_account = manager.get_current_account_for_family("gemini")
        assert gemini_account is not None
        assert gemini_account.index == 1

    def test_get_current_or_next_available(self, sample_storage):
        """Test getting next available account when current is rate limited."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)

        # Get current account
        current = manager.get_current_or_next_for_family("claude")
        assert current is not None
        assert current.index == 0
        assert current.last_used > 0  # Should update last_used

    def test_get_next_account_when_current_rate_limited(self, sample_storage):
        """Test that we get next account when current is rate limited."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)

        # Rate limit the first account for claude
        current = manager.get_current_account_for_family("claude")
        assert current is not None
        manager.mark_rate_limited(current, 5000, "claude", "antigravity")

        # Now get_current_or_next should return a different account
        next_account = manager.get_current_or_next_for_family("claude")
        assert next_account is not None
        assert next_account.index != 0

    def test_round_robin_selection(self, sample_storage):
        """Test round-robin account selection."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)

        # Rate limit first account
        first = manager.get_current_account_for_family("claude")
        manager.mark_rate_limited(first, 5000, "claude", "antigravity")

        # Get next - should be second
        second = manager.get_current_or_next_for_family("claude")
        assert second is not None
        assert second.index == 1
        assert manager._current_index_by_family["claude"] == 1

        # Rate limit second
        manager.mark_rate_limited(second, 5000, "claude", "antigravity")

        # Get next - should wrap to third
        third = manager.get_current_or_next_for_family("claude")
        assert third is not None
        assert third.index == 2

    def test_no_available_accounts(self, sample_storage):
        """Test behavior when all accounts are rate limited."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)

        # Rate limit all accounts
        for account in manager.get_accounts_snapshot():
            manager.mark_rate_limited(account, 5000, "claude", "antigravity")

        # Should return None
        result = manager.get_current_or_next_for_family("claude")
        assert result is None


# ============================================================================
# RATE LIMITING TESTS
# ============================================================================


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_mark_rate_limited(self, sample_storage):
        """Test marking an account as rate limited."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        account = manager.get_current_account_for_family("claude")
        assert account is not None

        manager.mark_rate_limited(account, 5000, "claude", "antigravity")

        assert _is_rate_limited_for_quota_key(account, "claude")

    def test_is_rate_limited_for_header_style(self, sample_storage):
        """Test checking rate limit for specific header style."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        account = manager.get_current_account_for_family("gemini")
        assert account is not None

        manager.mark_rate_limited(account, 5000, "gemini", "antigravity")

        assert manager.is_rate_limited_for_header_style(
            account, "gemini", "antigravity"
        )
        assert not manager.is_rate_limited_for_header_style(
            account, "gemini", "gemini-cli"
        )

    def test_get_available_header_style_claude(self, sample_storage):
        """Test getting available header style for Claude."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        account = manager.get_current_account_for_family("claude")
        assert account is not None

        # Initially available
        style = manager.get_available_header_style(account, "claude")
        assert style == "antigravity"

        # Rate limit it
        manager.mark_rate_limited(account, 5000, "claude", "antigravity")
        style = manager.get_available_header_style(account, "claude")
        assert style is None

    def test_get_available_header_style_gemini(self, sample_storage):
        """Test getting available header style for Gemini (with fallback)."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        account = manager.get_current_account_for_family("gemini")
        assert account is not None

        # Initially available
        style = manager.get_available_header_style(account, "gemini")
        assert style == "antigravity"

        # Rate limit antigravity, should fall back to CLI
        manager.mark_rate_limited(account, 5000, "gemini", "antigravity")
        style = manager.get_available_header_style(account, "gemini")
        assert style == "gemini-cli"

        # Rate limit CLI too, should return None
        manager.mark_rate_limited(account, 5000, "gemini", "gemini-cli")
        style = manager.get_available_header_style(account, "gemini")
        assert style is None

    def test_get_min_wait_time_available_now(self, sample_storage):
        """Test wait time when account is available now."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)

        wait_time = manager.get_min_wait_time_for_family("claude")
        assert wait_time == 0

    def test_get_min_wait_time_with_rate_limit(self, sample_storage):
        """Test wait time calculation with rate limits."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)

        # Rate limit ALL accounts for Claude with a long timeout
        for account in manager.get_accounts_snapshot():
            manager.mark_rate_limited(account, 60000, "claude", "antigravity")

        wait_time = manager.get_min_wait_time_for_family("claude")
        # Wait time should be positive when all accounts are rate limited
        # (should be ~60 seconds, but allow for some timing drift)
        assert wait_time > 0, (
            "Wait time should be positive when all accounts are rate limited"
        )
        assert wait_time <= 70000, (
            "Wait time should not exceed rate limit duration by much"
        )

    def test_get_min_wait_time_all_limited(self, sample_storage):
        """Test wait time when all accounts are rate limited."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)

        # Rate limit all with different times
        for i, account in enumerate(manager.get_accounts_snapshot()):
            manager.mark_rate_limited(account, 5000 * (i + 1), "claude", "antigravity")

        wait_time = manager.get_min_wait_time_for_family("claude")
        # Should be minimum - first account
        assert 4900 < wait_time < 5100


# ============================================================================
# ACCOUNT MANAGEMENT TESTS
# ============================================================================


class TestAccountManagement:
    """Test adding and removing accounts."""

    def test_add_account(self):
        """Test adding a new account."""
        manager = AccountManager(initial_refresh_token="", stored=None)
        assert manager.account_count == 0

        account = manager.add_account("refresh_token", "test@example.com", "proj_id")

        assert manager.account_count == 1
        assert account.email == "test@example.com"
        assert account.parts.refresh_token == "refresh_token"
        assert account.parts.project_id == "proj_id"
        assert account.index == 0

    def test_add_multiple_accounts(self):
        """Test adding multiple accounts."""
        manager = AccountManager(initial_refresh_token="", stored=None)

        for i in range(3):
            manager.add_account(f"token{i}", f"user{i}@example.com")

        assert manager.account_count == 3

        # Verify indices
        for i, account in enumerate(manager.get_accounts_snapshot()):
            assert account.index == i

    def test_remove_account(self, sample_storage):
        """Test removing an account."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        assert manager.account_count == 3

        account_to_remove = manager.get_accounts_snapshot()[1]
        result = manager.remove_account(account_to_remove)

        assert result is True
        assert manager.account_count == 2

        # Verify re-indexing
        for i, account in enumerate(manager.get_accounts_snapshot()):
            assert account.index == i

    def test_remove_nonexistent_account(self, sample_storage):
        """Test removing an account that doesn't exist."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        fake_account = ManagedAccount(
            index=99,
            email="fake@example.com",
            added_at=_now_ms(),
            last_used=0,
            parts=RefreshParts(refresh_token="fake"),
        )

        result = manager.remove_account(fake_account)
        assert result is False
        assert manager.account_count == 3

    def test_remove_last_account(self):
        """Test removing the last account."""
        manager = AccountManager(initial_refresh_token="token", stored=None)
        assert manager.account_count == 1

        account = manager.get_accounts_snapshot()[0]
        result = manager.remove_account(account)

        assert result is True
        assert manager.account_count == 0
        assert manager._current_index_by_family["claude"] == -1
        assert manager._current_index_by_family["gemini"] == -1

    def test_remove_account_adjusts_active_indices(self, sample_storage):
        """Test that removing an account adjusts active indices correctly."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        manager._current_index_by_family["claude"] = 2  # Set to third account

        # Remove middle account
        account_to_remove = manager.get_accounts_snapshot()[1]
        manager.remove_account(account_to_remove)

        # Claude index should be adjusted down
        assert manager._current_index_by_family["claude"] == 1


# ============================================================================
# PERSISTENCE TESTS
# ============================================================================


class TestPersistence:
    """Test saving and loading account state."""

    def test_save_to_disk(self, sample_storage, mock_save_accounts):
        """Test saving account state to disk."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)

        # Modify some state
        account = manager.get_current_account_for_family("claude")
        manager.mark_rate_limited(account, 5000, "claude", "antigravity")

        # Save should not raise
        manager.save_to_disk()

    def test_save_includes_rate_limits(self, sample_storage, monkeypatch):
        """Test that saving includes rate limit state."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        account = manager.get_current_account_for_family("claude")
        manager.mark_rate_limited(account, 5000, "claude", "antigravity")

        # Capture the saved storage
        saved_storage = None

        def capture_save(storage):
            nonlocal saved_storage
            saved_storage = storage

        monkeypatch.setattr(
            "code_puppy.plugins.antigravity_oauth.accounts.save_accounts",
            capture_save,
        )

        manager.save_to_disk()

        assert saved_storage is not None
        assert len(saved_storage.accounts) == 3
        # First account should have rate limit
        assert saved_storage.accounts[0].rate_limit_reset_times.claude is not None

    def test_save_includes_active_indices(self, sample_storage, monkeypatch):
        """Test that saving includes active family indices."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        manager._current_index_by_family["claude"] = 1
        manager._current_index_by_family["gemini"] = 2

        saved_storage = None

        def capture_save(storage):
            nonlocal saved_storage
            saved_storage = storage

        monkeypatch.setattr(
            "code_puppy.plugins.antigravity_oauth.accounts.save_accounts",
            capture_save,
        )

        manager.save_to_disk()

        assert saved_storage is not None
        assert saved_storage.active_index_by_family["claude"] == 1
        assert saved_storage.active_index_by_family["gemini"] == 2


# ============================================================================
# EDGE CASES AND INTEGRATION TESTS
# ============================================================================


class TestEdgeCases:
    """Test edge cases and integration scenarios."""

    def test_empty_account_manager(self):
        """Test operations on empty manager."""
        manager = AccountManager(initial_refresh_token="", stored=None)

        assert manager.account_count == 0
        assert manager.get_current_account_for_family("claude") is None
        assert manager.get_current_or_next_for_family("claude") is None
        assert manager.get_accounts_snapshot() == []

    def test_family_independent_rate_limiting(self, sample_storage):
        """Test that rate limiting is independent per model family."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        account = manager.get_current_account_for_family("claude")
        assert account is not None

        # Rate limit for Claude only
        manager.mark_rate_limited(account, 5000, "claude", "antigravity")

        # Account should be unavailable for Claude
        assert _is_rate_limited_for_family(account, "claude")

        # But available for Gemini
        assert not _is_rate_limited_for_family(account, "gemini")

    def test_cursor_progression(self, sample_storage):
        """Test that cursor progresses through accounts."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)

        # Get accounts in sequence
        first = manager._get_next_for_family("claude")
        second = manager._get_next_for_family("claude")
        third = manager._get_next_for_family("claude")

        assert first is not None
        assert second is not None
        assert third is not None
        assert first.index != second.index != third.index

    def test_large_account_pool(self):
        """Test with large number of accounts."""
        manager = AccountManager(initial_refresh_token="", stored=None)

        for i in range(100):
            manager.add_account(f"token{i}", f"user{i}@example.com")

        assert manager.account_count == 100

        # Should still work with selection
        account = manager.get_current_account_for_family("claude")
        assert account is not None

    def test_rate_limit_expires_naturally(self, sample_storage, monkeypatch):
        """Test that rate limits naturally expire."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        account = manager.get_current_account_for_family("claude")
        assert account is not None

        now = _now_ms()
        # Rate limit for 100ms
        account.rate_limit_reset_times["claude"] = now + 100

        # Immediately after, should still be limited
        assert _is_rate_limited_for_quota_key(account, "claude")

        # Simulate time passing - monkeypatch _now_ms to return future time
        call_count = [0]

        def mock_time_future():
            call_count[0] += 1
            return now + 200  # 200ms in future

        monkeypatch.setattr(
            "code_puppy.plugins.antigravity_oauth.accounts._now_ms",
            mock_time_future,
        )

        # Clear expired should remove it
        _clear_expired_rate_limits(account)
        assert "claude" not in account.rate_limit_reset_times

    def test_concurrent_family_management(self, sample_storage):
        """Test managing accounts for multiple families simultaneously."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)

        claude_account = manager.get_current_or_next_for_family("claude")
        gemini_account = manager.get_current_or_next_for_family("gemini")

        # Can be different accounts
        assert claude_account is not None
        assert gemini_account is not None

        # Rate limit claude account for Claude only
        manager.mark_rate_limited(claude_account, 5000, "claude", "antigravity")

        # Next call for Claude should get different account
        next_claude = manager.get_current_or_next_for_family("claude")
        assert next_claude is not None
        assert next_claude.index != claude_account.index

        # But Gemini can still use the rate-limited account if not limited for Gemini
        gemini_next = manager.get_current_or_next_for_family("gemini")
        assert gemini_next is not None

    def test_init_with_empty_accounts_in_storage(self):
        """Test init with stored AccountStorage that has an empty accounts list."""
        storage = AccountStorage(version=3, accounts=[], active_index=0)
        manager = AccountManager(initial_refresh_token="token", stored=storage)
        assert manager.account_count == 0

    def test_init_skips_account_without_refresh_token(self):
        """Test that accounts with no refresh_token are skipped during load."""
        now = time.time() * 1000
        storage = AccountStorage(
            version=3,
            accounts=[
                AccountMetadata(
                    refresh_token="",
                    email="no-token@example.com",
                    added_at=now,
                    last_used=0,
                    rate_limit_reset_times=RateLimitState(),
                ),
                AccountMetadata(
                    refresh_token="valid_token",
                    email="valid@example.com",
                    added_at=now,
                    last_used=0,
                    rate_limit_reset_times=RateLimitState(),
                ),
            ],
            active_index=0,
        )
        manager = AccountManager(initial_refresh_token="", stored=storage)
        assert manager.account_count == 1
        assert manager.get_accounts_snapshot()[0].email == "valid@example.com"

    def test_init_loads_gemini_cli_rate_limit(self):
        """Test that gemini_cli rate limits are loaded from storage."""
        now = time.time() * 1000
        storage = AccountStorage(
            version=3,
            accounts=[
                AccountMetadata(
                    refresh_token="token",
                    email="test@example.com",
                    added_at=now,
                    last_used=0,
                    rate_limit_reset_times=RateLimitState(
                        gemini_cli=now + 9000,
                    ),
                ),
            ],
            active_index=0,
        )
        manager = AccountManager(initial_refresh_token="", stored=storage)
        account = manager.get_accounts_snapshot()[0]
        assert account.rate_limit_reset_times["gemini-cli"] == now + 9000

    def test_get_min_wait_time_gemini_all_limited(self):
        """Test min wait time for gemini when all accounts are rate limited."""
        manager = AccountManager(initial_refresh_token="", stored=None)
        manager.add_account("t1", "a@b.com")
        manager.add_account("t2", "c@d.com")

        # Rate limit both accounts for both gemini pools
        for acc in manager.get_accounts_snapshot():
            manager.mark_rate_limited(acc, 10000, "gemini", "antigravity")
            manager.mark_rate_limited(acc, 5000, "gemini", "gemini-cli")

        wait = manager.get_min_wait_time_for_family("gemini")
        # Should pick the min of the min-per-account waits
        assert wait > 0
        assert wait <= 5100  # cli expires first at ~5000ms

    def test_get_min_wait_time_gemini_one_pool_not_limited(self):
        """Test gemini wait time when only one pool is limited (account available)."""
        manager = AccountManager(initial_refresh_token="", stored=None)
        manager.add_account("t1", "a@b.com")

        # Only limit antigravity, not cli - account is NOT fully rate limited
        acc = manager.get_accounts_snapshot()[0]
        manager.mark_rate_limited(acc, 10000, "gemini", "antigravity")

        wait = manager.get_min_wait_time_for_family("gemini")
        assert wait == 0  # Account is available (not fully limited)

    def test_remove_account_adjusts_cursor(self, sample_storage):
        """Test that removing an account before cursor adjusts cursor down."""
        manager = AccountManager(initial_refresh_token="", stored=sample_storage)
        manager._cursor = 2  # cursor after second account

        # Remove first account (index 0, before cursor)
        account_to_remove = manager.get_accounts_snapshot()[0]
        manager.remove_account(account_to_remove)

        assert manager._cursor == 1  # adjusted down

    def test_remove_account_resets_high_family_index(self):
        """Test that family index is set to -1 when it equals len(accounts)."""
        manager = AccountManager(initial_refresh_token="", stored=None)
        manager.add_account("t1", "a@b.com")
        manager.add_account("t2", "c@d.com")

        # Set claude index to last account (index 1)
        manager._current_index_by_family["claude"] = 1
        manager._current_index_by_family["gemini"] = 0

        # Remove last account (index 1) - claude index should become -1
        acc = manager.get_accounts_snapshot()[1]
        manager.remove_account(acc)

        assert manager._current_index_by_family["claude"] == -1
