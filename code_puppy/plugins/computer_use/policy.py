"""Persisted computer-use consent, explicit denials, and hard stops."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from code_puppy.config import CONFIG_DIR

from .backend_types import ComputerUseError

POLICY_PATH = Path(CONFIG_DIR) / "computer_use_policy.json"
SYSTEM_DENYLIST = {
    "com.apple.loginwindow",
    "com.apple.securityagent",
    "com.apple.systempreferences",
    "com.apple.systemsettings",
    "com.apple.keychainaccess",
    "com.apple.authorizationhost",
}


class PolicyStore:
    def __init__(self, path: Path = POLICY_PATH) -> None:
        self.path = path
        self._paused = False
        self._lock = threading.RLock()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"enabled": None, "denied": []}
        try:
            payload = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return {"enabled": None, "denied": []}
        enabled = payload.get("enabled")
        return {
            "enabled": enabled if isinstance(enabled, bool) else None,
            "denied": list(payload.get("denied", [])),
        }

    def _save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True))
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)

    def allow(self, bundle_id: str) -> None:
        """Remove an explicit denial; all other applications are allowed."""
        normalized = bundle_id.casefold()
        if normalized in SYSTEM_DENYLIST:
            raise ComputerUseError(
                f"Computer Use is never allowed for security process {bundle_id}."
            )
        with self._lock:
            payload = self._load()
            denied = {str(item).casefold() for item in payload["denied"]}
            denied.discard(normalized)
            payload["denied"] = sorted(denied)
            self._save(payload)

    def deny(self, bundle_id: str) -> None:
        normalized = bundle_id.casefold()
        with self._lock:
            payload = self._load()
            denied = {str(item).casefold() for item in payload["denied"]}
            denied.add(normalized)
            payload["denied"] = sorted(denied)
            self._save(payload)

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            payload = self._load()
            payload["enabled"] = enabled
            self._save(payload)

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self._paused = paused

    def require_enabled(self) -> None:
        with self._lock:
            if self._paused:
                raise ComputerUseError(
                    "Computer Use is paused by the emergency stop. Run "
                    "`/computer-use resume` after confirming it is safe."
                )
            payload = self._load()
            if payload["enabled"] is None:
                raise ComputerUseError(
                    "Computer Use needs your one-time permission before its first "
                    "use. It can view screenshots and control apps on this Mac. "
                    "Run `/computer-use enable` to allow it, or "
                    "`/computer-use disable` to keep it off. You can change this "
                    "setting later with the same commands."
                )
            if payload["enabled"] is False:
                raise ComputerUseError(
                    "Computer Use is disabled in settings. Run "
                    "`/computer-use enable` to turn it on."
                )

    def require(self, bundle_id: str) -> None:
        self.require_enabled()
        normalized = bundle_id.casefold()
        with self._lock:
            if normalized in SYSTEM_DENYLIST:
                raise ComputerUseError(
                    f"Computer Use is blocked for security process {bundle_id}."
                )
            payload = self._load()
            denied = {str(item).casefold() for item in payload["denied"]}
            if normalized in denied:
                raise ComputerUseError(
                    f"Computer Use is denied for application {bundle_id}."
                )

    def status(self) -> dict[str, Any]:
        with self._lock:
            payload = self._load()
            return {
                "mode": (
                    "enabled"
                    if payload["enabled"] is True
                    else "disabled"
                    if payload["enabled"] is False
                    else "needs-first-use-consent"
                ),
                "paused": self._paused,
                "denied": payload["denied"],
                "system_denied": sorted(SYSTEM_DENYLIST),
            }


policy_store = PolicyStore()
