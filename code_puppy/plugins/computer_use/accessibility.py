"""Focused-window accessibility extraction with relevance pruning."""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

MAX_SCAN_NODES = 4_000
# Electron embeds its web accessibility tree beneath a deep stack of generic
# groups; Spotify's search field, for example, sits beyond depth 16.
MAX_DEPTH = 32

_ROLE_SCORE = {
    "AXButton": 80,
    "AXCheckBox": 75,
    "AXComboBox": 75,
    "AXMenuItem": 75,
    "AXPopUpButton": 75,
    "AXRadioButton": 75,
    "AXSearchField": 75,
    "AXSlider": 70,
    "AXTextArea": 70,
    "AXTextField": 70,
    "AXLink": 65,
    "AXRow": 25,
    "AXCell": 20,
    "AXStaticText": 15,
    "AXWindow": 10,
}


def _copy_actions(api: Any, element: Any) -> list[str]:
    result = api.AXUIElementCopyActionNames(element, None)
    if isinstance(result, tuple):
        error, value = result
        if error != api.kAXErrorSuccess or not value:
            return []
        return [str(item) for item in value]
    return [str(item) for item in (result or [])]


def _focused_root(
    api: Any,
    application: Any,
    copy_attribute: Callable,
    preferred_window_id: int | None = None,
):
    if preferred_window_id is not None:
        windows = copy_attribute(api, application, api.kAXWindowsAttribute)
        for window in windows or []:
            number = copy_attribute(api, window, "AXWindowNumber")
            if number is not None and int(number) == preferred_window_id:
                return window
    for attribute in (
        api.kAXFocusedWindowAttribute,
        api.kAXMainWindowAttribute,
    ):
        window = copy_attribute(api, application, attribute)
        if window is not None:
            return window
    windows = copy_attribute(api, application, api.kAXWindowsAttribute)
    if windows:
        return windows[0]
    return application


def snapshot_tree(
    api: Any,
    application: Any,
    copy_attribute: Callable,
    max_nodes: int,
    preferred_window_id: int | None = None,
) -> tuple[list[dict[str, Any]], dict[int, Any], dict[str, Any]]:
    """Scan broadly, then retain controls most useful for agent interaction."""
    root = _focused_root(
        api,
        application,
        copy_attribute,
        preferred_window_id,
    )
    limit = max(1, min(int(max_nodes), 500))
    scan_limit = min(MAX_SCAN_NODES, max(1_000, limit * 8))
    candidates: list[tuple[int, int, Any, dict[str, Any]]] = []
    seen: set[int] = set()
    scan_stopped = False

    def visit(element: Any, depth: int) -> None:
        nonlocal scan_stopped
        if depth > MAX_DEPTH or scan_stopped:
            return
        identity = id(element)
        if identity in seen:
            return
        seen.add(identity)
        if len(candidates) >= scan_limit:
            scan_stopped = True
            return

        role = str(copy_attribute(api, element, api.kAXRoleAttribute) or "AXUnknown")
        title = str(copy_attribute(api, element, api.kAXTitleAttribute) or "")
        description = str(
            copy_attribute(api, element, api.kAXDescriptionAttribute) or ""
        )
        value = copy_attribute(api, element, api.kAXValueAttribute)
        enabled = copy_attribute(api, element, api.kAXEnabledAttribute)
        focused = copy_attribute(api, element, api.kAXFocusedAttribute)
        actions = _copy_actions(api, element)
        order = len(candidates)
        node = {
            "depth": depth,
            "source_order": order,
            "role": role,
            "title": title,
            "description": description,
            "enabled": bool(enabled) if enabled is not None else None,
            "focused": bool(focused) if focused is not None else None,
            "actions": actions,
        }
        if value is not None and "secure" not in role.casefold():
            node["value"] = str(value)[:500]

        score = _ROLE_SCORE.get(role, 0)
        score += 60 if actions else 0
        score += 100 if focused else 0
        score += 12 if title or description else 0
        semantic_text = " ".join((title, description, str(value or ""))).casefold()
        if (
            "now playing:" in semantic_text
            or "what do you want to play?" in semantic_text
            or description.casefold() in {"play", "pause"}
        ):
            score += 120
        score -= 50 if enabled is False else 0
        score -= min(depth, 10)
        candidates.append((score, order, element, node))

        children = copy_attribute(api, element, api.kAXChildrenAttribute)
        for child in children or []:
            visit(child, depth + 1)

    visit(root, 0)
    ranked = sorted(candidates, key=lambda item: (-item[0], item[1]))
    selected = ranked[:limit]
    nodes = []
    elements = {}
    for element_id, (_, _, element, node) in enumerate(selected, start=1):
        node["id"] = element_id
        nodes.append(node)
        elements[element_id] = element

    excluded = ranked[limit:]
    overflow_roles = Counter(item[3]["role"] for item in excluded)
    metadata = {
        "scanned_node_count": len(candidates),
        "returned_node_count": len(nodes),
        "truncated": bool(excluded or scan_stopped),
        "scan_limit_reached": scan_stopped,
        "overflow_summary": {
            "excluded_node_count": len(excluded),
            "roles": dict(overflow_roles.most_common(12)),
        },
    }
    return nodes, elements, metadata
