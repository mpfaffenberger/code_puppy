"""Agent-facing tools for yantrik_memory.

Tool surface (kept minimal but working):

* ``yantrik_recall``   — semantic search over learned memory (banded)
* ``yantrik_remember`` — explicit write of a durable fact
* ``yantrik_stats``    — store totals + enabled state

All tools share a single ``register_tools_callback`` plugin entrypoint and are
fully fail-soft: a tool never raises, it returns an ``error`` string instead.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from . import substrate
from .config import DB_PATH, HISTORY_TOP_K, PREFS_BAND_SIZE, YANTRIK_MEM_ROOT
from .state import DISABLED_TOOL_ERROR, is_enabled


class YantrikMemoryItem(BaseModel):
    """A single recalled memory in tool-output form."""

    text: str
    band: str  # "current" | "history"
    importance: float | None = None
    memory_type: str | None = None
    rid: str | None = None


class YantrikRecallOutput(BaseModel):
    query: str
    total: int
    memories: list[YantrikMemoryItem] = Field(default_factory=list)
    error: str | None = None


class YantrikRememberOutput(BaseModel):
    text: str
    importance: float
    namespace: str
    stored: bool = False
    error: str | None = None


class YantrikStatsOutput(BaseModel):
    db_path: str
    namespace: str
    enabled: bool
    total_semantic: int
    error: str | None = None


def _open() -> "substrate.Memory":
    YANTRIK_MEM_ROOT.mkdir(parents=True, exist_ok=True)
    ns = substrate.namespace_for_cwd()
    return substrate.Memory(str(DB_PATH), namespace=ns)


def _rid_of(m: dict) -> str | None:
    v = (m or {}).get("rid") or (m or {}).get("id")
    return str(v) if v is not None else None


def register_yantrik_recall(agent: Any) -> None:
    @agent.tool
    async def yantrik_recall(
        context: RunContext,
        query: str,
        top_k: int = HISTORY_TOP_K,
    ) -> YantrikRecallOutput:
        """Search learned memory (YantrikDB) for relevant facts and history.

        Returns two bands: ``current`` (authoritative durable facts/prefs,
        post-supersession) and ``history`` (query-relevant past context).

        Args:
            query: Free-form text to search for.
            top_k: Number of history items to return (1-20).
        """
        if not is_enabled():
            return YantrikRecallOutput(
                query=query or "", total=0, error=DISABLED_TOOL_ERROR
            )
        if not substrate.MEMORY_AVAILABLE:
            return YantrikRecallOutput(
                query=query or "", total=0, error="YantrikDB is not available."
            )
        if not query or not query.strip():
            return YantrikRecallOutput(
                query=query or "", total=0, error="Empty query — nothing to search."
            )
        try:
            top_k = max(1, min(int(top_k), 20))
        except (TypeError, ValueError):
            top_k = HISTORY_TOP_K

        mem = None
        try:
            mem = _open()
            current, history = mem.recall_banded(
                query, top_k=top_k, n_prefs=PREFS_BAND_SIZE
            )
            items: list[YantrikMemoryItem] = []
            for m in current:
                items.append(
                    YantrikMemoryItem(
                        text=str((m or {}).get("text", "")),
                        band="current",
                        importance=(m or {}).get("importance"),
                        memory_type=(m or {}).get("memory_type"),
                        rid=_rid_of(m),
                    )
                )
            for m in history:
                items.append(
                    YantrikMemoryItem(
                        text=str((m or {}).get("text", "")),
                        band="history",
                        importance=(m or {}).get("importance"),
                        memory_type=(m or {}).get("memory_type"),
                        rid=_rid_of(m),
                    )
                )
            return YantrikRecallOutput(
                query=query, total=len(items), memories=items
            )
        except Exception as exc:  # noqa: BLE001
            return YantrikRecallOutput(
                query=query, total=0, error=f"yantrik_recall failed: {exc!r}"
            )
        finally:
            if mem is not None:
                mem.close()


def register_yantrik_remember(agent: Any) -> None:
    @agent.tool
    async def yantrik_remember(
        context: RunContext,
        text: str,
        importance: float = 0.7,
    ) -> YantrikRememberOutput:
        """Save a durable fact / preference to learned memory.

        Use this when the user says "remember that..." or when you learn
        something durable that future sessions should know. Stored as a
        ``semantic`` memory in the current project's namespace.

        Args:
            text: The durable fact to remember. Required.
            importance: 0.0-1.0 priority (default 0.7). Higher = surfaced first.
        """
        if not is_enabled():
            return YantrikRememberOutput(
                text=text or "",
                importance=importance,
                namespace="",
                error=DISABLED_TOOL_ERROR,
            )
        if not substrate.MEMORY_AVAILABLE:
            return YantrikRememberOutput(
                text=text or "",
                importance=importance,
                namespace="",
                error="YantrikDB is not available.",
            )
        if not text or not text.strip():
            return YantrikRememberOutput(
                text="",
                importance=importance,
                namespace="",
                error="Empty text — nothing to remember.",
            )
        try:
            importance = max(0.0, min(float(importance), 1.0))
        except (TypeError, ValueError):
            importance = 0.7

        mem = None
        try:
            mem = _open()
            mem.remember(
                text.strip(),
                kind="semantic",
                importance=importance,
                metadata={"explicit": True},
            )
            mem.flush()
            return YantrikRememberOutput(
                text=text.strip(),
                importance=importance,
                namespace=mem.ns,
                stored=True,
            )
        except Exception as exc:  # noqa: BLE001
            return YantrikRememberOutput(
                text=text,
                importance=importance,
                namespace="",
                error=f"yantrik_remember failed: {exc!r}",
            )
        finally:
            if mem is not None:
                mem.close()


def register_yantrik_stats(agent: Any) -> None:
    @agent.tool
    async def yantrik_stats(context: RunContext) -> YantrikStatsOutput:
        """Return learned-memory totals for the current project namespace."""
        ns = ""
        try:
            ns = substrate.namespace_for_cwd()
        except Exception:
            ns = "default"
        if not substrate.MEMORY_AVAILABLE:
            return YantrikStatsOutput(
                db_path=str(DB_PATH),
                namespace=ns,
                enabled=is_enabled(),
                total_semantic=0,
                error="YantrikDB is not available.",
            )
        mem = None
        try:
            mem = _open()
            total = len(mem.list_semantic(limit=10000))
            return YantrikStatsOutput(
                db_path=str(DB_PATH),
                namespace=mem.ns,
                enabled=is_enabled(),
                total_semantic=total,
            )
        except Exception as exc:  # noqa: BLE001
            return YantrikStatsOutput(
                db_path=str(DB_PATH),
                namespace=ns,
                enabled=is_enabled(),
                total_semantic=0,
                error=f"yantrik_stats failed: {exc!r}",
            )
        finally:
            if mem is not None:
                mem.close()


def register_tools_callback() -> list[dict[str, Any]]:
    """``register_tools`` callback — exposes the yantrik tool surface."""
    return [
        {"name": "yantrik_recall", "register_func": register_yantrik_recall},
        {"name": "yantrik_remember", "register_func": register_yantrik_remember},
        {"name": "yantrik_stats", "register_func": register_yantrik_stats},
    ]
