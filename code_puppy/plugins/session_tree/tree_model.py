"""View-model helpers for a persistent conversation tree."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Sequence

from .tree_store import SessionTree, StoredNode


class FilterMode(StrEnum):
    DEFAULT = "default"
    NO_TOOLS = "no-tools"
    USER_ONLY = "user-only"
    LABELED_ONLY = "labeled-only"
    ALL = "all"


FILTER_MODES = tuple(FilterMode)
TOOL_ROLES = {"tool", "toolresult", "tool_result", "bashexecution"}
USERISH_ROLES = {"user", "custom"}


@dataclass(frozen=True, slots=True)
class HistoryNode:
    node_id: str
    parent_id: str | None
    role: str
    preview: str
    depth: int
    is_last: bool
    ancestor_has_next: tuple[bool, ...]
    is_system: bool = False
    label: str = ""
    label_timestamp: str | None = None
    is_active: bool = False
    is_on_active_path: bool = False

    @property
    def is_userish(self) -> bool:
        return self.role.lower() in USERISH_ROLES

    @property
    def is_toolish(self) -> bool:
        return self.role.lower() in TOOL_ROLES


@dataclass(frozen=True, slots=True)
class _FlatNode:
    stored: StoredNode
    depth: int
    is_last: bool
    ancestor_has_next: tuple[bool, ...]


def message_role(message: Any) -> str:
    role = getattr(message, "role", None)
    if isinstance(role, str):
        return role
    name = type(message).__name__.lower()
    if "response" in name:
        return "assistant"
    if "request" in name:
        return "user"
    return name or "message"


def message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    parts = getattr(message, "parts", None)
    if parts is None:
        parts = content if isinstance(content, list) else []
    chunks: list[str] = []
    for part in parts or []:
        text = getattr(part, "content", None)
        if text is None:
            text = getattr(part, "text", None)
        if isinstance(part, dict):
            text = part.get("content") or part.get("text")
        if isinstance(text, str):
            chunks.append(text)
    return " ".join(chunks) if chunks else str(message)


def _preview(text: str, max_len: int = 96) -> str:
    clean = " ".join(text.split()) or "(no text)"
    return clean if len(clean) <= max_len else f"{clean[: max_len - 1]}…"


def _flatten(tree: SessionTree) -> list[_FlatNode]:
    result: list[_FlatNode] = []
    roots = tree.children(None)
    stack: list[tuple[StoredNode, int, bool, tuple[bool, ...]]] = []
    for index in range(len(roots) - 1, -1, -1):
        stack.append((roots[index], 0, index == len(roots) - 1, ()))
    while stack:
        node, depth, is_last, ancestors = stack.pop()
        result.append(_FlatNode(node, depth, is_last, ancestors))
        children = tree.children(node.node_id)
        for index in range(len(children) - 1, -1, -1):
            child_is_last = index == len(children) - 1
            stack.append(
                (children[index], depth + 1, child_is_last, (*ancestors, not is_last))
            )
    return result


def build_nodes(tree: SessionTree) -> list[HistoryNode]:
    active_path = set(tree.path_ids(tree.active_leaf_id))
    nodes: list[HistoryNode] = []
    for item in _flatten(tree):
        role = message_role(item.stored.message)
        nodes.append(
            HistoryNode(
                node_id=item.stored.node_id,
                parent_id=item.stored.parent_id,
                role=role,
                preview=_preview(message_text(item.stored.message)),
                depth=item.depth,
                is_last=item.is_last,
                ancestor_has_next=item.ancestor_has_next,
                is_system=item.stored.parent_id is None and role == "system",
                label=item.stored.label,
                label_timestamp=item.stored.label_timestamp,
                is_active=item.stored.node_id == tree.active_leaf_id,
                is_on_active_path=item.stored.node_id in active_path,
            )
        )
    return nodes


def selectable_nodes(tree: SessionTree) -> list[HistoryNode]:
    return [node for node in build_nodes(tree) if not node.is_system]


def user_nodes(tree: SessionTree) -> list[HistoryNode]:
    return [node for node in selectable_nodes(tree) if node.is_userish]


def visible_nodes(
    nodes: Sequence[HistoryNode], mode: FilterMode, query: str = ""
) -> list[HistoryNode]:
    if mode == FilterMode.ALL:
        visible = list(nodes)
    elif mode == FilterMode.NO_TOOLS:
        visible = [node for node in nodes if not node.is_toolish]
    elif mode == FilterMode.USER_ONLY:
        visible = [node for node in nodes if node.is_userish]
    elif mode == FilterMode.LABELED_ONLY:
        visible = [node for node in nodes if node.label]
    else:
        visible = [node for node in nodes if not node.is_system and not node.is_toolish]
    tokens = query.lower().split()
    if not tokens:
        return visible
    return [
        node
        for node in visible
        if all(
            token in f"{node.role} {node.preview} {node.label}".lower()
            for token in tokens
        )
    ]


def resolve_node(selection: str, nodes: Iterable[HistoryNode]) -> HistoryNode | None:
    value = selection.strip()
    if not value:
        return None
    node_list = list(nodes)
    if value.isdigit() and 1 <= int(value) <= len(node_list):
        return node_list[int(value) - 1]
    lowered = value.lower()
    matches = [node for node in node_list if node.node_id.startswith(lowered)]
    return matches[0] if len(matches) == 1 else None
