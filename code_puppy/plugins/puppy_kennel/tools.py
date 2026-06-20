"""Agent-facing tools for the puppy_kennel.

Full tool surface:

* ``kennel_recall``     — BM25 search across wings
* ``kennel_remember``   — explicit verbatim write to a chosen wing
* ``kennel_recent``     — recent drawers without a query (timeline view)
* ``kennel_list_wings`` — discover wings + drawer counts
* ``kennel_stats``      — kennel-wide totals + on-disk size

All tools share a single ``register_tools_callback`` plugin entrypoint.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from . import kennel
from .config import DB_PATH
from .state import DISABLED_TOOL_ERROR, is_enabled
from .wings import (
    USER_WING,
    agent_wing,
    default_recall_scope,
    detect_cwd,
    repo_wing,
)


class KennelDrawer(BaseModel):
    """A single recalled drawer in tool output form."""

    id: int
    room_id: int
    role: str | None = None
    content: str
    ts: str
    session_id: str | None = None
    agent: str | None = None
    cwd: str | None = None


class KennelRecallOutput(BaseModel):
    """Output for ``kennel_recall``."""

    query: str
    wings_searched: list[str]
    total_hits: int
    drawers: list[KennelDrawer] = Field(default_factory=list)
    error: str | None = None


class KennelRememberOutput(BaseModel):
    """Output for ``kennel_remember``."""

    drawer_id: int
    wing: str
    room: str
    bytes_stored: int
    error: str | None = None


class KennelRecentOutput(BaseModel):
    """Output for ``kennel_recent``."""

    wings_searched: list[str]
    total: int
    drawers: list[KennelDrawer] = Field(default_factory=list)
    error: str | None = None


class WingInfo(BaseModel):
    name: str
    drawer_count: int


class KennelWingsOutput(BaseModel):
    """Output for ``kennel_list_wings``."""

    wings: list[WingInfo] = Field(default_factory=list)
    total_wings: int
    error: str | None = None


class KennelStatsOutput(BaseModel):
    """Output for ``kennel_stats``."""

    db_path: str
    db_size_bytes: int
    total_drawers: int
    total_wings: int
    error: str | None = None


def _drawer_to_model(d: Any) -> KennelDrawer:
    meta = d.metadata or {}
    return KennelDrawer(
        id=d.id,
        room_id=d.room_id,
        role=d.role,
        content=d.content,
        ts=d.ts,
        session_id=d.session_id,
        agent=meta.get("agent"),
        cwd=meta.get("cwd"),
    )


def _resolve_wing(value: str, agent_name: str, cwd: Any) -> str:
    """Turn a wing shortcut into a concrete wing name.

    Shortcuts:
        ``"repo"``   -> current repo wing (the default for writes)
        ``"agent"``  -> this agent's diary wing
        ``"user"``   -> the global user-prefs wing
        ``""``       -> defaults to ``repo`` (most writes are project-scoped)
        anything else is treated as an explicit wing name.
    """
    v = (value or "").strip()
    if v == "" or v == "repo":
        return repo_wing(cwd)
    if v == "agent":
        return agent_wing(agent_name)
    if v == "user":
        return USER_WING
    return v


def _resolve_scope(wing: str, scope: str, agent_name: str, cwd: Any) -> list[str]:
    """Turn (wing, scope) into the list of wings to search.

    Returns an empty list to mean "no wing filter — search everything."
    """
    w = (wing or "").strip()
    if w:
        return [_resolve_wing(w, agent_name, cwd)]
    if scope == "repo":
        return [repo_wing(cwd)]
    if scope == "agent":
        return [agent_wing(agent_name)]
    if scope == "user":
        return [USER_WING]
    if scope == "all":
        return []  # caller treats empty as "no filter"
    # "default" or anything weird
    return default_recall_scope(agent_name, cwd)


def register_kennel_recall(agent: Any) -> None:
    """Register the ``kennel_recall`` tool on the given agent."""

    @agent.tool
    async def kennel_recall(
        context: RunContext,
        query: str,
        wing: str = "",
        top_k: int = 5,
        scope: str = "default",
    ) -> KennelRecallOutput:
        """Search the Mist Memory for relevant past drawers (verbatim memories).

        The kennel stores prior agent responses scoped by wing:
        * ``repo:<path>``  — project memory shared across agents in that repo
        * ``agent:<name>`` — this agent's private diary
        * ``user:default`` — cross-cutting user preferences

        Args:
            query:  Free-form text. FTS5 BM25 ranks results.
            wing:   Restrict to a single wing (e.g. ``"repo:/Users/me/foo"``).
                    Leave blank to use ``scope``.
            top_k:  Number of drawers to return (default 5, max 20).
            scope:  When ``wing`` is empty, choose the wing set:
                    * ``"default"`` — repo + this agent + user (sensible default)
                    * ``"repo"``    — only the current repo wing
                    * ``"agent"``   — only this agent's diary
                    * ``"all"``     — every wing (use sparingly)

        Returns drawers ordered by BM25 relevance, deduplicated by content.
        """
        if not is_enabled():
            return KennelRecallOutput(
                query=query or "",
                wings_searched=[],
                total_hits=0,
                error=DISABLED_TOOL_ERROR,
            )
        try:
            top_k = max(1, min(int(top_k), 20))
        except (TypeError, ValueError):
            top_k = 5

        if not query or not query.strip():
            return KennelRecallOutput(
                query=query or "",
                wings_searched=[],
                total_hits=0,
                error="Empty query — provide some text to search for.",
            )

        try:
            agent_name = _agent_name_from_context(context)
            cwd = detect_cwd()
            wings_to_search = _resolve_scope(wing, scope, agent_name, cwd)

            hits = kennel.search_drawers_multi(
                query=query,
                wing_names=wings_to_search or None,
                limit=top_k,
            )
            return KennelRecallOutput(
                query=query,
                wings_searched=wings_to_search,
                total_hits=len(hits),
                drawers=[_drawer_to_model(d) for d in hits],
            )
        except Exception as exc:  # noqa: BLE001 — tool must never raise.
            return KennelRecallOutput(
                query=query,
                wings_searched=[],
                total_hits=0,
                error=f"kennel_recall failed: {exc!r}",
            )


def register_kennel_remember(agent: Any) -> None:
    """Register the ``kennel_remember`` tool — explicit verbatim write."""

    @agent.tool
    async def kennel_remember(
        context: RunContext,
        content: str,
        wing: str = "repo",
        room: str = "notes",
    ) -> KennelRememberOutput:
        """Save a verbatim note to the Mist Memory.

        Use this when the user says "remember that..." or when you learn
        something durable that future sessions should know about. Writes
        are best-effort; failures return an error string rather than raising.

        **Pick the wing deliberately — it determines who sees this memory:**

        * ``"repo"`` (default) — facts about THIS project: architectural
          decisions, gotchas, conventions, why-we-chose-X. Anyone working
          in this repo will see it. Use this for most "remember that..."
          requests during project work.
        * ``"user"`` — facts about the user (Mike): preferences, style,
          biographical detail. Pervasive across every repo and every
          agent. Use sparingly — only for cross-cutting truths.
        * ``"agent"`` — cross-project learnings about your own behavior
          or limitations. Rare. Most "agent" notes are actually project
          notes wearing a costume — prefer ``"repo"`` unless the lesson
          genuinely transcends projects.

        Args:
            content: The verbatim text to remember. Required.
            wing:    ``"repo"`` (default) / ``"user"`` / ``"agent"`` /
                     or an explicit wing name like ``"team:platform"``.
            room:    Room name within the wing. Defaults to ``"notes"``.
                     Use ``"preferences"`` for user-wing writes,
                     ``"decisions"`` for project-wide architectural calls.
        """
        if not is_enabled():
            return KennelRememberOutput(
                drawer_id=0,
                wing="",
                room=room,
                bytes_stored=0,
                error=DISABLED_TOOL_ERROR,
            )
        if not content or not content.strip():
            return KennelRememberOutput(
                drawer_id=0,
                wing="",
                room=room,
                bytes_stored=0,
                error="Empty content — nothing to remember.",
            )
        try:
            agent_name = _agent_name_from_context(context)
            cwd = detect_cwd()
            resolved_wing = _resolve_wing(wing, agent_name, cwd)
            drawer_id = kennel.write_note(
                wing_name=resolved_wing,
                room_name=(room or "notes").strip() or "notes",
                content=content,
                role="note",
                metadata={"agent": agent_name, "cwd": str(cwd), "explicit": True},
            )
            return KennelRememberOutput(
                drawer_id=drawer_id,
                wing=resolved_wing,
                room=room or "notes",
                bytes_stored=len(content.encode("utf-8")),
            )
        except Exception as exc:  # noqa: BLE001
            return KennelRememberOutput(
                drawer_id=0,
                wing=wing,
                room=room,
                bytes_stored=0,
                error=f"kennel_remember failed: {exc!r}",
            )


def register_kennel_recent(agent: Any) -> None:
    """Register the ``kennel_recent`` tool — time-ordered drawer browsing."""

    @agent.tool
    async def kennel_recent(
        context: RunContext,
        wing: str = "",
        top_k: int = 5,
        scope: str = "default",
    ) -> KennelRecentOutput:
        """List recent drawers without a query. Useful for orienting on a new session.

        Args:
            wing:   Restrict to a single wing (or shortcut: "repo", "agent", "user").
                    Leave blank to use ``scope``.
            top_k:  Number of drawers (1-50, default 5).
            scope:  When ``wing`` is blank: ``"default"`` / ``"repo"`` / ``"agent"``
                    / ``"user"`` / ``"all"``. Same semantics as ``kennel_recall``.

        Returns drawers newest-first, deduplicated by content.
        """
        if not is_enabled():
            return KennelRecentOutput(
                wings_searched=[],
                total=0,
                error=DISABLED_TOOL_ERROR,
            )
        try:
            top_k = max(1, min(int(top_k), 50))
        except (TypeError, ValueError):
            top_k = 5
        try:
            agent_name = _agent_name_from_context(context)
            cwd = detect_cwd()
            wings_to_search = _resolve_scope(wing, scope, agent_name, cwd)
            hits = kennel.recent_drawers_multi(
                wing_names=wings_to_search or None,
                limit=top_k,
            )
            return KennelRecentOutput(
                wings_searched=wings_to_search,
                total=len(hits),
                drawers=[_drawer_to_model(d) for d in hits],
            )
        except Exception as exc:  # noqa: BLE001
            return KennelRecentOutput(
                wings_searched=[],
                total=0,
                error=f"kennel_recent failed: {exc!r}",
            )


def register_kennel_list_wings(agent: Any) -> None:
    """Register the ``kennel_list_wings`` tool — wing discovery."""

    @agent.tool
    async def kennel_list_wings(context: RunContext) -> KennelWingsOutput:
        """List every wing in the kennel with its drawer count.

        Use this to discover what memory partitions exist before scoping a
        ``kennel_recall`` or ``kennel_recent`` call.
        """
        if not is_enabled():
            return KennelWingsOutput(wings=[], total_wings=0, error=DISABLED_TOOL_ERROR)
        try:
            pairs = kennel.wings_with_counts()
            return KennelWingsOutput(
                wings=[WingInfo(name=n, drawer_count=c) for n, c in pairs],
                total_wings=len(pairs),
            )
        except Exception as exc:  # noqa: BLE001
            return KennelWingsOutput(
                wings=[],
                total_wings=0,
                error=f"kennel_list_wings failed: {exc!r}",
            )


def register_kennel_stats(agent: Any) -> None:
    """Register the ``kennel_stats`` tool — kennel-wide totals + size."""

    @agent.tool
    async def kennel_stats(context: RunContext) -> KennelStatsOutput:
        """Return kennel-wide totals: drawers, wings, and on-disk size.

        Useful for gating behavior — e.g. skip recall on an empty kennel.
        """
        if not is_enabled():
            return KennelStatsOutput(
                db_path=str(DB_PATH),
                db_size_bytes=0,
                total_drawers=0,
                total_wings=0,
                error=DISABLED_TOOL_ERROR,
            )
        try:
            size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
            return KennelStatsOutput(
                db_path=str(DB_PATH),
                db_size_bytes=size,
                total_drawers=kennel.count_drawers(),
                total_wings=len(kennel.list_wings()),
            )
        except Exception as exc:  # noqa: BLE001
            return KennelStatsOutput(
                db_path=str(DB_PATH),
                db_size_bytes=0,
                total_drawers=0,
                total_wings=0,
                error=f"kennel_stats failed: {exc!r}",
            )


def _agent_name_from_context(context: RunContext) -> str:
    """Best-effort extraction of the calling agent's name from the run context.

    Falls back to ``"unknown"`` if the framework doesn't expose it on this
    version of pydantic_ai.
    """
    for attr in ("agent_name", "name"):
        val = getattr(context, attr, None)
        if val:
            return str(val)
    deps = getattr(context, "deps", None)
    if deps is not None:
        for attr in ("agent_name", "name"):
            val = getattr(deps, attr, None)
            if val:
                return str(val)
    return "unknown"


def register_tools_callback() -> list[dict[str, Any]]:
    """``register_tools`` callback — exposes the full kennel tool surface."""
    return [
        {"name": "kennel_recall", "register_func": register_kennel_recall},
        {"name": "kennel_remember", "register_func": register_kennel_remember},
        {"name": "kennel_recent", "register_func": register_kennel_recent},
        {"name": "kennel_list_wings", "register_func": register_kennel_list_wings},
        {"name": "kennel_stats", "register_func": register_kennel_stats},
    ]
