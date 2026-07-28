"""macOS Accessibility and Quartz bridge.

PyObjC is imported lazily so Code Puppy remains importable on every platform.
Element IDs are intentionally snapshot-scoped: any new snapshot invalidates the
previous IDs, preventing an agent from acting on a stale accessibility tree.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from .accessibility import snapshot_tree
from .activation import activate_application, activate_state
from .backend_types import ComputerUseError
from .capture import capture_window
from .keycodes import KEY_CODES
from .policy import policy_store
from .safety import require_safe_state
from .state import state_store

MAX_NODES = 500


class MacOSBackend:
    def __init__(self) -> None:
        self._elements: dict[int, Any] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _api():
        try:
            import ApplicationServices
        except ImportError as exc:
            raise ComputerUseError(
                "Computer Use requires the macOS extra. Install it with "
                "`pip install 'code-puppy[computer-use]'`."
            ) from exc
        return ApplicationServices

    def trusted(self, prompt: bool = False) -> bool:
        quartz = self._api()
        options = {quartz.kAXTrustedCheckOptionPrompt: bool(prompt)}
        return bool(quartz.AXIsProcessTrustedWithOptions(options))

    def _require_trusted(self, prompt: bool = True) -> Any:
        quartz = self._api()
        if not self.trusted(prompt=prompt):
            raise ComputerUseError(
                "Accessibility permission is required. Enable Code Puppy (or its "
                "terminal) in System Settings > Privacy & Security > Accessibility."
            )
        return quartz

    @staticmethod
    def _copy_attribute(quartz: Any, element: Any, attribute: str) -> Any:
        result = quartz.AXUIElementCopyAttributeValue(element, attribute, None)
        if isinstance(result, tuple):
            error, value = result
            if error != quartz.kAXErrorSuccess:
                return None
            return value
        return result

    def _application(self, app_name: str | None) -> tuple[Any, str]:
        quartz = self._require_trusted()
        if app_name:
            try:
                from AppKit import NSWorkspace
            except ImportError as exc:
                raise ComputerUseError(
                    "AppKit bindings are unavailable; reinstall the computer-use extra."
                ) from exc
            wanted = app_name.casefold()
            for app in NSWorkspace.sharedWorkspace().runningApplications():
                name = str(app.localizedName() or "")
                bundle = str(app.bundleIdentifier() or "")
                if wanted in {name.casefold(), bundle.casefold()}:
                    return quartz.AXUIElementCreateApplication(
                        app.processIdentifier()
                    ), name
            raise ComputerUseError(f"Running application not found: {app_name}")

        system = quartz.AXUIElementCreateSystemWide()
        app = self._copy_attribute(
            quartz, system, quartz.kAXFocusedApplicationAttribute
        )
        if app is None:
            try:
                from AppKit import NSWorkspace
            except ImportError as exc:
                raise ComputerUseError(
                    "No focused macOS application was found."
                ) from exc
            frontmost = NSWorkspace.sharedWorkspace().frontmostApplication()
            if frontmost is None:
                raise ComputerUseError("No focused macOS application was found.")
            app = quartz.AXUIElementCreateApplication(frontmost.processIdentifier())
            fallback_name = str(frontmost.localizedName() or "Focused application")
        else:
            fallback_name = "Focused application"
        title = self._copy_attribute(quartz, app, quartz.kAXTitleAttribute)
        return app, str(title or fallback_name)

    @staticmethod
    def _bundle_id(app_name: str) -> str:
        try:
            from AppKit import NSWorkspace
        except ImportError as exc:
            raise ComputerUseError("AppKit bindings are unavailable.") from exc
        wanted = app_name.casefold()
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            name = str(app.localizedName() or "")
            bundle = str(app.bundleIdentifier() or "")
            if wanted in {name.casefold(), bundle.casefold()}:
                return bundle
        raise ComputerUseError(f"Running application not found: {app_name}")

    def require_state(
        self,
        revision: str,
        *,
        consume: bool = False,
    ):
        state = require_safe_state(
            revision,
        )
        activate_state(state)
        if consume:
            return require_safe_state(revision, consume=True)
        return state

    def snapshot(
        self,
        app_name: str | None = None,
        max_nodes: int = MAX_NODES,
        preferred_window_id: int | None = None,
    ) -> dict[str, Any]:
        policy_store.require_enabled()
        quartz = self._require_trusted()
        application, resolved_name = self._application(app_name)
        policy_store.require(self._bundle_id(resolved_name))
        nodes, elements, metadata = snapshot_tree(
            quartz,
            application,
            self._copy_attribute,
            max_nodes,
            preferred_window_id,
        )
        with self._lock:
            self._elements = elements
        return {
            "success": True,
            "application": resolved_name,
            "node_count": len(nodes),
            **metadata,
            "nodes": nodes,
            "warning": "Element IDs expire when the next snapshot is taken.",
        }

    def get_app_state(
        self, app_name: str, max_nodes: int = MAX_NODES
    ) -> dict[str, Any]:
        if not app_name:
            raise ComputerUseError("app_name is required.")
        policy_store.require(self._bundle_id(app_name))
        target = (
            Path(tempfile.gettempdir())
            / f"code-puppy-app-state-{int(time.time() * 1000)}.png"
        )
        capture = capture_window(app_name, target)
        # Electron apps often expose their useful web accessibility subtree only
        # while frontmost. Activate before reading AX state so the model receives
        # semantic controls instead of a nearly empty generic window tree.
        activate_application(
            int(capture["pid"]),
            str(capture["application"]),
        )
        snapshot = self.snapshot(
            app_name,
            max_nodes,
            preferred_window_id=int(capture["window_id"]),
        )
        with self._lock:
            elements = dict(self._elements)
        state = state_store.create(
            application=str(capture["application"]),
            bundle_id=str(capture["bundle_id"]),
            pid=int(capture["pid"]),
            window_id=int(capture["window_id"]),
            window_title=str(capture["window_title"]),
            geometry=capture["geometry"],
            screenshot_path=str(capture["path"]),
            elements=elements,
        )
        return {
            "success": True,
            **state.public_metadata(),
            "node_count": snapshot["node_count"],
            "scanned_node_count": snapshot["scanned_node_count"],
            "truncated": snapshot["truncated"],
            "scan_limit_reached": snapshot["scan_limit_reached"],
            "overflow_summary": snapshot["overflow_summary"],
            "nodes": snapshot["nodes"],
            "warning": (
                "Use this state_revision for one mutation or one guarded batch, "
                "then fetch fresh app state."
            ),
        }

    def _element(
        self, state_revision: str, element_id: int, *, consume: bool = True
    ) -> tuple[Any, Any]:
        quartz = self._require_trusted()
        state = self.require_state(state_revision)
        element = state.elements.get(element_id)
        if element is None:
            raise ComputerUseError(
                f"Unknown or expired element ID {element_id}; take a new snapshot."
            )
        if consume:
            self.require_state(state_revision, consume=True)
        return quartz, element

    def click(
        self, state_revision: str, element_id: int, *, consume: bool = True
    ) -> dict[str, Any]:
        quartz, element = self._element(state_revision, element_id, consume=consume)
        error = quartz.AXUIElementPerformAction(element, quartz.kAXPressAction)
        if error != quartz.kAXErrorSuccess:
            raise ComputerUseError(f"AXPress failed with accessibility error {error}.")
        return {
            "success": True,
            "element_id": element_id,
            "consumed_state_revision": state_revision,
            "state_invalidated": True,
        }

    def set_value(
        self,
        state_revision: str,
        element_id: int,
        value: str,
        *,
        consume: bool = True,
    ) -> dict[str, Any]:
        quartz, element = self._element(state_revision, element_id, consume=consume)
        error = quartz.AXUIElementSetAttributeValue(
            element, quartz.kAXValueAttribute, value
        )
        if error != quartz.kAXErrorSuccess:
            raise ComputerUseError(
                f"Setting AXValue failed with accessibility error {error}."
            )
        return {
            "success": True,
            "element_id": element_id,
            "consumed_state_revision": state_revision,
            "state_invalidated": True,
        }

    def perform_action(
        self,
        state_revision: str,
        element_id: int,
        action: str,
        *,
        consume: bool = True,
    ) -> dict[str, Any]:
        quartz, element = self._element(state_revision, element_id, consume=False)
        result = quartz.AXUIElementCopyActionNames(element, None)
        if isinstance(result, tuple):
            error, names = result
            actions = list(names or []) if error == quartz.kAXErrorSuccess else []
        else:
            actions = list(result or [])
        matched = next(
            (
                str(item)
                for item in actions
                if str(item).casefold() == action.casefold()
            ),
            None,
        )
        if matched is None:
            raise ComputerUseError(
                f"{action!r} is not exposed by element {element_id}. "
                f"Available actions: {[str(item) for item in actions]}"
            )
        if consume:
            self.require_state(state_revision, consume=True)
        error = quartz.AXUIElementPerformAction(element, matched)
        if error != quartz.kAXErrorSuccess:
            raise ComputerUseError(f"Accessibility action failed with error {error}.")
        return {
            "success": True,
            "element_id": element_id,
            "action": matched,
            "state_invalidated": True,
        }

    def select_text(
        self,
        state_revision: str,
        element_id: int,
        text: str,
        mode: str = "text",
        prefix: str | None = None,
        suffix: str | None = None,
        *,
        consume: bool = True,
    ) -> dict[str, Any]:
        quartz, element = self._element(state_revision, element_id, consume=False)
        value = self._copy_attribute(quartz, element, quartz.kAXValueAttribute)
        if not isinstance(value, str):
            raise ComputerUseError("The selected element has no text value.")
        starts = []
        offset = 0
        while True:
            found = value.find(text, offset)
            if found < 0:
                break
            before_ok = prefix is None or value[:found].endswith(prefix)
            after = found + len(text)
            after_ok = suffix is None or value[after:].startswith(suffix)
            if before_ok and after_ok:
                starts.append(found)
            offset = found + max(1, len(text))
        if len(starts) != 1:
            raise ComputerUseError(
                f"Text selection is ambiguous: found {len(starts)} matches."
            )
        modes = {
            "text": (starts[0], len(text)),
            "cursor_before": (starts[0], 0),
            "cursor_after": (starts[0] + len(text), 0),
        }
        try:
            location, length = modes[mode]
        except KeyError as exc:
            raise ComputerUseError(f"Unsupported selection mode: {mode}") from exc
        range_value = quartz.AXValueCreate(
            quartz.kAXValueCFRangeType, (location, length)
        )
        if range_value is None:
            raise ComputerUseError("Could not construct a text selection range.")
        if consume:
            self.require_state(state_revision, consume=True)
        error = quartz.AXUIElementSetAttributeValue(
            element, quartz.kAXSelectedTextRangeAttribute, range_value
        )
        if error != quartz.kAXErrorSuccess:
            raise ComputerUseError(
                f"Setting the selected text range failed with error {error}."
            )
        return {
            "success": True,
            "element_id": element_id,
            "mode": mode,
            "range": {"location": location, "length": length},
            "state_invalidated": True,
        }

    def click_pixel(
        self,
        state_revision: str,
        x: float,
        y: float,
        button: str = "left",
        click_count: int = 1,
        *,
        consume: bool = True,
    ) -> dict[str, Any]:
        quartz = self._require_trusted()
        state = self.require_state(state_revision)
        point = state.geometry.screenshot_to_quartz(x, y)
        buttons = {
            "left": (
                quartz.kCGMouseButtonLeft,
                quartz.kCGEventLeftMouseDown,
                quartz.kCGEventLeftMouseUp,
            ),
            "right": (
                quartz.kCGMouseButtonRight,
                quartz.kCGEventRightMouseDown,
                quartz.kCGEventRightMouseUp,
            ),
        }
        try:
            mouse_button, down_type, up_type = buttons[button.casefold()]
        except KeyError as exc:
            raise ComputerUseError(f"Unsupported mouse button: {button}") from exc
        click_count = max(1, min(int(click_count), 3))
        if consume:
            self.require_state(state_revision, consume=True)
        for index in range(click_count):
            down = quartz.CGEventCreateMouseEvent(None, down_type, point, mouse_button)
            up = quartz.CGEventCreateMouseEvent(None, up_type, point, mouse_button)
            quartz.CGEventSetIntegerValueField(
                down, quartz.kCGMouseEventClickState, index + 1
            )
            quartz.CGEventSetIntegerValueField(
                up, quartz.kCGMouseEventClickState, index + 1
            )
            quartz.CGEventPost(quartz.kCGHIDEventTap, down)
            quartz.CGEventPost(quartz.kCGHIDEventTap, up)
        return {
            "success": True,
            "screenshot_point": {"x": x, "y": y},
            "quartz_point": {"x": point[0], "y": point[1]},
            "button": button,
            "click_count": click_count,
            "state_invalidated": True,
        }

    def drag_pixel(
        self,
        state_revision: str,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        duration: float = 0.5,
        *,
        consume: bool = True,
    ) -> dict[str, Any]:
        quartz = self._require_trusted()
        state = self.require_state(state_revision)
        start = state.geometry.screenshot_to_quartz(start_x, start_y)
        end = state.geometry.screenshot_to_quartz(end_x, end_y)
        duration = max(0.05, min(float(duration), 5.0))
        if consume:
            self.require_state(state_revision, consume=True)
        steps = max(2, min(120, round(duration * 60)))
        down = quartz.CGEventCreateMouseEvent(
            None, quartz.kCGEventLeftMouseDown, start, quartz.kCGMouseButtonLeft
        )
        quartz.CGEventPost(quartz.kCGHIDEventTap, down)
        for index in range(1, steps + 1):
            fraction = index / steps
            point = (
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            )
            dragged = quartz.CGEventCreateMouseEvent(
                None,
                quartz.kCGEventLeftMouseDragged,
                point,
                quartz.kCGMouseButtonLeft,
            )
            quartz.CGEventPost(quartz.kCGHIDEventTap, dragged)
            time.sleep(duration / steps)
        up = quartz.CGEventCreateMouseEvent(
            None, quartz.kCGEventLeftMouseUp, end, quartz.kCGMouseButtonLeft
        )
        quartz.CGEventPost(quartz.kCGHIDEventTap, up)
        return {
            "success": True,
            "start_screenshot_point": {"x": start_x, "y": start_y},
            "end_screenshot_point": {"x": end_x, "y": end_y},
            "duration": duration,
            "state_invalidated": True,
        }

    def press_key(
        self,
        state_revision: str,
        key: str,
        modifiers: list[str] | None = None,
        *,
        consume: bool = True,
    ) -> dict[str, Any]:
        quartz = self._require_trusted()
        self.require_state(state_revision)
        normalized = key.casefold()
        if normalized not in KEY_CODES:
            raise ComputerUseError(f"Unsupported key: {key}")
        flags = 0
        flag_map = {
            "command": quartz.kCGEventFlagMaskCommand,
            "shift": quartz.kCGEventFlagMaskShift,
            "option": quartz.kCGEventFlagMaskAlternate,
            "control": quartz.kCGEventFlagMaskControl,
        }
        for modifier in modifiers or []:
            try:
                flags |= flag_map[modifier.casefold()]
            except KeyError as exc:
                raise ComputerUseError(f"Unsupported modifier: {modifier}") from exc
        if consume:
            self.require_state(state_revision, consume=True)
        for down in (True, False):
            event = quartz.CGEventCreateKeyboardEvent(None, KEY_CODES[normalized], down)
            quartz.CGEventSetFlags(event, flags)
            quartz.CGEventPost(quartz.kCGHIDEventTap, event)
        return {"success": True, "key": key, "modifiers": modifiers or []}

    def type_text(
        self, state_revision: str, text: str, *, consume: bool = True
    ) -> dict[str, Any]:
        quartz = self._require_trusted()
        self.require_state(state_revision)
        if len(text) > 10_000:
            raise ComputerUseError("Text is limited to 10,000 characters per call.")
        if consume:
            self.require_state(state_revision, consume=True)
        event_down = quartz.CGEventCreateKeyboardEvent(None, 0, True)
        event_up = quartz.CGEventCreateKeyboardEvent(None, 0, False)
        quartz.CGEventKeyboardSetUnicodeString(event_down, len(text), text)
        quartz.CGEventKeyboardSetUnicodeString(event_up, len(text), text)
        quartz.CGEventPost(quartz.kCGHIDEventTap, event_down)
        quartz.CGEventPost(quartz.kCGHIDEventTap, event_up)
        return {"success": True, "characters": len(text)}

    def scroll_pages(
        self,
        state_revision: str,
        direction: str,
        pages: float = 1.0,
        *,
        consume: bool = True,
    ) -> dict[str, Any]:
        quartz = self._require_trusted()
        state = self.require_state(state_revision)
        directions = {
            "up": (1, 0),
            "down": (-1, 0),
            "left": (0, 1),
            "right": (0, -1),
        }
        try:
            vertical_sign, horizontal_sign = directions[direction.casefold()]
        except KeyError as exc:
            raise ComputerUseError(
                f"Unsupported scroll direction: {direction}"
            ) from exc
        pages = max(0.05, min(float(pages), 10.0))
        vertical = round(
            vertical_sign * pages * state.geometry.image_height_pixels * 0.85
        )
        horizontal = round(
            horizontal_sign * pages * state.geometry.image_width_pixels * 0.85
        )
        if consume:
            self.require_state(state_revision, consume=True)
        event = quartz.CGEventCreateScrollWheelEvent(
            None,
            quartz.kCGScrollEventUnitPixel,
            2,
            vertical,
            horizontal,
        )
        quartz.CGEventPost(quartz.kCGHIDEventTap, event)
        return {
            "success": True,
            "direction": direction,
            "pages": pages,
            "pixel_delta": {"vertical": vertical, "horizontal": horizontal},
            "state_invalidated": True,
        }

    def screenshot(
        self, path: str | None = None, app_name: str | None = None
    ) -> dict[str, Any]:
        if not app_name:
            raise ComputerUseError(
                "app_name is required so screenshot capture can enforce the "
                "application deny policy."
            )
        target = (
            Path(path).expanduser()
            if path
            else Path(tempfile.gettempdir())
            / f"code-puppy-computer-use-{int(time.time() * 1000)}.png"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        policy_store.require(self._bundle_id(app_name))
        return capture_window(app_name, target)


backend = MacOSBackend()
