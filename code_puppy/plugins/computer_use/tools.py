"""Pydantic-AI registrations for the macOS computer-use backend."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from pydantic_ai import BinaryContent, RunContext, ToolReturn

from .backend import ComputerUseError, backend
from .inline_image import emit_inline_image
from .settle import wait_for_ui_settle

MAX_BATCH_STEPS = 20


async def _call(func: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any):
    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except ComputerUseError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"Computer Use failed: {exc}"}


def register_get_app_state(agent):
    @agent.tool
    async def computer_get_app_state(
        context: RunContext,
        app_name: str,
        max_nodes: int = 100,
        show_screenshot: bool = True,
    ) -> Any:
        """Get one revisioned screenshot and accessibility tree for an app.

        Call this once per turn and after every standalone mutation. All action
        tools require the returned state_revision and reject stale state.
        """
        del context
        result = await _call(backend.get_app_state, app_name, max_nodes)
        if not result.get("success") or not show_screenshot:
            return result
        return _state_tool_return(result, "macOS app state")

    return computer_get_app_state


def register_snapshot(agent):
    @agent.tool
    async def computer_snapshot(
        context: RunContext,
        app_name: str | None = None,
        max_nodes: int = 100,
        show_screenshot: bool = True,
    ) -> Any:
        """Inspect a macOS application's accessibility tree.

        Call this before acting and again after navigation. Returned element IDs
        are invalidated by the next snapshot. By default, also capture and show
        a compact inline screenshot in Ghostty, Kitty, WezTerm, or iTerm2.
        """
        del context
        if app_name:
            result = await _call(backend.get_app_state, app_name, max_nodes)
            if not result.get("success") or not show_screenshot:
                return result
            return _state_tool_return(result, "macOS accessibility snapshot")
        return await _call(backend.snapshot, None, max_nodes)

    return computer_snapshot


def register_click(agent):
    @agent.tool
    async def computer_click(
        context: RunContext,
        state_revision: str,
        element_id: int | None = None,
        x: float | None = None,
        y: float | None = None,
        button: str = "left",
        click_count: int = 1,
    ) -> dict[str, Any]:
        """Click by element ID or screenshot-pixel coordinates.

        Exactly one target form is required: element_id, or both x and y from
        the screenshot associated with state_revision.
        """
        del context
        if element_id is not None and x is None and y is None:
            return await _call(backend.click, state_revision, element_id)
        if element_id is None and x is not None and y is not None:
            return await _call(
                backend.click_pixel,
                state_revision,
                x,
                y,
                button,
                click_count,
            )
        return {
            "success": False,
            "error": "Provide element_id or both x and y, but not both target forms.",
        }

    return computer_click


def register_set_value(agent):
    @agent.tool
    async def computer_set_value(
        context: RunContext,
        state_revision: str,
        element_id: int,
        value: str,
    ) -> dict[str, Any]:
        """Set the value of an accessible text field or control."""
        del context
        return await _call(backend.set_value, state_revision, element_id, value)

    return computer_set_value


def register_perform_action(agent):
    @agent.tool
    async def computer_perform_action(
        context: RunContext,
        state_revision: str,
        element_id: int,
        action: str,
    ) -> dict[str, Any]:
        """Perform an action listed in an element's `actions` array."""
        del context
        return await _call(
            backend.perform_action,
            state_revision,
            element_id,
            action,
        )

    return computer_perform_action


def register_select_text(agent):
    @agent.tool
    async def computer_select_text(
        context: RunContext,
        state_revision: str,
        element_id: int,
        text: str,
        mode: str = "text",
        prefix: str | None = None,
        suffix: str | None = None,
    ) -> dict[str, Any]:
        """Select exact text or place the cursor before/after it.

        Use prefix or suffix when the target text occurs more than once.
        """
        del context
        return await _call(
            backend.select_text,
            state_revision,
            element_id,
            text,
            mode,
            prefix,
            suffix,
        )

    return computer_select_text


def register_press_key(agent):
    @agent.tool
    async def computer_press_key(
        context: RunContext,
        state_revision: str,
        key: str,
        modifiers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Press a supported key, optionally with command/shift/option/control."""
        del context
        return await _call(backend.press_key, state_revision, key, modifiers)

    return computer_press_key


def register_type_text(agent):
    @agent.tool
    async def computer_type_text(
        context: RunContext, state_revision: str, text: str
    ) -> dict[str, Any]:
        """Type Unicode text into the currently focused macOS control."""
        del context
        return await _call(backend.type_text, state_revision, text)

    return computer_type_text


def register_scroll(agent):
    @agent.tool
    async def computer_scroll(
        context: RunContext,
        state_revision: str,
        direction: str,
        pages: float = 1.0,
    ) -> dict[str, Any]:
        """Scroll up, down, left, or right by fractional pages."""
        del context
        return await _call(backend.scroll_pages, state_revision, direction, pages)

    return computer_scroll


def register_drag(agent):
    @agent.tool
    async def computer_drag(
        context: RunContext,
        state_revision: str,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        duration: float = 0.5,
    ) -> dict[str, Any]:
        """Drag between two screenshot-pixel coordinates."""
        del context
        return await _call(
            backend.drag_pixel,
            state_revision,
            start_x,
            start_y,
            end_x,
            end_y,
            duration,
        )

    return computer_drag


def register_screenshot(agent):
    @agent.tool
    async def computer_screenshot(
        context: RunContext,
        path: str | None = None,
        app_name: str | None = None,
    ) -> Any:
        """Capture and display a macOS application window."""
        del context
        result = await _call(backend.screenshot, path, app_name)
        if not result.get("success"):
            return result
        return _image_tool_return(result, "macOS screenshot")

    return computer_screenshot


def register_batch(agent):
    @agent.tool
    async def computer_use_batch(
        context: RunContext,
        state_revision: str,
        steps: list[dict[str, Any]],
    ) -> Any:
        """Run up to 20 computer-use actions sequentially.

        Supported action values are click, set_value, perform_action,
        select_text, press_key, type_text, scroll, drag, and wait. Stop
        immediately when an action fails, then return updated state after
        deterministic UI settling.
        """
        del context
        if len(steps) > MAX_BATCH_STEPS:
            return {
                "success": False,
                "error": f"A batch may contain at most {MAX_BATCH_STEPS} steps.",
            }
        completed = []
        try:
            initial_state = backend.require_state(state_revision)
        except ComputerUseError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            return {
                "success": False,
                "error": f"Computer Use activation failed: {exc}",
            }

        def invoke(action_name: str, kwargs: dict[str, Any]):
            if action_name == "click":
                if "element_id" in kwargs:
                    return backend.click(state_revision, consume=False, **kwargs)
                return backend.click_pixel(state_revision, consume=False, **kwargs)
            actions: dict[str, Callable[..., Any]] = {
                "set_value": backend.set_value,
                "perform_action": backend.perform_action,
                "select_text": backend.select_text,
                "press_key": backend.press_key,
                "type_text": backend.type_text,
                "scroll": backend.scroll_pages,
                "drag": backend.drag_pixel,
            }
            return actions[action_name](state_revision, consume=False, **kwargs)

        supported = {
            "click",
            "set_value",
            "perform_action",
            "select_text",
            "press_key",
            "type_text",
            "scroll",
            "drag",
        }
        for index, step in enumerate(steps):
            action = str(step.get("action", ""))
            if action == "wait":
                seconds = max(0.0, min(float(step.get("seconds", 1)), 10.0))
                await asyncio.sleep(seconds)
                result = {"success": True, "seconds": seconds}
            elif action in supported:
                kwargs = {key: value for key, value in step.items() if key != "action"}
                result = await _call(invoke, action, kwargs)
            else:
                result = {"success": False, "error": f"Unknown action: {action}"}
            completed.append({"index": index, "action": action, "result": result})
            if not result.get("success"):
                return {"success": False, "completed_steps": completed}
        try:
            backend.require_state(state_revision, consume=True)
        except ComputerUseError as exc:
            return {
                "success": False,
                "error": str(exc),
                "completed_steps": completed,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": f"Computer Use finalization failed: {exc}",
                "completed_steps": completed,
            }
        settle = await asyncio.to_thread(
            wait_for_ui_settle,
            backend.snapshot,
            initial_state.application,
        )
        updated = await _call(backend.get_app_state, initial_state.application, 100)
        if not updated.get("success"):
            return {
                "success": True,
                "completed_steps": completed,
                "updated_state_error": updated.get("error"),
            }
        updated["completed_steps"] = completed
        updated["ui_settle"] = settle
        return _state_tool_return(updated, "macOS state after computer-use batch")

    return computer_use_batch


REGISTRARS = {
    "computer_get_app_state": register_get_app_state,
    "computer_snapshot": register_snapshot,
    "computer_click": register_click,
    "computer_set_value": register_set_value,
    "computer_perform_action": register_perform_action,
    "computer_select_text": register_select_text,
    "computer_press_key": register_press_key,
    "computer_type_text": register_type_text,
    "computer_scroll": register_scroll,
    "computer_drag": register_drag,
    "computer_screenshot": register_screenshot,
    "computer_use_batch": register_batch,
}


def _image_tool_return(result: dict[str, Any], label: str) -> ToolReturn:
    path = str(result["path"])
    image_bytes = Path(path).read_bytes()
    displayed = emit_inline_image(path)
    metadata = dict(result)
    metadata["displayed_inline"] = displayed
    return ToolReturn(
        return_value=metadata,
        content=[
            f"Here is the {label}:",
            BinaryContent(data=image_bytes, media_type="image/png"),
        ],
        metadata=metadata,
    )


def _state_tool_return(result: dict[str, Any], label: str) -> ToolReturn:
    image = _image_tool_return(
        {"success": True, "path": result["screenshot_path"]}, label
    )
    metadata = dict(result)
    metadata["displayed_inline"] = image.metadata["displayed_inline"]
    return ToolReturn(
        return_value=_compact_state_for_model(metadata),
        content=image.content,
        metadata=metadata,
    )


def _compact_state_for_model(state: dict[str, Any]) -> dict[str, Any]:
    """Keep control semantics while removing repetitive AX bookkeeping."""
    keep = (
        "success",
        "state_revision",
        "application",
        "bundle_id",
        "window_title",
        "window_bounds_points",
        "screenshot_size_pixels",
        "screenshot_coordinate_system",
        "action_coordinate_system",
        "node_count",
        "truncated",
        "overflow_summary",
        "warning",
        "completed_steps",
        "ui_settle",
    )
    compact = {key: state[key] for key in keep if key in state}
    compact_nodes = []
    ignored_actions = {"AXShowMenu", "AXScrollToVisible"}
    for node in state.get("nodes", []):
        item = {
            key: node[key]
            for key in ("id", "role", "title", "description", "value")
            if node.get(key) not in (None, "")
        }
        actions = [
            action
            for action in node.get("actions", [])
            if action not in ignored_actions
        ]
        if actions:
            item["actions"] = actions
        if node.get("focused"):
            item["focused"] = True
        if node.get("enabled") is False:
            item["enabled"] = False
        compact_nodes.append(item)
    compact["nodes"] = compact_nodes
    return compact


async def _attach_screenshot(
    result: dict[str, Any],
    label: str,
    app_name: str | None = None,
) -> ToolReturn | dict[str, Any]:
    screenshot = await _call(backend.screenshot, None, app_name)
    if not screenshot.get("success"):
        result["screenshot_error"] = screenshot.get("error")
        return result
    screenshot_return = _image_tool_return(screenshot, label)
    merged = dict(result)
    merged["screenshot_path"] = screenshot["path"]
    merged["displayed_inline"] = screenshot_return.metadata["displayed_inline"]
    return ToolReturn(
        return_value=merged,
        content=screenshot_return.content,
        metadata=merged,
    )
