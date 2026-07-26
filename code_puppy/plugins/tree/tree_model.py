"""Append-only conversation graph used by the ``/tree`` plugin.

Code Puppy's provider history is linear.  This model keeps old linear paths as
branches whenever the user rewinds and submits a replacement prompt.  Provider
message objects remain untouched, so selecting a node can restore the exact
root-to-node history expected by pydantic-ai.
"""

from __future__ import annotations

import hashlib
import pickle
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


@dataclass(slots=True)
class TreeNode:
    id: str
    parent_id: Optional[str]
    message: Any
    role: str
    text: str
    fingerprint: str
    children: list[str] = field(default_factory=list)
    label: Optional[str] = None


@dataclass(slots=True)
class Navigation:
    history: list[Any]
    editor_text: Optional[str]
    leaf_id: Optional[str]
    changed: bool


def message_fingerprint(message: Any) -> str:
    """Return a stable-enough identity for prefix comparison.

    Pickle is already Code Puppy's session format and preserves all provider
    fields.  The repr fallback keeps third-party/custom message types usable.
    """
    try:
        payload = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        payload = repr(message).encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


def describe_message(message: Any) -> tuple[str, str]:
    """Extract a Pi-like role and searchable/copyable text."""
    role = "unknown"
    text: list[str] = []
    try:
        from pydantic_ai.messages import (
            ModelRequest,
            ModelResponse,
            SystemPromptPart,
            TextPart,
            ToolCallPart,
            ToolReturnPart,
            UserPromptPart,
        )

        if isinstance(message, ModelRequest):
            role = "request"
            for part in getattr(message, "parts", ()) or ():
                if isinstance(part, UserPromptPart):
                    role = "user"
                    content = getattr(part, "content", "")
                    text.append(_content_text(content))
                elif isinstance(part, ToolReturnPart):
                    if role != "user":
                        role = "tool"
                    tool_name = getattr(part, "tool_name", "tool")
                    content = getattr(part, "content", "")
                    text.append(f"[{tool_name} result: {_content_text(content)}]")
                elif isinstance(part, SystemPromptPart) and role == "request":
                    role = "system"
        elif isinstance(message, ModelResponse):
            role = "assistant"
            saw_text = False
            saw_tool = False
            for part in getattr(message, "parts", ()) or ():
                if isinstance(part, TextPart):
                    content = str(getattr(part, "content", ""))
                    if content:
                        saw_text = True
                        text.append(content)
                elif isinstance(part, ToolCallPart):
                    saw_tool = True
                    tool_name = getattr(part, "tool_name", "tool")
                    args = getattr(part, "args", "")
                    text.append(f"[{tool_name}: {args}]")
            if saw_tool and not saw_text:
                role = "tool-call"
    except Exception:
        pass

    clean = " ".join(fragment for fragment in text if fragment).strip()
    return role, clean or str(message)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, Iterable) and not isinstance(content, (bytes, dict)):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, str):
                fragments.append(item)
            else:
                value = getattr(item, "content", None)
                if isinstance(value, str):
                    fragments.append(value)
        return " ".join(fragments)
    return str(content)


class ConversationTree:
    """A graph projection of one agent's current conversation session."""

    def __init__(self) -> None:
        self.nodes: dict[str, TreeNode] = {}
        self.roots: list[str] = []
        self.active_path: list[str] = []
        self.branching_armed = False

    @property
    def leaf_id(self) -> Optional[str]:
        return self.active_path[-1] if self.active_path else None

    def sync(self, history: list[Any]) -> None:
        """Merge a provider's current linear history into the graph."""
        if not history:
            # Session identity is owned by the plugin's session-keyed store.
            # Empty history can legitimately mean /tree rewound before the
            # first prompt, so it must not erase inactive branches.
            self.active_path = []
            return

        fingerprints = [message_fingerprint(message) for message in history]
        active_fingerprints = [
            self.nodes[node_id].fingerprint for node_id in self.active_path
        ]
        common = 0
        while (
            common < len(fingerprints)
            and common < len(active_fingerprints)
            and fingerprints[common] == active_fingerprints[common]
        ):
            common += 1

        # A replaced prefix can be provider compaction. Session identity is
        # handled outside this model, so retain old roots and append the new
        # compacted path instead of destroying inactive branches.
        path = self.active_path[:common]
        parent_id = path[-1] if path else None
        for message, fingerprint in zip(history[common:], fingerprints[common:]):
            node_id = uuid.uuid4().hex[:12]
            role, text = describe_message(message)
            node = TreeNode(
                id=node_id,
                parent_id=parent_id,
                message=message,
                role=role,
                text=text,
                fingerprint=fingerprint,
            )
            self.nodes[node_id] = node
            if parent_id is None:
                self.roots.append(node_id)
            else:
                self.nodes[parent_id].children.append(node_id)
            path.append(node_id)
            parent_id = node_id
        self.active_path = path
        self.branching_armed = False

    def clear(self) -> None:
        self.nodes.clear()
        self.roots.clear()
        self.active_path.clear()
        self.branching_armed = False

    def path_to(self, node_id: str) -> list[str]:
        if node_id not in self.nodes:
            raise KeyError(node_id)
        path: list[str] = []
        seen: set[str] = set()
        current: Optional[str] = node_id
        while current is not None and current not in seen:
            seen.add(current)
            path.append(current)
            current = self.nodes[current].parent_id
        path.reverse()
        return path

    def navigate(self, node_id: str) -> Navigation:
        """Apply Pi semantics: user nodes rewind before the prompt."""
        if node_id == self.leaf_id:
            return Navigation(self.current_history(), None, self.leaf_id, False)

        selected = self.nodes[node_id]
        selected_path = self.path_to(node_id)
        editor_text: Optional[str] = None
        if selected.role == "user":
            destination = selected_path[:-1]
            editor_text = selected.text
        else:
            destination = selected_path

        self.active_path = destination
        self.branching_armed = True
        return Navigation(
            history=[self.nodes[item].message for item in destination],
            editor_text=editor_text,
            leaf_id=self.leaf_id,
            changed=True,
        )

    def current_history(self) -> list[Any]:
        return [self.nodes[node_id].message for node_id in self.active_path]

    def ordered_children(self, node_id: Optional[str]) -> list[str]:
        children = self.roots if node_id is None else self.nodes[node_id].children
        active = set(self.active_path)
        active_children = [item for item in children if item in active]
        inactive_children = [item for item in children if item not in active]
        return active_children + inactive_children

    def visible_nodes(self, mode: str = "default", query: str = "") -> list[str]:
        """Flatten active branches first, then apply Pi's useful filters."""
        ordered: list[str] = []
        stack = list(reversed(self.ordered_children(None)))
        while stack:
            node_id = stack.pop()
            ordered.append(node_id)
            stack.extend(reversed(self.ordered_children(node_id)))

        tokens = query.casefold().split()

        def keep(node: TreeNode) -> bool:
            if mode == "user" and node.role != "user":
                return False
            if mode == "no-tools" and node.role in {"tool", "tool-call"}:
                return False
            if (
                mode == "default"
                and node.role == "tool-call"
                and node.id != self.leaf_id
            ):
                return False
            haystack = f"{node.role} {node.label or ''} {node.text}".casefold()
            return all(token in haystack for token in tokens)

        return [node_id for node_id in ordered if keep(self.nodes[node_id])]
