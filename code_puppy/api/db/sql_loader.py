"""Helpers for loading external SQL query files.

Keeps complex SQL out of Python source while preserving parameterized execution.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_SQL_DIR = Path(__file__).with_name("sql")


@lru_cache(maxsize=64)
def load_sql(name: str) -> str:
    """Load an SQL file from ``code_puppy/api/db/sql``.

    Args:
        name: Filename like ``session_history_parity.sql``.
    """
    sql_path = _SQL_DIR / name
    return sql_path.read_text(encoding="utf-8")
