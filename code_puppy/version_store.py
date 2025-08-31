import os
import sqlite3
import hashlib
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional
import contextvars

from code_puppy.config import CONFIG_DIR

# Note: DB path is resolved dynamically via get_db_path().
# Keep a home-directory fallback path for legacy compatibility.
DB_FILE_HOME = os.path.join(CONFIG_DIR, "version_store.db")

# Keep the last resolved/used DB path so callers can display the actual value.
_resolved_db_path: Optional[str] = None

# Context-local buffer for changes recorded during a single agent run
_pending_changes: contextvars.ContextVar[Optional[List[Dict[str, Optional[str]]]]] = (
    contextvars.ContextVar("pending_changes", default=None)
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_or_none(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    try:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()
    except Exception:
        return None


def get_db_connection() -> sqlite3.Connection:
    global _resolved_db_path
    # Compute a candidate path based on precedence rules
    db_path = _compute_default_db_path()
    db_dir = os.path.dirname(db_path)
    try:
        os.makedirs(db_dir, exist_ok=True)
    except Exception:
        # As a defensive fallback, try the home path
        db_path = DB_FILE_HOME
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    # Record the resolved path for later display
    _resolved_db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(_resolved_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _compute_default_db_path() -> str:
    """Compute the preferred DB path based on env vars and CWD, without side effects."""
    # 1) Explicit file path override
    env_path = os.getenv("CODE_PUPPY_DB_PATH")
    if env_path:
        try:
            return os.path.abspath(env_path)
        except Exception:
            pass

    # 2) Directory override
    env_dir = os.getenv("CODE_PUPPY_DB_DIR")
    if env_dir:
        try:
            return os.path.abspath(os.path.join(env_dir, "version_store.db"))
        except Exception:
            pass

    # 3) Project-local default under current working directory
    try:
        local_dir = os.path.join(os.getcwd(), ".code_puppy")
        return os.path.abspath(os.path.join(local_dir, "version_store.db"))
    except Exception:
        # 4) Fallback to home path
        return os.path.abspath(DB_FILE_HOME)


def get_db_path() -> str:
    """Return the absolute path to the version store SQLite database file.

    If a connection has already been established, return the last resolved path.
    Otherwise, compute the default path according to precedence rules.
    """
    return _resolved_db_path or _compute_default_db_path()


def initialize_db() -> None:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT UNIQUE NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id INTEGER NOT NULL,
                version INTEGER NOT NULL,
                output_text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                parent_response_id INTEGER,
                FOREIGN KEY (prompt_id) REFERENCES prompts(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_response_id) REFERENCES responses(id),
                UNIQUE (prompt_id, version)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                response_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                change_type TEXT NOT NULL,
                diff TEXT NOT NULL,
                before_content BLOB,
                after_content BLOB,
                before_hash TEXT,
                after_hash TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (response_id) REFERENCES responses(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()


def _ensure_prompt(conn: sqlite3.Connection, prompt_text: str) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id FROM prompts WHERE text = ?", (prompt_text,))
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur.execute("INSERT INTO prompts(text) VALUES (?)", (prompt_text,))
    conn.commit()
    return int(cur.lastrowid)


def add_version(
    prompt_text: str,
    output_text: str,
    parent_response_id: Optional[int] = None,
) -> (int, int):
    """
    Create a new response version for the prompt.
    Returns (version_number, response_id)
    """
    with get_db_connection() as conn:
        prompt_id = _ensure_prompt(conn, prompt_text)
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM responses WHERE prompt_id = ?",
            (prompt_id,),
        )
        next_version = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO responses(prompt_id, version, output_text, timestamp, parent_response_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (prompt_id, next_version, output_text, _now_iso(), parent_response_id),
        )
        conn.commit()
        return next_version, int(cur.lastrowid)


def update_response_output(response_id: int, output_text: str) -> None:
    """Update the output_text (and timestamp) for an existing response row."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE responses
            SET output_text = ?, timestamp = ?
            WHERE id = ?
            """,
            (output_text, _now_iso(), response_id),
        )
        conn.commit()


def list_versions(prompt_text: str) -> Iterable[tuple[int, int, str]]:
    """Yield (response_id, version, timestamp) for the given prompt."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.id, r.version, r.timestamp
            FROM responses r
            JOIN prompts p ON p.id = r.prompt_id
            WHERE p.text = ?
            ORDER BY r.version ASC
            """,
            (prompt_text,),
        )
        for row in cur.fetchall():
            yield int(row[0]), int(row[1]), str(row[2])


def list_all_versions(
    limit: Optional[int] = None,
) -> Iterable[tuple[int, str, int, str]]:
    """
    Yield (response_id, prompt_text, version, timestamp) for all prompts, newest first.
    If limit is provided, only return that many rows.
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        if limit is not None:
            cur.execute(
                """
                SELECT r.id, p.text, r.version, r.timestamp
                FROM responses r
                JOIN prompts p ON p.id = r.prompt_id
                ORDER BY r.id DESC
                LIMIT ?
                """,
                (int(limit),),
            )
        else:
            cur.execute(
                """
                SELECT r.id, p.text, r.version, r.timestamp
                FROM responses r
                JOIN prompts p ON p.id = r.prompt_id
                ORDER BY r.id DESC
                """
            )
        for row in cur.fetchall():
            yield int(row[0]), str(row[1]), int(row[2]), str(row[3])


def get_response_by_version(prompt_text: str, version: int) -> Optional[Dict[str, str]]:
    """Return dict with keys: id, version, output_text, timestamp."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.id, r.version, r.output_text, r.timestamp
            FROM responses r
            JOIN prompts p ON p.id = r.prompt_id
            WHERE p.text = ? AND r.version = ?
            """,
            (prompt_text, version),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": int(row[0]),
            "version": int(row[1]),
            "output_text": str(row[2]),
            "timestamp": str(row[3]),
        }


def get_response_by_id(response_id: int) -> Optional[Dict[str, str]]:
    """Return dict with keys: id, version, prompt_text, output_text, timestamp for a response id."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.id, r.version, r.output_text, r.timestamp, p.text
            FROM responses r
            JOIN prompts p ON p.id = r.prompt_id
            WHERE r.id = ?
            """,
            (response_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": int(row[0]),
            "version": int(row[1]),
            "output_text": str(row[2]),
            "timestamp": str(row[3]),
            "prompt_text": str(row[4]),
        }


# ---- Change capture (no Git) ----


def start_change_capture() -> None:
    """Begin a new capture session for file changes."""
    _pending_changes.set([])


def record_change(
    file_path: str,
    change_type: str,  # 'create' | 'modify' | 'delete'
    before_content: Optional[str],
    after_content: Optional[str],
    diff: str,
) -> None:
    buf = _pending_changes.get()
    if buf is None:
        # Not capturing right now; ignore
        return
    buf.append(
        {
            "file_path": file_path,
            "change_type": change_type,
            "before_content": before_content,
            "after_content": after_content,
            "diff": diff or "",
            "timestamp": _now_iso(),
        }
    )


def finalize_changes(response_id: int) -> None:
    buf = _pending_changes.get()
    # Clear buffer early to avoid duplicate writes on re-entry
    _pending_changes.set(None)
    if not buf:
        return
    with get_db_connection() as conn:
        cur = conn.cursor()
        for rec in buf:
            cur.execute(
                """
                INSERT INTO changes(
                    response_id, file_path, change_type, diff,
                    before_content, after_content, before_hash, after_hash, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    response_id,
                    rec["file_path"],
                    rec["change_type"],
                    rec.get("diff", ""),
                    rec.get("before_content"),
                    rec.get("after_content"),
                    _sha256_or_none(rec.get("before_content")),
                    _sha256_or_none(rec.get("after_content")),
                    rec.get("timestamp") or _now_iso(),
                ),
            )
        conn.commit()


def get_changes_for_version(
    prompt_text: str, version: int
) -> Iterable[Dict[str, Optional[str]]]:
    """
    Yield rows with keys: file_path, change_type, diff, before_content, after_content, timestamp.
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.file_path, c.change_type, c.diff, c.before_content, c.after_content, c.timestamp
            FROM changes c
            JOIN responses r ON r.id = c.response_id
            JOIN prompts p ON p.id = r.prompt_id
            WHERE p.text = ? AND r.version = ?
            ORDER BY c.id ASC
            """,
            (prompt_text, version),
        )
        for row in cur.fetchall():
            yield {
                "file_path": row[0],
                "change_type": row[1],
                "diff": row[2],
                "before_content": row[3],
                "after_content": row[4],
                "timestamp": row[5],
            }


def get_response_id_for_prompt_version(prompt_text: str, version: int) -> Optional[int]:
    """
    Resolve the response id for a given prompt text and version number.
    Returns None if not found.
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.id
            FROM responses r
            JOIN prompts p ON p.id = r.prompt_id
            WHERE p.text = ? AND r.version = ?
            """,
            (prompt_text, version),
        )
        row = cur.fetchone()
        return int(row[0]) if row else None


def compute_snapshot_as_of_response_id(
    response_id: int,
) -> Iterable[Dict[str, Optional[str]]]:
    """
    Compute the repository snapshot as-of the given response id across ALL tracked files.

    For each file that has ever been tracked in the `changes` table, yield a record:
      { 'file_path': str, 'content': Optional[str] }

    - If 'content' is None, the file should not exist at the snapshot point (delete if present).
    - If 'content' is a string, the file's content should be exactly this value at the snapshot point.
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        # Gather all tracked file paths
        cur.execute(
            """
            SELECT DISTINCT file_path
            FROM changes
            ORDER BY file_path ASC
            """
        )
        all_paths = [str(row[0]) for row in cur.fetchall()]

        # Get all change rows up to and including the cutoff response id, ordered
        cur.execute(
            """
            SELECT c.file_path, c.after_content, c.change_type, r.id AS rid, c.id AS cid
            FROM changes c
            JOIN responses r ON r.id = c.response_id
            WHERE r.id <= ?
            ORDER BY c.file_path ASC, r.id ASC, c.id ASC
            """,
            (response_id,),
        )
        last_by_path: Dict[str, sqlite3.Row] = {}
        for row in cur.fetchall():
            # Keep only the last change per file up to the cutoff
            last_by_path[str(row[0])] = row

        # Build the snapshot map: include all tracked files.
        # For paths without any change before cutoff, yield content=None to indicate deletion.
        for path in all_paths:
            row = last_by_path.get(path)
            if row is None:
                yield {"file_path": path, "content": None}
                continue
            after = row[1]
            if isinstance(after, (bytes, bytearray)):
                try:
                    after = after.decode("utf-8", errors="replace")
                except Exception:
                    after = None
            content: Optional[str] = after if after is not None else None
            yield {"file_path": path, "content": content}


def get_changes_for_response_id(response_id: int) -> Iterable[Dict[str, Optional[str]]]:
    """
    Yield rows with keys: file_path, change_type, diff, before_content, after_content, timestamp for a response id.
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.file_path, c.change_type, c.diff, c.before_content, c.after_content, c.timestamp
            FROM changes c
            WHERE c.response_id = ?
            ORDER BY c.id ASC
            """,
            (response_id,),
        )
        for row in cur.fetchall():
            yield {
                "file_path": row[0],
                "change_type": row[1],
                "diff": row[2],
                "before_content": row[3],
                "after_content": row[4],
                "timestamp": row[5],
            }
