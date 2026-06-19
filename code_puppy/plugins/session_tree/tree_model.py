"""Small helpers for navigating Code Puppy message history."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Sequence


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
    index: int
    node_id: str
    role: str
    preview: str
    is_system: bool = False
    label: str = ""

    @property
    def is_userish(self) -> bool:
        return self.role.lower() in USERISH_ROLES

    @property
    def is_toolish(self) -> bool:
        return self.role.lower() in TOOL_ROLES


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

    if chunks:
        return " ".join(chunks)
    return str(message)


def node_id_for(index: int, message: Any) -> str:
    raw = f"{index}:{type(message).__name__}:{message_text(message)}".encode()
    return hashlib.sha1(raw).hexdigest()[:8]


def _preview(text: str, max_len: int = 72) -> str:
    clean = " ".join(text.split())
    if not clean:
        clean = "(no text)"
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1] + "…"


def build_nodes(
    history: Sequence[Any], labels: dict[str, str] | None = None
) -> list[HistoryNode]:
    labels = labels or {}
    nodes: list[HistoryNode] = []
    for index, message in enumerate(history):
        role = message_role(message)
        node_id = node_id_for(index, message)
        nodes.append(
            HistoryNode(
                index=index,
                node_id=node_id,
                role=role,
                preview=_preview(message_text(message)),
                is_system=index == 0 and role == "system",
                label=labels.get(node_id, ""),
            )
        )
    return nodes


def selectable_nodes(history: Sequence[Any]) -> list[HistoryNode]:
    return [node for node in build_nodes(history) if not node.is_system]


def user_nodes(history: Sequence[Any]) -> list[HistoryNode]:
    return [node for node in selectable_nodes(history) if node.is_userish]


def visible_nodes(nodes: Sequence[HistoryNode], mode: FilterMode) -> list[HistoryNode]:
    if mode == FilterMode.ALL:
        return list(nodes)
    if mode == FilterMode.NO_TOOLS:
        return [node for node in nodes if not node.is_toolish]
    if mode == FilterMode.USER_ONLY:
        return [node for node in nodes if node.is_userish]
    if mode == FilterMode.LABELED_ONLY:
        return [node for node in nodes if node.label]
    return [node for node in nodes if not node.is_system and not node.is_toolish]


def resolve_node(selection: str, nodes: Iterable[HistoryNode]) -> HistoryNode | None:
    value = selection.strip()
    if not value:
        return None

    node_list = list(nodes)
    if value.isdigit():
        ordinal = int(value)
        if 1 <= ordinal <= len(node_list):
            return node_list[ordinal - 1]
        for node in node_list:
            if node.index == ordinal:
                return node

    value_lower = value.lower()
    for node in node_list:
        if node.node_id.startswith(value_lower):
            return node
    return None


def history_through(history: Sequence[Any], index: int) -> list[Any]:
    if index < 0:
        return []
    return list(history[: index + 1])


def history_before(history: Sequence[Any], index: int) -> list[Any]:
    if index <= 0:
        return list(history[:1]) if history else []
    return list(history[:index])
