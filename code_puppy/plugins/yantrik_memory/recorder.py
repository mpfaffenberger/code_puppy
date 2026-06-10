"""Recorder — turns conversation into learned memory.

Two entry points:

* ``distill_user_message(prompt, session_id)`` — fires on ``user_prompt_submit``.
  Logs the raw turn as an ``episodic`` memory AND distills durable facts into
  ``semantic`` memory (learning new facts, superseding updated ones).

* ``record_response(...)`` — fires on ``agent_run_end``. Logs the agent's final
  response as an ``episodic`` memory.

The "fact -> rid" map needed for supersession is **reconstructed from the store
on every turn** (each callback is a fresh process state): we list the namespace's
semantic memories (text -> rid), feed those texts to the distiller as
``existing_facts``, and when the distiller flags an ``updates`` match we call
``substrate.correct(rid, new_text)`` instead of inserting a duplicate.

Everything here is best-effort and fail-soft: the memory layer must never crash
the host app or a turn.
"""

from __future__ import annotations

from typing import Any

from code_puppy.messaging.bus import emit_debug

from . import substrate
from .config import DB_PATH, MAX_KNOWN_FACTS, YANTRIK_MEM_ROOT
from .distiller import extract
from .state import is_enabled


def _open_memory() -> "substrate.Memory | None":
    """Open a namespace-scoped Memory handle for the current cwd. Fail-soft."""
    if not substrate.MEMORY_AVAILABLE:
        return None
    try:
        YANTRIK_MEM_ROOT.mkdir(parents=True, exist_ok=True)
        ns = substrate.namespace_for_cwd()
        return substrate.Memory(str(DB_PATH), namespace=ns)
    except Exception as exc:  # noqa: BLE001
        emit_debug(f"[yantrik_memory] open failed: {exc!r}")
        return None


def _rid_of(r: Any) -> Any:
    """Normalize a record() return into a record id."""
    if isinstance(r, str):
        return r
    if isinstance(r, dict):
        return r.get("rid") or r.get("id")
    return None


def _known_facts(mem: "substrate.Memory") -> dict[str, Any]:
    """Reconstruct the text -> rid map of durable facts from the store."""
    fact_map: dict[str, Any] = {}
    try:
        for m in mem.list_semantic(limit=MAX_KNOWN_FACTS):
            text = (m or {}).get("text")
            rid = (m or {}).get("rid") or (m or {}).get("id")
            if text and rid is not None:
                fact_map[text] = rid
    except Exception:
        pass
    return fact_map


def _norm_fact(text: str) -> str:
    """Normalize a fact for tolerant matching: lowercased, punctuation-stripped."""
    cleaned = "".join(c if (c.isalnum() or c.isspace()) else " " for c in text.lower())
    return " ".join(cleaned.split())


def _match_known(upd: str, fact_map: dict[str, Any]) -> str | None:
    """Resolve the distiller's ``updates`` text to a known-fact key.

    The local distiller often echoes the prior fact with slight drift (a missing
    trailing period, different casing). An exact dict lookup is too brittle, so
    we fall back to a normalized match, then to bidirectional substring overlap.
    Returns the matching key in ``fact_map`` or ``None``.
    """
    if not upd:
        return None
    if upd in fact_map:
        return upd
    upd_n = _norm_fact(upd)
    for key in fact_map:
        if _norm_fact(key) == upd_n:
            return key
    # Substring fallback: the longest known fact contained in / containing upd.
    cand = None
    for key in fact_map:
        kn = _norm_fact(key)
        if kn and (kn in upd_n or upd_n in kn):
            if cand is None or len(key) > len(cand):
                cand = key
    return cand


def _ingest(mem: "substrate.Memory", fact_map: dict[str, Any], message: str) -> int:
    """Distill ``message`` -> learn new facts / correct() superseded ones.

    Returns the number of durable facts written or updated.
    """
    changed = 0
    for f in extract(message, list(fact_map.keys())):
        match = _match_known(f.get("updates"), fact_map)
        if match:  # update -> supersede the prior fact
            try:
                mem.correct(fact_map[match], f["fact"], importance=f["importance"])
                fact_map[f["fact"]] = fact_map.pop(match)
                changed += 1
            except Exception:
                rid = _rid_of(
                    mem.remember(
                        f["fact"], kind="semantic", importance=f["importance"]
                    )
                )
                if rid is not None:
                    fact_map[f["fact"]] = rid
                changed += 1
        else:  # new durable fact
            rid = _rid_of(
                mem.remember(f["fact"], kind="semantic", importance=f["importance"])
            )
            if rid is not None:
                fact_map[f["fact"]] = rid
            changed += 1
    return changed


def distill_user_message(prompt: str | None, session_id: str | None = None) -> None:
    """Log the user turn (episodic) + distill durable facts (semantic).

    Fires on ``user_prompt_submit``. Fail-soft, skips when disabled.
    """
    if not prompt or not prompt.strip():
        return
    if not is_enabled():
        return

    mem = _open_memory()
    if mem is None:
        return
    try:
        mem.remember(
            prompt,
            kind="episodic",
            importance=0.5,
            metadata={"role": "user", "session_id": session_id},
        )
        fact_map = _known_facts(mem)
        n = _ingest(mem, fact_map, prompt)
        # Reopen so the freshly-written semantic facts are queryable this turn.
        mem.flush()
        if n:
            emit_debug(f"[yantrik_memory] distilled {n} durable fact(s)")
    except Exception as exc:  # noqa: BLE001 — best-effort memory.
        emit_debug(f"[yantrik_memory] distill skipped: {exc!r}")
    finally:
        mem.close()


def record_response(
    agent_name: str,
    model_name: str,
    session_id: str | None = None,
    success: bool = True,
    error: Exception | None = None,
    response_text: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Log the agent's final response as an episodic memory.

    Fires on ``agent_run_end``. Fail-soft, skips when disabled or on failure.
    """
    if not response_text or not response_text.strip():
        return
    if not success:
        return
    if not is_enabled():
        return

    mem = _open_memory()
    if mem is None:
        return
    try:
        drawer_meta: dict[str, Any] = {
            "role": "assistant",
            "agent": agent_name,
            "model": model_name,
            "session_id": session_id,
        }
        if metadata:
            drawer_meta["run_metadata"] = metadata
        mem.remember(
            response_text, kind="episodic", importance=0.4, metadata=drawer_meta
        )
    except Exception as exc:  # noqa: BLE001
        emit_debug(f"[yantrik_memory] record_response skipped: {exc!r}")
    finally:
        mem.close()
