"""Append-only JSONL session tree compatible with arbitrary model messages."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pickle
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_FORMAT = "mist-session-tree-v1"


@dataclass(frozen=True, slots=True)
class TreeEntry:
    id: str
    parent_id: str | None
    payload: str
    fingerprint: str
    created_at: str

    def message(self) -> Any:
        return pickle.loads(base64.b64decode(self.payload))  # noqa: S301


class SessionTree:
    """A durable tree whose mutation log is never rewritten."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.entries: dict[str, TreeEntry] = {}
        self.children: dict[str | None, list[str]] = {}
        self.labels: dict[str, str] = {}
        self.active_leaf: str | None = None
        self._load()

    @staticmethod
    def _encode(message: Any) -> tuple[str, str]:
        raw = pickle.dumps(message)
        return base64.b64encode(raw).decode("ascii"), hashlib.sha256(raw).hexdigest()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = record.get("type")
            if kind == "entry":
                entry = TreeEntry(
                    id=record["id"],
                    parent_id=record.get("parent_id"),
                    payload=record["payload"],
                    fingerprint=record["fingerprint"],
                    created_at=record["created_at"],
                )
                self.entries[entry.id] = entry
                self.children.setdefault(entry.parent_id, []).append(entry.id)
                self.active_leaf = entry.id
            elif kind == "cursor":
                target = record.get("entry_id")
                if target is None or target in self.entries:
                    self.active_leaf = target
            elif kind == "label" and record.get("entry_id") in self.entries:
                label = record.get("label")
                if label:
                    self.labels[record["entry_id"]] = str(label)
                else:
                    self.labels.pop(record["entry_id"], None)

    def _append_record(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists()
        with self.path.open("a", encoding="utf-8") as stream:
            if new_file:
                stream.write(json.dumps({"type": "header", "format": _FORMAT}) + "\n")
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def append(self, message: Any, *, parent_id: str | None = None) -> TreeEntry:
        with self._lock:
            parent = self.active_leaf if parent_id is None else parent_id
            if parent is not None and parent not in self.entries:
                raise KeyError(f"Unknown parent entry: {parent}")
            payload, fingerprint = self._encode(message)
            entry = TreeEntry(
                id=uuid.uuid4().hex,
                parent_id=parent,
                payload=payload,
                fingerprint=fingerprint,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._append_record(
                {
                    "type": "entry",
                    "id": entry.id,
                    "parent_id": entry.parent_id,
                    "payload": entry.payload,
                    "fingerprint": entry.fingerprint,
                    "created_at": entry.created_at,
                }
            )
            self.entries[entry.id] = entry
            self.children.setdefault(parent, []).append(entry.id)
            self.active_leaf = entry.id
            return entry

    def path_entries(self, leaf_id: str | None = None) -> list[TreeEntry]:
        current = self.active_leaf if leaf_id is None else leaf_id
        result: list[TreeEntry] = []
        seen: set[str] = set()
        while current is not None:
            if current in seen or current not in self.entries:
                raise ValueError("Session tree contains a cycle or dangling parent")
            seen.add(current)
            entry = self.entries[current]
            result.append(entry)
            current = entry.parent_id
        result.reverse()
        return result

    def history(self, leaf_id: str | None = None) -> list[Any]:
        return [entry.message() for entry in self.path_entries(leaf_id)]

    def branch(self, entry_id: str | None) -> None:
        if entry_id is not None and entry_id not in self.entries:
            raise KeyError(f"Unknown tree entry: {entry_id}")
        with self._lock:
            self._append_record({"type": "cursor", "entry_id": entry_id})
            self.active_leaf = entry_id

    def set_label(self, entry_id: str, label: str | None) -> None:
        if entry_id not in self.entries:
            raise KeyError(f"Unknown tree entry: {entry_id}")
        with self._lock:
            self._append_record({"type": "label", "entry_id": entry_id, "label": label})
            if label:
                self.labels[entry_id] = label
            else:
                self.labels.pop(entry_id, None)

    def sync_history(self, history: Iterable[Any]) -> None:
        """Append a linear history, branching at its common path prefix."""
        messages = list(history)
        encoded = [self._encode(message) for message in messages]
        current = self.path_entries()
        common = 0
        while (
            common < len(current)
            and common < len(encoded)
            and current[common].fingerprint == encoded[common][1]
        ):
            common += 1
        branch_point = current[common - 1].id if common else None
        if common != len(current):
            self.branch(branch_point)
        for message in messages[common:]:
            self.append(message)

    def fork_to(self, destination: Path, leaf_id: str | None = None) -> "SessionTree":
        if destination.exists():
            raise FileExistsError(destination)
        forked = SessionTree(destination)
        id_map: dict[str, str] = {}
        for source in self.path_entries(leaf_id):
            parent = id_map.get(source.parent_id) if source.parent_id else None
            created = forked.append(source.message(), parent_id=parent)
            id_map[source.id] = created.id
            if source.id in self.labels:
                forked.set_label(created.id, self.labels[source.id])
        return forked

    def render(self) -> str:
        lines: list[str] = []

        def visit(parent: str | None, prefix: str) -> None:
            child_ids = self.children.get(parent, [])
            for index, child_id in enumerate(child_ids):
                last = index == len(child_ids) - 1
                marker = "*" if child_id == self.active_leaf else " "
                label = f" [{self.labels[child_id]}]" if child_id in self.labels else ""
                lines.append(
                    f"{prefix}{'└─' if last else '├─'}{marker} {child_id[:8]}{label}"
                )
                visit(child_id, prefix + ("  " if last else "│ "))

        visit(None, "")
        return "\n".join(lines) or "(empty session tree)"
