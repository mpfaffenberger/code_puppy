"""Shared policy and stale-state enforcement."""

from __future__ import annotations

from .policy import policy_store
from .state import AppState, state_store


def require_safe_state(
    revision: str,
    *,
    consume: bool = False,
) -> AppState:
    state = state_store.require(revision)
    policy_store.require(state.bundle_id)
    if consume:
        return state_store.require(revision, consume=True)
    return state
