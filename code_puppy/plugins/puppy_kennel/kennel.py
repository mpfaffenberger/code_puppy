"""The Kennel — storage layer for puppy_kennel.

A thin wrapper around SQLite that exposes the wing/room/drawer vocabulary
without leaking SQL all over the rest of the plugin. Connections are
short-lived and use a per-call ``with sqlite3.connect(...)`` block so we
never accidentally hold the write lock across awaits.

WAL mode means many readers + one writer is safe across processes.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import DB_PATH, MAX_DRAWER_CHARS, KENNEL_ROOT
from .schema import PRAGMAS, SCHEMA_SQL


@dataclass(slots=True, frozen=True)
class Drawer:
    """A verbatim chunk of remembered content."""

    id: int
    room_id: int
    role: str | None
    content: str
    ts: str
    session_id: str | None
    metadata: dict[str, Any] | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_root() -> None:
    KENNEL_ROOT.mkdir(parents=True, exist_ok=True)


@contextmanager
def _connect(path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with the kennel PRAGMAs applied.

    Short-lived by design: open, do work, close. WAL handles concurrency.
    """
    _ensure_root()
    conn = sqlite3.connect(path, timeout=10.0, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        for pragma in PRAGMAS:
            conn.execute(pragma)
        yield conn
    finally:
        conn.close()


def initialize() -> None:
    """Create tables, indexes, and FTS triggers if they don't exist.

    Idempotent. Safe to call on every plugin load.
    """
    with _connect() as conn:
        conn.executescript(SCHEMA_SQL)


# --------------------------------------------------------------------------- #
# Wings and rooms (simple upserts; nothing fancy)
# --------------------------------------------------------------------------- #


def ensure_wing(name: str, metadata: dict[str, Any] | None = None) -> int:
    """Return the id of the wing named ``name``, creating it if missing.

    Uses ``INSERT OR IGNORE`` to dodge the SELECT-then-INSERT TOCTOU race
    between concurrent processes. The single INSERT is atomic; if another
    writer beat us to it the row already exists and we just re-SELECT.
    """
    payload = json.dumps(metadata) if metadata else None
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO wings(name, created_at, metadata) VALUES (?, ?, ?)",
            (name, _now_iso(), payload),
        )
        row = conn.execute("SELECT id FROM wings WHERE name = ?", (name,)).fetchone()
        return int(row["id"])


def ensure_room(wing_id: int, name: str, metadata: dict[str, Any] | None = None) -> int:
    """Return the id of the room (wing_id, name), creating it if missing.

    Same race-free pattern as ``ensure_wing``.
    """
    payload = json.dumps(metadata) if metadata else None
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO rooms(wing_id, name, created_at, metadata) "
            "VALUES (?, ?, ?, ?)",
            (wing_id, name, _now_iso(), payload),
        )
        row = conn.execute(
            "SELECT id FROM rooms WHERE wing_id = ? AND name = ?",
            (wing_id, name),
        ).fetchone()
        return int(row["id"])


# --------------------------------------------------------------------------- #
# Drawers — the actual remembered content
# --------------------------------------------------------------------------- #


def add_drawer(
    room_id: int,
    content: str,
    role: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Append a verbatim drawer to a room. Returns the new drawer id."""
    if not content or not content.strip():
        return 0
    if len(content) > MAX_DRAWER_CHARS:
        content = content[:MAX_DRAWER_CHARS] + "\n...[truncated]"
    payload = json.dumps(metadata) if metadata else None
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO drawers(room_id, role, content, ts, session_id, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (room_id, role, content, _now_iso(), session_id, payload),
        )
        return int(cur.lastrowid)


def _row_to_drawer(row: sqlite3.Row) -> Drawer:
    meta_raw = row["metadata"] if "metadata" in row.keys() else None
    meta = json.loads(meta_raw) if meta_raw else None
    return Drawer(
        id=int(row["id"]),
        room_id=int(row["room_id"]),
        role=row["role"],
        content=row["content"],
        ts=row["ts"],
        session_id=row["session_id"],
        metadata=meta,
    )


def recent_drawers(
    wing_name: str, limit: int = 5, role: str | None = None
) -> list[Drawer]:
    """Return the most recent drawers in a wing, optionally role-filtered.

    ``role=None`` returns every role (assistant + note + ...). Pass a
    specific value like ``"note"`` to get just sticky writes from
    ``kennel_remember``.
    """
    sql_parts = [
        "SELECT d.* FROM drawers d",
        "JOIN rooms r ON r.id = d.room_id",
        "JOIN wings w ON w.id = r.wing_id",
        "WHERE w.name = ?",
    ]
    params: list[Any] = [wing_name]
    if role is not None:
        sql_parts.append("AND d.role = ?")
        params.append(role)
    sql_parts.append("ORDER BY d.ts DESC LIMIT ?")
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(" ".join(sql_parts), params).fetchall()
    return [_row_to_drawer(r) for r in rows]


def recent_drawers_multi(
    wing_names: list[str] | None = None,
    limit: int = 5,
) -> list[Drawer]:
    """Recent drawers across multiple wings, deduplicated by content.

    Same dual-write workaround as ``search_drawers_multi``: over-fetch then
    dedupe by content, keeping the most recent copy of each unique drawer.
    """
    sql_parts = [
        "SELECT d.* FROM drawers d",
        "JOIN rooms r ON r.id = d.room_id",
        "JOIN wings w ON w.id = r.wing_id",
    ]
    params: list[Any] = []
    if wing_names:
        placeholders = ",".join("?" * len(wing_names))
        sql_parts.append(f"WHERE w.name IN ({placeholders})")
        params.extend(wing_names)
    sql_parts.append("ORDER BY d.ts DESC LIMIT ?")
    params.append(max(limit * 4, limit))

    with _connect() as conn:
        rows = conn.execute(" ".join(sql_parts), params).fetchall()

    seen: set[str] = set()
    out: list[Drawer] = []
    for row in rows:
        drawer = _row_to_drawer(row)
        if drawer.content in seen:
            continue
        seen.add(drawer.content)
        out.append(drawer)
        if len(out) >= limit:
            break
    return out


def write_note(
    wing_name: str,
    room_name: str,
    content: str,
    role: str = "note",
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """High-level helper: ensure (wing, room) exist, then add a drawer.

    Returns the new drawer id, or 0 if the content was blank.
    """
    wing_id = ensure_wing(wing_name)
    room_id = ensure_room(wing_id, room_name)
    return add_drawer(
        room_id=room_id,
        content=content,
        role=role,
        session_id=session_id,
        metadata=metadata,
    )


def wings_with_counts() -> list[tuple[str, int]]:
    """List every wing with its drawer count. Sorted by name."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT w.name AS name, COUNT(d.id) AS n
            FROM wings w
            LEFT JOIN rooms r ON r.wing_id = w.id
            LEFT JOIN drawers d ON d.room_id = r.id
            GROUP BY w.id, w.name
            ORDER BY w.name
            """
        ).fetchall()
    return [(r["name"], int(r["n"])) for r in rows]


def search_drawers(
    query: str,
    wing_name: str | None = None,
    limit: int = 5,
) -> list[Drawer]:
    """FTS5 BM25 search across drawers, optionally scoped to a single wing."""
    if not query or not query.strip():
        return []
    fts_query = _sanitize_fts_query(query)
    if not fts_query:
        return []

    sql_parts = [
        "SELECT d.* FROM drawers d",
        "JOIN drawers_fts f ON f.rowid = d.id",
        "JOIN rooms r ON r.id = d.room_id",
        "JOIN wings w ON w.id = r.wing_id",
        "WHERE drawers_fts MATCH ?",
    ]
    params: list[Any] = [fts_query]
    if wing_name:
        sql_parts.append("AND w.name = ?")
        params.append(wing_name)
    sql_parts.append("ORDER BY bm25(drawers_fts) ASC LIMIT ?")
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(" ".join(sql_parts), params).fetchall()
    return [_row_to_drawer(r) for r in rows]


def search_drawers_multi(
    query: str,
    wing_names: list[str] | None = None,
    limit: int = 5,
) -> list[Drawer]:
    """Search multiple wings and dedupe by content.

    Because the recorder currently dual-writes every response to the repo
    wing AND the agent wing, naive multi-wing search returns the same text
    twice. We over-fetch, then dedupe by content keeping the best-scoring
    drawer per unique text. This is a pragmatic workaround for the schema
    duplication noted in the README; remove once the schema is normalised.
    """
    if not query or not query.strip():
        return []
    fts_query = _sanitize_fts_query(query)
    if not fts_query:
        return []

    sql_parts = [
        "SELECT d.* FROM drawers d",
        "JOIN drawers_fts f ON f.rowid = d.id",
        "JOIN rooms r ON r.id = d.room_id",
        "JOIN wings w ON w.id = r.wing_id",
        "WHERE drawers_fts MATCH ?",
    ]
    params: list[Any] = [fts_query]
    if wing_names:
        placeholders = ",".join("?" * len(wing_names))
        sql_parts.append(f"AND w.name IN ({placeholders})")
        params.extend(wing_names)
    # Over-fetch so dedup still leaves us with ``limit`` distinct drawers.
    sql_parts.append("ORDER BY bm25(drawers_fts) ASC LIMIT ?")
    params.append(max(limit * 4, limit))

    with _connect() as conn:
        rows = conn.execute(" ".join(sql_parts), params).fetchall()

    seen: set[str] = set()
    out: list[Drawer] = []
    for row in rows:
        drawer = _row_to_drawer(row)
        if drawer.content in seen:
            continue
        seen.add(drawer.content)
        out.append(drawer)
        if len(out) >= limit:
            break
    return out


# FTS5 treats a lot of punctuation as operators. For free-form text queries
# we wrap each token in quotes and OR them together. Crude but bulletproof.
_FTS_BAD = set('"()*:^-+')


def _sanitize_fts_query(query: str) -> str:
    tokens = []
    for raw in query.split():
        stripped = "".join(ch for ch in raw if ch not in _FTS_BAD).strip()
        if len(stripped) >= 2:
            tokens.append(f'"{stripped}"')
    return " OR ".join(tokens)


def list_wings() -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT name FROM wings ORDER BY name").fetchall()
    return [r["name"] for r in rows]


def count_drawers(wing_name: str | None = None) -> int:
    with _connect() as conn:
        if wing_name is None:
            row = conn.execute("SELECT COUNT(*) AS n FROM drawers").fetchone()
        else:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM drawers d
                JOIN rooms r ON r.id = d.room_id
                JOIN wings w ON w.id = r.wing_id
                WHERE w.name = ?
                """,
                (wing_name,),
            ).fetchone()
    return int(row["n"]) if row else 0
