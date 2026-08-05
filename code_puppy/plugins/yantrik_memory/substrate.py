"""Single-substrate learning memory over YantrikDB (ported into the plugin).

YantrikDB IS the whole memory: episodic (verbatim turns), semantic (durable
facts/preferences), procedural (skills) — plus graph, importance, decay,
reinforcement, and native consolidation/conflict. No SQLite layer.

Lessons baked in: production ONNX MiniLM embedder, reopen-before-query (async
HNSW), never-retry-on-queue-full, atomic units. We KEEP the default live-memory
time-weights here (recency SHOULD matter for an agent's working memory).

Self-contained: the only hard dependency is ``yantrikdb_mcp``. Import is
fail-soft — if the engine isn't installable, ``MEMORY_AVAILABLE`` is ``False``
and the rest of the plugin disables itself.
"""

from __future__ import annotations

import os
import time

from .config import EMBEDDER

# YantrikDB reads the embedder choice off the environment at import time, so we
# set it BEFORE importing the engine. Default is the production ONNX MiniLM.
os.environ.setdefault("YANTRIKDB_EMBEDDER", EMBEDDER)

try:  # fail-soft: a missing engine disables the whole plugin, never crashes boot.
    from yantrikdb_mcp.embedder import load_engine

    MEMORY_AVAILABLE = True
    IMPORT_ERROR: Exception | None = None
except Exception as exc:  # noqa: BLE001 — any import failure means "unavailable".
    load_engine = None  # type: ignore[assignment]
    MEMORY_AVAILABLE = False
    IMPORT_ERROR = exc


def namespace_for_cwd(cwd: str | os.PathLike | None = None) -> str:
    """Slug the current working directory into a stable namespace.

    Memory is partitioned per project directory (analogous to the kennel's
    repo wings). The slug is filesystem-derived and stable across sessions so
    a repo's learned facts persist and don't bleed into other projects.
    """
    raw = str(cwd) if cwd is not None else os.getcwd()
    slug = "".join(c if c.isalnum() else "-" for c in raw.lower())
    slug = "-".join(p for p in slug.split("-") if p)  # collapse runs of '-'
    return slug or "default"


class Memory:
    """Thin wrapper over a YantrikDB engine instance, scoped to a namespace."""

    def __init__(self, db_path: str, namespace: str = "default"):
        self._path = db_path
        self.ns = namespace
        self.db = load_engine(db_path)

    # ---- write ----
    def remember(self, text, kind="episodic", importance=0.5, metadata=None):
        """kind: 'episodic' (turns) | 'semantic' (durable facts) | 'procedural'."""
        try:
            return self.db.record(
                text=text,
                memory_type=kind,
                importance=importance,
                metadata=metadata or {},
                namespace=self.ns,
            )
        except RuntimeError as e:
            if "queue full" not in str(e):
                raise
            time.sleep(0.1)  # already enqueued; never retry (would duplicate)

    def flush(self):
        """Drain the async queue + reopen so the HNSW index is built before query."""
        time.sleep(1.0)
        self.db.close()
        self.db = load_engine(self._path)

    def think(self):
        """Native cognitive cycle: conflict detection + episodic->semantic consolidation."""
        try:
            self.db.think()
        except Exception:
            pass

    def correct(self, rid, new_text, importance=None):
        self.db.correct(rid, new_text=new_text, new_importance=importance)

    def reinforce(self, rid, outcome):
        self.db.reinforce_procedural(rid, outcome)

    def learn_skill(self, text, effectiveness=0.5, domain="general", metadata=None):
        return self.db.record_procedural(
            text=text, effectiveness=effectiveness, domain=domain, namespace=self.ns
        )

    def surface_skills(self, query, top_k=5, domain="general"):
        emb = self.db.embed(query)
        return self._norm(
            self.db.surface_procedural(
                query_embedding=emb,
                query_text=query,
                domain=domain,
                top_k=top_k,
                namespace=self.ns,
            )
        )

    def relate(self, src, dst, rel="related_to"):
        try:
            self.db.relate(src, dst, rel)
        except Exception:
            pass

    # ---- read ----
    def _norm(self, r):
        return r["results"] if isinstance(r, dict) and "results" in r else (r or [])

    def recall(self, query, top_k=8):
        return self._norm(
            self.db.recall(
                query=query, top_k=top_k, namespace=self.ns, skip_reinforce=True
            )
        )

    def list_semantic(self, limit=100):
        """Return all durable (semantic) memories in this namespace."""
        r = self.db.list_memories(
            memory_type="semantic", namespace=self.ns, limit=limit
        )
        return (r or {}).get("memories", []) if isinstance(r, dict) else (r or [])

    def prefs(self, top_n=5):
        """Always-include the highest-importance durable facts (a 'P0 prefs' band)."""
        mems = self.list_semantic(limit=100)
        mems = sorted(
            mems, key=lambda m: (m or {}).get("importance", 0.0), reverse=True
        )
        return mems[:top_n]

    def recall_for_prompt(self, query, top_k=8, n_prefs=5):
        """What the agent actually sees: always-on prefs + query-relevant memories."""
        out, seen = [], set()
        for m in self.prefs(n_prefs) + self.recall(query, top_k):
            key = (m or {}).get("rid") or (m or {}).get("text")
            if key and key not in seen:
                seen.add(key)
                out.append(m)
        return out

    def recall_banded(self, query, top_k=8, n_prefs=5):
        """Two bands: CURRENT (authoritative semantic facts/prefs, post-correction)
        and HISTORY (query-relevant episodic/events, e.g. 'like last time'). A
        superseded value stays OUT of CURRENT even though it still (truthfully)
        exists in the verbatim episodic log."""
        current = self.prefs(n_prefs)
        cur_keys = {(m or {}).get("rid") for m in current}
        history = [
            m for m in self.recall(query, top_k) if (m or {}).get("rid") not in cur_keys
        ]
        return current, history

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass
