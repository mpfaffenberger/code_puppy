"""Persistent append-only conversation graph for the session tree plugin."""

from __future__ import annotations

import hashlib
import pickle
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def _message_fingerprint(message: Any) -> str:
    """Return a stable-enough identity for matching a message on one path."""
    try:
        payload = pickle.dumps(message)
    except Exception:  # pragma: no cover - exotic third-party messages
        payload = repr(message).encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


@dataclass(slots=True)
class StoredNode:
    node_id: str
    parent_id: str | None
    message: Any
    fingerprint: str
    sequence: int
    label: str = ""
    label_timestamp: str | None = None


@dataclass(slots=True)
class SessionTree:
    """All known messages and branches for one Code Puppy autosave session."""

    nodes: dict[str, StoredNode] = field(default_factory=dict)
    active_leaf_id: str | None = None
    next_sequence: int = 0

    def sync_history(self, history: Sequence[Any]) -> str | None:
        """Merge a live linear history into the graph and mark its final node active."""
        parent_id: str | None = None
        for message in history:
            fingerprint = _message_fingerprint(message)
            matching = next(
                (
                    node
                    for node in self.nodes.values()
                    if node.parent_id == parent_id and node.fingerprint == fingerprint
                ),
                None,
            )
            if matching is None:
                matching = StoredNode(
                    node_id=uuid.uuid4().hex[:12],
                    parent_id=parent_id,
                    message=message,
                    fingerprint=fingerprint,
                    sequence=self.next_sequence,
                )
                self.nodes[matching.node_id] = matching
                self.next_sequence += 1
            else:
                # Keep the newest object shape after dependency upgrades/deserialization.
                matching.message = message
            parent_id = matching.node_id
        self.active_leaf_id = parent_id
        return parent_id

    def children(self, parent_id: str | None) -> list[StoredNode]:
        return sorted(
            (node for node in self.nodes.values() if node.parent_id == parent_id),
            key=lambda node: node.sequence,
        )

    def path_ids(self, node_id: str | None) -> list[str]:
        path: list[str] = []
        seen: set[str] = set()
        while node_id is not None and node_id not in seen:
            seen.add(node_id)
            node = self.nodes.get(node_id)
            if node is None:
                break
            path.append(node_id)
            node_id = node.parent_id
        path.reverse()
        return path

    def history_through(self, node_id: str | None) -> list[Any]:
        return [self.nodes[item].message for item in self.path_ids(node_id)]

    def common_ancestor(self, left_id: str | None, right_id: str | None) -> str | None:
        common: str | None = None
        for left, right in zip(self.path_ids(left_id), self.path_ids(right_id)):
            if left != right:
                break
            common = left
        return common

    def abandoned_history(self, target_id: str) -> list[Any]:
        ancestor = self.common_ancestor(self.active_leaf_id, target_id)
        active_path = self.path_ids(self.active_leaf_id)
        start = active_path.index(ancestor) + 1 if ancestor in active_path else 0
        return [self.nodes[item].message for item in active_path[start:]]

    def set_label(self, node_id: str, label: str | None) -> None:
        node = self.nodes[node_id]
        node.label = (label or "").strip()
        node.label_timestamp = (
            datetime.now(timezone.utc).isoformat() if node.label else None
        )


class TreeStore:
    """Atomic pickle persistence for a session graph."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> SessionTree:
        if not self.path.exists():
            return SessionTree()
        try:
            value = pickle.loads(self.path.read_bytes())  # noqa: S301
        except Exception:
            return SessionTree()
        return value if isinstance(value, SessionTree) else SessionTree()

    def save(self, tree: SessionTree) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(pickle.dumps(tree))
        temporary.replace(self.path)
