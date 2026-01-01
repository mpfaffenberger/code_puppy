"""Multi-account manager for Antigravity OAuth with load balancing."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from .storage import (
    AccountMetadata,
    AccountStorage,
    HeaderStyle,
    ModelFamily,
    QuotaKey,
    RateLimitState,
    load_accounts,
    save_accounts,
)
from .token import RefreshParts, parse_refresh_parts

logger = logging.getLogger(__name__)


@dataclass
class ManagedAccount:
    """In-memory representation of a managed account."""

    index: int
    email: Optional[str]
    added_at: float
    last_used: float
    parts: RefreshParts
    access_token: Optional[str] = None
    expires_at: Optional[float] = None
    rate_limit_reset_times: Dict[str, float] = field(default_factory=dict)
    last_switch_reason: Optional[Literal["rate-limit", "initial", "rotation"]] = None


def _now_ms() -> float:
    """Current time in milliseconds."""
    return time.time() * 1000


def _get_quota_key(family: ModelFamily, header_style: HeaderStyle) -> QuotaKey:
    """Get the quota key for a model family and header style."""
    if family == "claude":
        return "claude"
    return "gemini-cli" if header_style == "gemini-cli" else "gemini-antigravity"


def _is_rate_limited_for_quota_key(account: ManagedAccount, key: QuotaKey) -> bool:
    """Check if account is rate limited for a specific quota key."""
    reset_time = account.rate_limit_reset_times.get(key)
    return reset_time is not None and _now_ms() < reset_time


def _is_rate_limited_for_family(account: ManagedAccount, family: ModelFamily) -> bool:
    """Check if account is rate limited for an entire model family."""
    if family == "claude":
        return _is_rate_limited_for_quota_key(account, "claude")
    # For Gemini, both pools must be rate limited
    return _is_rate_limited_for_quota_key(
        account, "gemini-antigravity"
    ) and _is_rate_limited_for_quota_key(account, "gemini-cli")


def _clear_expired_rate_limits(account: ManagedAccount) -> None:
    """Clear expired rate limits from an account."""
    now = _now_ms()
    keys_to_remove = [
        key
        for key, reset_time in account.rate_limit_reset_times.items()
        if now >= reset_time
    ]
    for key in keys_to_remove:
        del account.rate_limit_reset_times[key]


class AccountManager:
    """Multi-account manager with sticky account selection and load balancing.

    Uses the same account until it hits a rate limit (429), then switches.
    Rate limits are tracked per-model-family (claude/gemini) so an account
    rate-limited for Claude can still be used for Gemini.
    """

    def __init__(
        self,
        initial_refresh_token: Optional[str] = None,
        stored: Optional[AccountStorage] = None,
    ):
        self._accounts: List[ManagedAccount] = []
        self._cursor = 0
        self._current_index_by_family: Dict[ModelFamily, int] = {
            "claude": -1,
            "gemini": -1,
        }
        self._last_toast_index = -1
        self._last_toast_time = 0.0

        initial_parts = parse_refresh_parts(initial_refresh_token or "")

        if stored and not stored.accounts:
            return

        if stored and stored.accounts:
            now = _now_ms()
            for i, acc in enumerate(stored.accounts):
                if not acc.refresh_token:
                    continue

                parts = RefreshParts(
                    refresh_token=acc.refresh_token,
                    project_id=acc.project_id,
                    managed_project_id=acc.managed_project_id,
                )

                # Convert rate limits from storage
                rate_limits: Dict[str, float] = {}
                if acc.rate_limit_reset_times.claude:
                    rate_limits["claude"] = acc.rate_limit_reset_times.claude
                if acc.rate_limit_reset_times.gemini_antigravity:
                    rate_limits["gemini-antigravity"] = (
                        acc.rate_limit_reset_times.gemini_antigravity
                    )
                if acc.rate_limit_reset_times.gemini_cli:
                    rate_limits["gemini-cli"] = acc.rate_limit_reset_times.gemini_cli

                self._accounts.append(
                    ManagedAccount(
                        index=i,
                        email=acc.email,
                        added_at=acc.added_at or now,
                        last_used=acc.last_used or 0,
                        parts=parts,
                        access_token=None,  # Tokens loaded separately
                        expires_at=None,
                        rate_limit_reset_times=rate_limits,
                        last_switch_reason=acc.last_switch_reason,
                    )
                )

            if self._accounts:
                self._cursor = max(0, min(stored.active_index, len(self._accounts) - 1))
                default_idx = self._cursor
                self._current_index_by_family["claude"] = (
                    stored.active_index_by_family.get("claude", default_idx)
                    % len(self._accounts)
                )
                self._current_index_by_family["gemini"] = (
                    stored.active_index_by_family.get("gemini", default_idx)
                    % len(self._accounts)
                )
            return

        # Fallback: create single account from initial token
        if initial_parts.refresh_token:
            now = _now_ms()
            self._accounts.append(
                ManagedAccount(
                    index=0,
                    email=None,
                    added_at=now,
                    last_used=0,
                    parts=initial_parts,
                    rate_limit_reset_times={},
                )
            )
            self._current_index_by_family["claude"] = 0
            self._current_index_by_family["gemini"] = 0

    @classmethod
    def load_from_disk(
        cls, initial_refresh_token: Optional[str] = None
    ) -> "AccountManager":
        """Load account manager from disk."""
        stored = load_accounts()
        return cls(initial_refresh_token, stored)

    @property
    def account_count(self) -> int:
        """Number of accounts in the pool."""
        return len(self._accounts)

    def get_accounts_snapshot(self) -> List[ManagedAccount]:
        """Get a snapshot of all accounts."""
        return list(self._accounts)

    def get_current_account_for_family(
        self,
        family: ModelFamily,
    ) -> Optional[ManagedAccount]:
        """Get the current active account for a model family."""
        idx = self._current_index_by_family.get(family, -1)
        if 0 <= idx < len(self._accounts):
            return self._accounts[idx]
        return None

    def get_current_or_next_for_family(
        self,
        family: ModelFamily,
    ) -> Optional[ManagedAccount]:
        """Get current account if not rate limited, otherwise find next available."""
        current = self.get_current_account_for_family(family)

        if current:
            _clear_expired_rate_limits(current)
            if not _is_rate_limited_for_family(current, family):
                current.last_used = _now_ms()
                return current

        # Find next available account
        next_account = self._get_next_for_family(family)
        if next_account:
            self._current_index_by_family[family] = next_account.index
        return next_account

    def _get_next_for_family(self, family: ModelFamily) -> Optional[ManagedAccount]:
        """Get next available account for a model family."""
        available = []
        for acc in self._accounts:
            _clear_expired_rate_limits(acc)
            if not _is_rate_limited_for_family(acc, family):
                available.append(acc)

        if not available:
            return None

        account = available[self._cursor % len(available)]
        self._cursor += 1
        account.last_used = _now_ms()
        return account

    def mark_rate_limited(
        self,
        account: ManagedAccount,
        retry_after_ms: float,
        family: ModelFamily,
        header_style: HeaderStyle = "antigravity",
    ) -> None:
        """Mark an account as rate limited."""
        key = _get_quota_key(family, header_style)
        account.rate_limit_reset_times[key] = _now_ms() + retry_after_ms

    def is_rate_limited_for_header_style(
        self,
        account: ManagedAccount,
        family: ModelFamily,
        header_style: HeaderStyle,
    ) -> bool:
        """Check if account is rate limited for a specific header style."""
        _clear_expired_rate_limits(account)
        key = _get_quota_key(family, header_style)
        return _is_rate_limited_for_quota_key(account, key)

    def get_available_header_style(
        self,
        account: ManagedAccount,
        family: ModelFamily,
    ) -> Optional[HeaderStyle]:
        """Get an available header style for the account, or None if all limited."""
        _clear_expired_rate_limits(account)

        if family == "claude":
            if not _is_rate_limited_for_quota_key(account, "claude"):
                return "antigravity"
            return None

        # For Gemini, try Antigravity first, then Gemini CLI
        if not _is_rate_limited_for_quota_key(account, "gemini-antigravity"):
            return "antigravity"
        if not _is_rate_limited_for_quota_key(account, "gemini-cli"):
            return "gemini-cli"
        return None

    def get_min_wait_time_for_family(self, family: ModelFamily) -> float:
        """Get minimum wait time until an account becomes available (in ms)."""
        # Check if any account is already available
        for acc in self._accounts:
            _clear_expired_rate_limits(acc)
            if not _is_rate_limited_for_family(acc, family):
                return 0

        # Calculate minimum wait time
        wait_times: List[float] = []
        now = _now_ms()

        for acc in self._accounts:
            if family == "claude":
                reset = acc.rate_limit_reset_times.get("claude")
                if reset is not None:
                    wait_times.append(max(0, reset - now))
            else:
                # For Gemini, account available when EITHER pool expires
                ag_reset = acc.rate_limit_reset_times.get("gemini-antigravity")
                cli_reset = acc.rate_limit_reset_times.get("gemini-cli")

                ag_wait = max(0, ag_reset - now) if ag_reset else float("inf")
                cli_wait = max(0, cli_reset - now) if cli_reset else float("inf")

                account_wait = min(ag_wait, cli_wait)
                if account_wait != float("inf"):
                    wait_times.append(account_wait)

        return min(wait_times) if wait_times else 0

    def add_account(
        self,
        refresh_token: str,
        email: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> ManagedAccount:
        """Add a new account to the pool."""
        now = _now_ms()
        parts = parse_refresh_parts(refresh_token)
        if project_id:
            parts.project_id = project_id

        account = ManagedAccount(
            index=len(self._accounts),
            email=email,
            added_at=now,
            last_used=0,
            parts=parts,
            rate_limit_reset_times={},
        )
        self._accounts.append(account)

        # Set as active if this is the first account
        if len(self._accounts) == 1:
            self._current_index_by_family["claude"] = 0
            self._current_index_by_family["gemini"] = 0

        return account

    def remove_account(self, account: ManagedAccount) -> bool:
        """Remove an account from the pool."""
        try:
            idx = self._accounts.index(account)
        except ValueError:
            return False

        self._accounts.pop(idx)

        # Re-index remaining accounts
        for i, acc in enumerate(self._accounts):
            acc.index = i

        if not self._accounts:
            self._cursor = 0
            self._current_index_by_family["claude"] = -1
            self._current_index_by_family["gemini"] = -1
            return True

        # Adjust cursor and active indices
        if self._cursor > idx:
            self._cursor -= 1
        self._cursor = self._cursor % len(self._accounts)

        for family in ["claude", "gemini"]:
            family_key: ModelFamily = family  # type: ignore
            if self._current_index_by_family[family_key] > idx:
                self._current_index_by_family[family_key] -= 1
            if self._current_index_by_family[family_key] >= len(self._accounts):
                self._current_index_by_family[family_key] = -1

        return True

    def save_to_disk(self) -> None:
        """Persist account state to disk."""
        claude_idx = max(0, self._current_index_by_family.get("claude", 0))
        gemini_idx = max(0, self._current_index_by_family.get("gemini", 0))

        accounts: List[AccountMetadata] = []
        for acc in self._accounts:
            rate_limits = RateLimitState(
                claude=acc.rate_limit_reset_times.get("claude"),
                gemini_antigravity=acc.rate_limit_reset_times.get("gemini-antigravity"),
                gemini_cli=acc.rate_limit_reset_times.get("gemini-cli"),
            )

            accounts.append(
                AccountMetadata(
                    refresh_token=acc.parts.refresh_token,
                    email=acc.email,
                    project_id=acc.parts.project_id,
                    managed_project_id=acc.parts.managed_project_id,
                    added_at=acc.added_at,
                    last_used=acc.last_used,
                    last_switch_reason=acc.last_switch_reason,
                    rate_limit_reset_times=rate_limits,
                )
            )

        storage = AccountStorage(
            version=3,
            accounts=accounts,
            active_index=claude_idx,
            active_index_by_family={
                "claude": claude_idx,
                "gemini": gemini_idx,
            },
        )

        save_accounts(storage)
