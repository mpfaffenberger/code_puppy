"""Multi-session isolation layer for Code Puppy.

Provides per-session state management so that each browser tab / WebSocket
connection gets its own agent instance, model selection, working directory,
and message history — without touching any global singletons.

Usage:
    from code_puppy.api.session_context import session_manager

    ctx = session_manager.create_session("my-session-123")
    ctx.agent.run_sync("Hello!")  # uses the session’s own agent
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from code_puppy.agents.agent_manager import get_available_agents, load_agent
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.api.db.message_utils import (
    extract_content,
    extract_thinking,
    get_message_timestamp,
    get_role,
    pydantic_json_for_message,
)
from code_puppy.config import get_global_model_name

logger = logging.getLogger(__name__)


def _apply_session_model(agent: Any, model_name: Optional[str]) -> None:
    """Best-effort session-model setter for migration compatibility.

    Some migrated/legacy agent classes may not yet implement
    ``set_session_model``. In that case we set the internal override field
    directly to avoid failing model switches at runtime.
    """
    setter = getattr(agent, "set_session_model", None)
    if callable(setter):
        setter(model_name)
        return

    # Last-resort compatibility for older agent implementations
    try:
        setattr(agent, "_session_model_name", model_name or None)
    except Exception:
        pass


def _reload_agent_if_supported(agent: Any) -> None:
    reloader = getattr(agent, "reload_code_generation_agent", None)
    if callable(reloader):
        reloader()


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_SAFE_SESSION_ID_RE = re.compile(r"^[\w.\-]{1,256}$", re.ASCII)


def _validate_session_id(session_id: str) -> None:
    """Reject session IDs that could cause path-traversal or other mischief."""
    if not session_id or not _SAFE_SESSION_ID_RE.match(session_id):
        raise ValueError(
            f"Invalid session_id: {session_id!r}. "
            "Must be 1–256 chars of [a-zA-Z0-9_.-]."
        )
    # Extra guard: no `..` anywhere
    if ".." in session_id:
        raise ValueError(f"Path traversal detected in session_id: {session_id!r}")


def _validate_agent_name(agent_name: str) -> None:
    """Ensure the agent actually exists in the registry."""
    available = get_available_agents()
    if agent_name not in available:
        raise ValueError(
            f"Unknown agent {agent_name!r}. Available: {', '.join(sorted(available))}"
        )


@dataclass
class SessionContext:
    """All mutable state scoped to a single user session.

    Every field lives *only* on this object — nothing is written to global
    singletons like ``_SESSION_MODEL`` or ``_CURRENT_AGENT``.
    """

    session_id: str
    agent: BaseAgent
    agent_name: str
    model_name: str
    working_directory: str
    title: str = ""
    pinned: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    websocket: Any | None = None

    # Per-agent-name history cache (survives agent switches within session)
    _saved_histories: Dict[str, List[Any]] = field(default_factory=dict)
    # Per-agent-name compacted-message hashes
    _compacted_hashes: Dict[str, Set[str]] = field(default_factory=dict)
    # Serialises mutations (switch_agent, switch_model, save) on this session.
    # Stored as Optional so it can be created lazily inside a running event loop.
    _op_lock: Optional[asyncio.Lock] = field(default=None, repr=False, compare=False)

    @property
    def op_lock(self) -> asyncio.Lock:
        """Lazy asyncio.Lock — created on first access inside the event loop."""
        if self._op_lock is None:
            self._op_lock = asyncio.Lock()
        return self._op_lock

    async def switch_agent_inline(self, new_agent_name: str) -> "BaseAgent":
        """Hot-swap the agent on this context, preserving/restoring history.

        Unlike SessionManager.switch_agent(), operates directly on self without
        requiring a session_id lookup. Used by MuxChatHandler which manages
        the runtime reference directly.

        Returns:
            The newly loaded BaseAgent.
        """
        from code_puppy.agent_loader import load_agent  # local to avoid circular import

        old_name = self.agent_name

        async with self.op_lock:
            # Persist outgoing agent state
            if hasattr(self.agent, "get_message_history"):
                self._saved_histories[old_name] = self.agent.get_message_history()
            if hasattr(self.agent, "get_compacted_message_hashes"):
                self._compacted_hashes[old_name] = (
                    self.agent.get_compacted_message_hashes()
                )

            # Load new agent
            new_agent = load_agent(new_agent_name)

            # Restore history if we've visited this agent before
            if new_agent_name in self._saved_histories and hasattr(
                new_agent, "set_message_history"
            ):
                new_agent.set_message_history(self._saved_histories[new_agent_name])
            if new_agent_name in self._compacted_hashes and hasattr(
                new_agent, "add_compacted_message_hash"
            ):
                for h in self._compacted_hashes[new_agent_name]:
                    new_agent.add_compacted_message_hash(h)

            # Carry session model across
            _apply_session_model(new_agent, self.model_name)
            _reload_agent_if_supported(new_agent)

            self.agent = new_agent
            self.agent_name = new_agent_name

        return new_agent


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class SessionManager:
    """Thread-safe registry of active ``SessionContext`` instances."""

    _SESSION_RETENTION_SECONDS = 15 * 60  # 15 minutes

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionContext] = {}
        self._lock = asyncio.Lock()
        self._inactive_since: Dict[
            str, datetime
        ] = {}  # Track when session became inactive
        self._cleanup_task: Optional[asyncio.Task] = None  # Background cleanup task

    # -- creation / lookup / teardown ------------------------------------

    async def create_session(
        self,
        session_id: str,
        agent_name: str = "code-puppy",
        model_name: Optional[str] = None,
        working_directory: str = "",
    ) -> SessionContext:
        """Spin up a brand-new isolated session.

        Args:
            session_id: Unique identifier (validated for path safety).
            agent_name: Which agent to load (default ``code-puppy``).
            model_name: Session-local model override. ``None`` → global default.
            working_directory: Session-local CWD (never calls ``os.chdir``).

        Returns:
            The freshly-created ``SessionContext``.

        Raises:
            ValueError: On invalid *session_id* or unknown *agent_name*.
        """
        _validate_session_id(session_id)
        _validate_agent_name(agent_name)

        agent = load_agent(agent_name)
        resolved_model = model_name or get_global_model_name()

        if model_name is not None:
            _apply_session_model(agent, model_name)

        ctx = SessionContext(
            session_id=session_id,
            agent=agent,
            agent_name=agent_name,
            model_name=resolved_model,
            working_directory=working_directory,
        )

        async with self._lock:
            self._sessions[session_id] = ctx

        logger.info(
            "Session created: id=%s agent=%s model=%s",
            session_id,
            agent_name,
            resolved_model,
        )
        return ctx

    async def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Look up an active session. Returns ``None`` if not found."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def destroy_session(self, session_id: str) -> None:
        """Remove a session from the registry."""
        async with self._lock:
            removed = self._sessions.pop(session_id, None)
        if removed:
            logger.info("Session destroyed: id=%s", session_id)
        else:
            logger.warning("destroy_session called for unknown id=%s", session_id)

    # -- agent switching -------------------------------------------------

    async def switch_agent(
        self,
        session_id: str,
        new_agent_name: str,
    ) -> BaseAgent:
        """Hot-swap the agent inside an existing session.

        * Saves current agent’s history & compacted hashes.
        * Loads a fresh agent for *new_agent_name*.
        * Restores any previously-saved history if switching *back*.
        * Carries over the session model.

        Returns:
            The newly-loaded ``BaseAgent``.

        Raises:
            KeyError: If *session_id* is unknown.
            ValueError: If *new_agent_name* is invalid.
        """
        ctx = await self._require_session(session_id)
        _validate_agent_name(new_agent_name)

        async with ctx.op_lock:  # Serialise all mutations on this session
            old_name = ctx.agent_name

            # Persist outgoing agent's state
            ctx._saved_histories[old_name] = ctx.agent.get_message_history()
            ctx._compacted_hashes[old_name] = ctx.agent.get_compacted_message_hashes()

            # Build the replacement agent
            new_agent = load_agent(new_agent_name)

            # Restore history if we've visited this agent before
            if new_agent_name in ctx._saved_histories:
                new_agent.set_message_history(ctx._saved_histories[new_agent_name])
            if new_agent_name in ctx._compacted_hashes:
                for h in ctx._compacted_hashes[new_agent_name]:
                    new_agent.add_compacted_message_hash(h)

            # Carry session model across agents
            _apply_session_model(new_agent, ctx.model_name)
            _reload_agent_if_supported(new_agent)

            ctx.agent = new_agent
            ctx.agent_name = new_agent_name

        logger.info(
            "Session %s: switched agent %s → %s",
            session_id,
            old_name,
            new_agent_name,
        )
        return new_agent

    # -- model switching -------------------------------------------------

    async def switch_model(self, session_id: str, new_model: str) -> None:
        """Change the model for a session without touching global config.

        Raises:
            KeyError: If *session_id* is unknown.
        """
        ctx = await self._require_session(session_id)
        async with ctx.op_lock:
            ctx.model_name = new_model
            _apply_session_model(ctx.agent, new_model)
            _reload_agent_if_supported(ctx.agent)
        logger.info("Session %s: model → %s", session_id, new_model)

    # -- persistence -----------------------------------------------------

    async def _write_to_sqlite(
        self,
        session_id: str,
        ctx: "SessionContext",
        history: List[Any],
    ) -> None:
        """Write session metadata + any new messages to SQLite.

        Called from save_session() as the sole durable write path.
        All errors are caught — a DB failure never breaks the WS session.

        Uses INSERT OR IGNORE on (session_id, seq) so re-running after a
        partial write is fully idempotent.
        """
        try:
            from code_puppy.api.db.queries import (
                insert_messages_batch,
                update_session_stats,
                upsert_session,
            )
        except Exception as exc:
            logger.debug("SQLite not available, skipping DB write: %s", exc)
            return

        from datetime import datetime
        from datetime import timezone as _tz

        updated_at = datetime.now(_tz.utc).isoformat()

        try:
            # Upsert session row (creates it if this is the first save)
            await upsert_session(
                session_id=session_id,
                title=ctx.title,
                agent_name=ctx.agent_name,
                model_name=ctx.model_name,
                working_directory=ctx.working_directory,
                pinned=ctx.pinned,
                created_at=ctx.created_at.isoformat(),
                updated_at=updated_at,
                message_count=len(history),
                total_tokens=0,  # updated below
                deleted_at=None,
            )
        except Exception as exc:
            logger.warning("Failed to upsert session %s in SQLite: %s", session_id, exc)
            return

        # Build message rows — seq is 1-based index into the full history.
        # INSERT OR IGNORE on UNIQUE(session_id, seq) makes this idempotent.
        message_rows = []
        total_tokens = 0

        for idx, msg in enumerate(history):
            # Skip system dict entries that aren't proper ModelMessages
            if isinstance(msg, dict) and not hasattr(msg, "parts"):
                continue

            seq = idx + 1
            ts = get_message_timestamp(msg) or updated_at
            content = extract_content(msg)
            thinking = extract_thinking(msg)
            pj = pydantic_json_for_message(msg)

            try:
                token_count = ctx.agent.estimate_tokens_for_message(msg)
            except Exception:
                token_count = max(1, len(content) // 4)

            total_tokens += token_count

            message_rows.append(
                {
                    "session_id": session_id,
                    "seq": seq,
                    "role": get_role(msg),
                    "content": content,
                    "type": type(msg).__name__,
                    "agent_name": ctx.agent_name,
                    "model_name": ctx.model_name,
                    "timestamp": ts,
                    "thinking": thinking,
                    "token_count": token_count,
                    "pydantic_json": pj,
                }
            )

        try:
            await insert_messages_batch(message_rows)
        except Exception as exc:
            logger.warning(
                "Failed to insert messages for %s in SQLite: %s", session_id, exc
            )
            return

        # Update the token count now that we've summed it
        try:
            await update_session_stats(
                session_id,
                message_count=len(history),
                total_tokens=total_tokens,
                updated_at=updated_at,
            )
        except Exception as exc:
            logger.warning(
                "Failed to update session stats for %s in SQLite: %s", session_id, exc
            )

        logger.debug(
            "Session %s written to SQLite (%d messages, %d tokens)",
            session_id,
            len(history),
            total_tokens,
        )

    async def save_session(self, session_id: str) -> None:
        """Persist session history and metadata to SQLite (single source of truth).

        Previously wrote session files under {WS_SESSION_DIR} — that legacy file write
        has been removed. SQLite at ~/.puppy_desk/chat_messages.db is now the
        only durable store.

        aiosqlite serialises all DB I/O through its own background thread so
        this coroutine yields to the event loop on every await — no
        thread-pool needed.
        """
        ctx = await self._require_session(session_id)
        _validate_session_id(session_id)

        async with ctx.op_lock:
            history: List[Any] = ctx.agent.get_message_history()

        await self._write_to_sqlite(session_id, ctx, history)
        logger.debug(
            "Session %s saved to SQLite (%d messages)", session_id, len(history)
        )

    async def _load_from_sqlite(
        self, session_id: str
    ) -> Optional[tuple[List[Any], dict]]:
        """Try to load message history + metadata from SQLite.

        Returns (messages, meta_dict) on success, None if SQLite is unavailable
        or the session has no pydantic_json rows (seeded without BE).
        """
        try:
            from code_puppy.api.db.queries import get_active_messages, session_exists
        except Exception:
            return None

        try:
            if not await session_exists(session_id):
                return None

            rows = await get_active_messages(session_id)
            # Filter to only rows with pydantic_json (seeder may leave some NULL).
            # Sessions with no parseable messages still resume — just with empty history.
            rows_with_json = [r for r in rows if r.get("pydantic_json")]

            from pydantic_ai.messages import ModelMessagesTypeAdapter

            messages: List[Any] = []
            for row in rows_with_json:
                try:
                    parsed = ModelMessagesTypeAdapter.validate_json(
                        row["pydantic_json"]
                    )
                    if parsed:
                        messages.append(parsed[0])
                except Exception as exc:
                    logger.warning(
                        "Failed to deserialise message seq=%s for session %s: %s",
                        row.get("seq"),
                        session_id,
                        exc,
                    )

            # Build a metadata dict from the sessions table
            try:
                from code_puppy.api.db.connection import get_db

                db = get_db()
                cursor = await db.execute(
                    "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
                )
                row_s = await cursor.fetchone()
                meta: dict = dict(row_s) if row_s else {}
            except Exception:
                meta = {}

            logger.info(
                "Session %s loaded from SQLite (%d messages)",
                session_id,
                len(messages),
            )
            return messages, meta

        except Exception as exc:
            logger.warning(
                "SQLite load failed for session %s: %s",
                session_id,
                exc,
            )
            return None

    async def load_session(self, session_id: str) -> Optional[SessionContext]:
        """Restore a session from disk, creating a fresh agent.

        Returns ``None`` if no persisted data exists or loading fails.
        """
        _validate_session_id(session_id)

        # ---- try SQLite first (sessions saved by BE write path) ----------
        sqlite_result = await self._load_from_sqlite(session_id)
        if sqlite_result is not None:
            messages, db_meta = sqlite_result

            agent_name = db_meta.get("agent_name", "code-puppy")
            model_name = db_meta.get("model_name", get_global_model_name())
            title = db_meta.get("title", "")
            pinned = bool(db_meta.get("pinned", False))
            working_directory = db_meta.get("working_directory", "")
            created_at_raw = db_meta.get("created_at", "")
            try:
                created_at = (
                    datetime.fromisoformat(created_at_raw)
                    if created_at_raw
                    else datetime.now(timezone.utc)
                )
            except Exception:
                created_at = datetime.now(timezone.utc)

            try:
                agent = load_agent(agent_name)
            except ValueError:
                logger.warning(
                    "Agent %s unavailable, falling back to code-puppy", agent_name
                )
                agent_name = "code-puppy"
                agent = load_agent(agent_name)

            agent.set_message_history(messages)
            _apply_session_model(agent, model_name)

            ctx = SessionContext(
                session_id=session_id,
                agent=agent,
                agent_name=agent_name,
                model_name=model_name,
                working_directory=working_directory,
                title=title,
                pinned=pinned,
                created_at=created_at,
            )

            async with self._lock:
                self._sessions[session_id] = ctx

            return ctx
        # SQLite is the single source of truth — no file fallback.
        # If _load_from_sqlite() returned None the session does not exist in the DB.
        logger.debug("Session %s not found in SQLite — treating as new", session_id)
        return None

    # -- session retention (15-min inactive cleanup) -------------------------

    async def mark_session_inactive(self, session_id: str) -> None:
        """Mark a session as inactive (WS disconnected). Starts retention timer."""
        async with self._lock:
            if session_id in self._sessions:
                self._inactive_since[session_id] = datetime.now(timezone.utc)
                logger.debug(
                    "Session %s marked inactive, will be cleaned up in 15 min",
                    session_id,
                )
        # Ensure cleanup task is running
        self._ensure_cleanup_task()

    async def mark_session_active(self, session_id: str) -> None:
        """Mark a session as active (WS connected). Cancels pending cleanup."""
        async with self._lock:
            self._inactive_since.pop(session_id, None)
            logger.debug("Session %s marked active", session_id)

    def _ensure_cleanup_task(self) -> None:
        """Start the background cleanup task if not already running."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_inactive_sessions())

    async def _cleanup_inactive_sessions(self) -> None:
        """Background task that cleans up sessions inactive for > 15 minutes."""
        while True:
            await asyncio.sleep(60)  # Check every minute
            now = datetime.now(timezone.utc)
            to_cleanup: List[str] = []

            async with self._lock:
                for session_id, inactive_time in list(self._inactive_since.items()):
                    elapsed = (now - inactive_time).total_seconds()
                    if elapsed > self._SESSION_RETENTION_SECONDS:
                        to_cleanup.append(session_id)

            for session_id in to_cleanup:
                logger.info(
                    "Cleaning up inactive session %s (inactive > 15 min)", session_id
                )
                await self.destroy_session(session_id)
                async with self._lock:
                    self._inactive_since.pop(session_id, None)

            # Stop task if no more inactive sessions to monitor
            async with self._lock:
                if not self._inactive_since:
                    break

    async def get_or_load_session(self, session_id: str) -> Optional[SessionContext]:
        """Get an existing in-memory session OR load from SQLite.

        This is the preferred method for session access - it checks
        in-memory first (including inactive sessions pending cleanup),
        then falls back to SQLite load.
        """
        # First check if session exists in memory (active or inactive)
        async with self._lock:
            ctx = self._sessions.get(session_id)
            if ctx is not None:
                # Session exists in memory - mark it active and return
                self._inactive_since.pop(session_id, None)
                logger.debug("Reusing in-memory session %s", session_id)
                return ctx

        # Not in memory - try to load from SQLite
        return await self.load_session(session_id)

        # -- internal helpers ------------------------------------------------

    async def _require_session(self, session_id: str) -> SessionContext:
        """Return the session or raise ``KeyError``."""
        async with self._lock:
            ctx = self._sessions.get(session_id)
        if ctx is None:
            raise KeyError(f"No active session with id={session_id!r}")
        return ctx


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

session_manager = SessionManager()
