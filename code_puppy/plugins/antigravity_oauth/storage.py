"""Account storage for multi-account Antigravity OAuth."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from .config import get_accounts_storage_path

logger = logging.getLogger(__name__)

ModelFamily = Literal["claude", "gemini"]
HeaderStyle = Literal["antigravity", "gemini-cli"]
QuotaKey = Literal["claude", "gemini-antigravity", "gemini-cli"]


@dataclass
class RateLimitState:
    """Rate limit reset times per quota key."""

    claude: Optional[float] = None
    gemini_antigravity: Optional[float] = None
    gemini_cli: Optional[float] = None

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for JSON serialization."""
        result: Dict[str, float] = {}
        if self.claude is not None:
            result["claude"] = self.claude
        if self.gemini_antigravity is not None:
            result["gemini-antigravity"] = self.gemini_antigravity
        if self.gemini_cli is not None:
            result["gemini-cli"] = self.gemini_cli
        return result

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "RateLimitState":
        """Create from dictionary."""
        if not data:
            return cls()
        return cls(
            claude=data.get("claude"),
            gemini_antigravity=data.get("gemini-antigravity"),
            gemini_cli=data.get("gemini-cli"),
        )


@dataclass
class AccountMetadata:
    """Stored metadata for a single account."""

    refresh_token: str
    email: Optional[str] = None
    project_id: Optional[str] = None
    managed_project_id: Optional[str] = None
    added_at: float = 0
    last_used: float = 0
    last_switch_reason: Optional[Literal["rate-limit", "initial", "rotation"]] = None
    rate_limit_reset_times: RateLimitState = field(default_factory=RateLimitState)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: Dict[str, Any] = {
            "refreshToken": self.refresh_token,
            "addedAt": self.added_at,
            "lastUsed": self.last_used,
        }
        if self.email:
            result["email"] = self.email
        if self.project_id:
            result["projectId"] = self.project_id
        if self.managed_project_id:
            result["managedProjectId"] = self.managed_project_id
        if self.last_switch_reason:
            result["lastSwitchReason"] = self.last_switch_reason

        rate_limits = self.rate_limit_reset_times.to_dict()
        if rate_limits:
            result["rateLimitResetTimes"] = rate_limits

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AccountMetadata":
        """Create from dictionary."""
        return cls(
            refresh_token=data.get("refreshToken", ""),
            email=data.get("email"),
            project_id=data.get("projectId"),
            managed_project_id=data.get("managedProjectId"),
            added_at=data.get("addedAt", 0),
            last_used=data.get("lastUsed", 0),
            last_switch_reason=data.get("lastSwitchReason"),
            rate_limit_reset_times=RateLimitState.from_dict(
                data.get("rateLimitResetTimes")
            ),
        )


@dataclass
class AccountStorage:
    """V3 account storage format."""

    version: int = 3
    accounts: List[AccountMetadata] = field(default_factory=list)
    active_index: int = 0
    active_index_by_family: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "accounts": [acc.to_dict() for acc in self.accounts],
            "activeIndex": self.active_index,
            "activeIndexByFamily": self.active_index_by_family,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AccountStorage":
        """Create from dictionary."""
        accounts = [AccountMetadata.from_dict(acc) for acc in data.get("accounts", [])]
        return cls(
            version=data.get("version", 3),
            accounts=accounts,
            active_index=data.get("activeIndex", 0),
            active_index_by_family=data.get("activeIndexByFamily", {}),
        )


def _migrate_v1_to_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate V1 storage format to V2."""
    now = time.time() * 1000  # V1 used milliseconds

    accounts = []
    for acc in data.get("accounts", []):
        rate_limits: Dict[str, float] = {}
        if acc.get("isRateLimited") and acc.get("rateLimitResetTime"):
            reset_time = acc["rateLimitResetTime"]
            if reset_time > now:
                rate_limits["claude"] = reset_time
                rate_limits["gemini"] = reset_time

        accounts.append(
            {
                "email": acc.get("email"),
                "refreshToken": acc.get("refreshToken", ""),
                "projectId": acc.get("projectId"),
                "managedProjectId": acc.get("managedProjectId"),
                "addedAt": acc.get("addedAt", now),
                "lastUsed": acc.get("lastUsed", 0),
                "lastSwitchReason": acc.get("lastSwitchReason"),
                "rateLimitResetTimes": rate_limits if rate_limits else None,
            }
        )

    return {
        "version": 2,
        "accounts": accounts,
        "activeIndex": data.get("activeIndex", 0),
    }


def _migrate_v2_to_v3(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate V2 storage format to V3."""
    now = time.time() * 1000

    accounts = []
    for acc in data.get("accounts", []):
        rate_limits: Dict[str, float] = {}
        old_limits = acc.get("rateLimitResetTimes", {}) or {}

        if old_limits.get("claude") and old_limits["claude"] > now:
            rate_limits["claude"] = old_limits["claude"]
        if old_limits.get("gemini") and old_limits["gemini"] > now:
            rate_limits["gemini-antigravity"] = old_limits["gemini"]

        accounts.append(
            {
                "email": acc.get("email"),
                "refreshToken": acc.get("refreshToken", ""),
                "projectId": acc.get("projectId"),
                "managedProjectId": acc.get("managedProjectId"),
                "addedAt": acc.get("addedAt", 0),
                "lastUsed": acc.get("lastUsed", 0),
                "lastSwitchReason": acc.get("lastSwitchReason"),
                "rateLimitResetTimes": rate_limits if rate_limits else None,
            }
        )

    return {
        "version": 3,
        "accounts": accounts,
        "activeIndex": data.get("activeIndex", 0),
        "activeIndexByFamily": {},
    }


def load_accounts() -> Optional[AccountStorage]:
    """Load account storage from disk with automatic migration."""
    path = get_accounts_storage_path()

    try:
        if not path.exists():
            return None

        content = path.read_text(encoding="utf-8")
        data = json.loads(content)

        if not isinstance(data.get("accounts"), list):
            logger.warning("Invalid storage format, ignoring")
            return None

        version = data.get("version", 1)

        # Migrate if needed
        if version == 1:
            logger.info("Migrating account storage from v1 to v3")
            data = _migrate_v1_to_v2(data)
            data = _migrate_v2_to_v3(data)
        elif version == 2:
            logger.info("Migrating account storage from v2 to v3")
            data = _migrate_v2_to_v3(data)

        storage = AccountStorage.from_dict(data)

        # Validate active index
        if storage.accounts:
            storage.active_index = max(
                0, min(storage.active_index, len(storage.accounts) - 1)
            )
        else:
            storage.active_index = 0

        # Save migrated data if we migrated
        if version < 3:
            try:
                save_accounts(storage)
                logger.info("Migration to v3 complete")
            except Exception as e:
                logger.warning("Failed to persist migrated storage: %s", e)

        return storage

    except FileNotFoundError:
        return None
    except Exception as e:
        logger.error("Failed to load account storage: %s", e)
        return None


def save_accounts(storage: AccountStorage) -> None:
    """Save account storage to disk atomically."""
    path = get_accounts_storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    content = json.dumps(storage.to_dict(), indent=2)

    # Atomic write: write to temp file then rename
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))  # atomic on POSIX
        path.chmod(0o600)
    except BaseException:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def clear_accounts() -> None:
    """Clear all stored accounts."""
    path = get_accounts_storage_path()
    try:
        if path.exists():
            path.unlink()
    except Exception as e:
        logger.error("Failed to clear account storage: %s", e)
