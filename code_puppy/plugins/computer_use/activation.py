"""Bring the state target to the foreground before sending global input."""

from __future__ import annotations

import time

from .backend_types import ComputerUseError


def _workspace():
    try:
        from AppKit import NSWorkspace
    except ImportError as exc:
        raise ComputerUseError("AppKit bindings are unavailable.") from exc
    return NSWorkspace.sharedWorkspace()


def activate_application(pid: int, application_name: str, timeout: float = 1.0) -> None:
    workspace = _workspace()
    application = next(
        (
            app
            for app in workspace.runningApplications()
            if int(app.processIdentifier()) == pid
        ),
        None,
    )
    if application is None or bool(application.isTerminated()):
        raise ComputerUseError(
            f"The target application {application_name} is no longer running."
        )
    # NSApplicationActivateAllWindows | NSApplicationActivateIgnoringOtherApps.
    if not bool(application.activateWithOptions_(3)):
        raise ComputerUseError(
            f"Could not activate target application {application_name}."
        )
    # A background CLI can receive a successful AppKit result without macOS
    # changing focus. The plugin already requires Accessibility permission, so
    # explicitly foreground and raise the target window through AX as well.
    try:
        import ApplicationServices as api

        ax_application = api.AXUIElementCreateApplication(pid)
        api.AXUIElementSetAttributeValue(
            ax_application,
            api.kAXFrontmostAttribute,
            True,
        )
        result = api.AXUIElementCopyAttributeValue(
            ax_application,
            api.kAXWindowsAttribute,
            None,
        )
        windows = result[1] if isinstance(result, tuple) else result
        if windows:
            api.AXUIElementSetAttributeValue(
                windows[0],
                api.kAXMainAttribute,
                True,
            )
            api.AXUIElementPerformAction(windows[0], api.kAXRaiseAction)
    except ImportError:
        pass
    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline:
        frontmost = workspace.frontmostApplication()
        if frontmost is not None and int(frontmost.processIdentifier()) == pid:
            return
        time.sleep(0.02)
    raise ComputerUseError(
        f"Target application {application_name} did not become frontmost."
    )


def activate_state(state, timeout: float = 1.0) -> None:
    activate_application(state.pid, state.application, timeout)
