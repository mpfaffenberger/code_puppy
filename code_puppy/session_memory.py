import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_MEMORY_PATH = Path(".puppy_session_memory.json")


class SessionMemory:
    """
    Simple persistent memory for Code Puppy agent sessions.
    Stores short histories of tasks, notes, user preferences, and watched files.
    """

    def __init__(
        self, storage_path: Path = DEFAULT_MEMORY_PATH, memory_limit: int = 128
    ):
        self.storage_path = storage_path
        self.memory_limit = memory_limit
        self._data = {
            "history": [],  # List of task/event dicts
            "user_preferences": {},
            "watched_files": [],
        }
        self._load()

    def _load(self):
        if self.storage_path.exists():
            try:
                self._data = json.loads(self.storage_path.read_text())
            except Exception:
                self._data = {
                    "history": [],
                    "user_preferences": {},
                    "watched_files": [],
                }

    def _save(self):
        try:
            self.storage_path.write_text(json.dumps(self._data, indent=2))
        except Exception:
            pass  # Don't crash the agent for memory fails

    def log_task(self, description: str, extras: Optional[Dict[str, Any]] = None):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "description": description,
        }
        if extras:
            entry.update(extras)
        self._data["history"].append(entry)
        # Trim memory
        self._data["history"] = self._data["history"][-self.memory_limit :]
        self._save()

    def get_history(self, within_minutes: Optional[int] = None) -> List[Dict[str, Any]]:
        if not within_minutes:
            return list(self._data["history"])
        cutoff = datetime.utcnow() - timedelta(minutes=within_minutes)
        return [
            h
            for h in self._data["history"]
            if datetime.fromisoformat(h["timestamp"]) >= cutoff
        ]

    def set_preference(self, key: str, value: Any):
        self._data["user_preferences"][key] = value
        self._save()

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self._data["user_preferences"].get(key, default)

    def add_watched_file(self, path: str):
        if path not in self._data["watched_files"]:
            self._data["watched_files"].append(path)
            self._save()

    def list_watched_files(self) -> List[str]:
        return list(self._data["watched_files"])

    def clear(self):
        self._data = {"history": [], "user_preferences": {}, "watched_files": []}
        self._save()
