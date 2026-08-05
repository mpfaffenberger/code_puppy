from __future__ import annotations

from code_puppy.plugins.computer_use.accessibility import snapshot_tree


class API:
    kAXErrorSuccess = 0
    kAXFocusedWindowAttribute = "focused_window"
    kAXMainWindowAttribute = "main_window"
    kAXWindowsAttribute = "windows"
    kAXRoleAttribute = "role"
    kAXTitleAttribute = "title"
    kAXDescriptionAttribute = "description"
    kAXValueAttribute = "value"
    kAXEnabledAttribute = "enabled"
    kAXFocusedAttribute = "focused"
    kAXChildrenAttribute = "children"

    @staticmethod
    def AXUIElementCopyActionNames(element, _):
        return 0, element.get("actions", [])


def copy_attribute(api, element, attribute):
    del api
    return element.get(attribute)


def test_actionable_controls_rank_ahead_of_large_file_list():
    rows = [
        {
            "role": "AXRow",
            "title": f"File {index}",
            "enabled": True,
            "children": [],
        }
        for index in range(300)
    ]
    button = {
        "role": "AXButton",
        "title": "New Document",
        "enabled": True,
        "actions": ["AXPress"],
        "children": [],
    }
    window = {
        "role": "AXWindow",
        "title": "Open",
        "children": [*rows, button],
    }
    application = {"focused_window": window}

    nodes, elements, metadata = snapshot_tree(
        API, application, copy_attribute, max_nodes=20
    )

    assert nodes[0]["title"] == "New Document"
    assert nodes[0]["actions"] == ["AXPress"]
    assert elements[nodes[0]["id"]] is button
    assert metadata["scanned_node_count"] == 302
    assert metadata["truncated"] is True
    assert metadata["overflow_summary"]["roles"]["AXRow"] > 250


def test_preferred_capture_window_keeps_tree_and_screenshot_aligned():
    other = {
        "AXWindowNumber": 10,
        "role": "AXWindow",
        "title": "Other",
        "children": [],
    }
    captured = {
        "AXWindowNumber": 20,
        "role": "AXWindow",
        "title": "Captured",
        "children": [],
    }
    application = {
        "focused_window": other,
        "windows": [other, captured],
    }

    nodes, _, _ = snapshot_tree(
        API,
        application,
        copy_attribute,
        max_nodes=20,
        preferred_window_id=20,
    )

    assert nodes[0]["title"] == "Captured"
