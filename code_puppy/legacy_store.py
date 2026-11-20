"""``puppy.db``: Code Puppy's own SQLite file, beside the runtime's ``config.db``.

pydantic-ai-pax owns ``config.db`` and rejects setting names it does not know.
Everything that belongs to Code Puppy alone lives here instead:

* ``legacy_settings``: 0.0.x ``puppy.cfg`` keys with no 1.0 equivalent, and
  whatever 0.0.x plugins write through ``code_puppy.config``.
* ``meta``: bookkeeping, such as which legacy files were already migrated.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from code_puppy import identity

FILE_NAME = "puppy.db"
SCHEMA_VERSION = 1


class LegacyStore:
    """Short transactions over ``puppy.db``; every call opens and closes it."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or identity.config_dir() / FILE_NAME
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise ValueError(f"Unsupported {FILE_NAME} schema version: {version}")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS legacy_settings "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS meta "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM legacy_settings WHERE key = ?", (key,)
            ).fetchone()
        return None if row is None else row[0]

    def set(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO legacy_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def set_missing(self, values: Mapping[str, str]) -> list[str]:
        """Insert the keys that are not stored yet; return the ones inserted."""
        added: list[str] = []
        with self._connect() as connection:
            for key, value in values.items():
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO legacy_settings (key, value) VALUES (?, ?)",
                    (key, value),
                )
                if cursor.rowcount:
                    added.append(key)
        return added

    def delete(self, key: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM legacy_settings WHERE key = ?", (key,)
            )
        return bool(cursor.rowcount)

    def items(self) -> dict[str, str]:
        with self._connect() as connection:
            return dict(
                connection.execute(
                    "SELECT key, value FROM legacy_settings ORDER BY key"
                )
            )

    def meta(self, key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        return None if row is None else row[0]

    def set_meta(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
