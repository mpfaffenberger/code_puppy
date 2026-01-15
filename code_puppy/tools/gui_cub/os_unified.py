"""Cross-platform unified UI tools that dispatch to Windows or macOS implementations.

These provide parity-style interfaces: ui_list_windows, ui_list_elements, ui_find_element, ui_click_element.
"""

from __future__ import annotations

import sys
from typing import Any

from pydantic_ai import RunContext

from code_puppy.messaging import emit_info, emit_warning
from .rich_emit import emit_rich
from code_puppy.tools.common import generate_group_id
from code_puppy.tools.gui_cub.result_types import (
    ElementClickResult,
    ElementListResult,
    ElementSearchResult,
    WindowListResult,
)

if sys.platform == "win32":
    from code_puppy.tools.gui_cub.windows_automation import (
        list_elements_in_window as _win_list_elements,
        find_element as _win_find_element,
        click_element as _win_click_element,
        list_windows as _win_list_windows,
    )

    _WIN = True
else:
    _WIN = False

if sys.platform == "darwin":
    from code_puppy.tools.gui_cub.accessibility import (
        list_accessible_elements as _mac_list_elements,
        find_accessible_element as _mac_find_element,
        _list_macos_windows as _mac_list_windows,
    )

    try:
        import atomacos as _atomacos  # type: ignore
    except Exception:
        _atomacos = None
    _MAC = True
else:
    _MAC = False


# Module-level functions (importable by workflow executor)
# These are the actual implementations, wrapped by register_os_unified_tools()


def ui_click_element(
    context: RunContext,
    title: str | None = None,
    role: str | None = None,
    control_type: str | None = None,
    class_name: str | None = None,
    auto_id: str | None = None,
    fuzzy: bool = True,
    fuzzy_threshold: float = 0.7,
    window_title: str | None = None,
) -> ElementClickResult:
    """Click a UI element across OS.

    Windows: title/control_type/class_name/auto_id
    macOS: role/title
    """
    group_id = generate_group_id("ui_click_element", sys.platform)
    emit_rich(
        f"[bold white on blue] UI CLICK ELEMENT 🐻 [/bold white on blue] 🖱️ ({sys.platform})",
        message_group=group_id,
    )
    try:
        if _WIN:
            if window_title:
                try:
                    from code_puppy.tools.gui_cub.windows_automation import (
                        focus_window as _focus,
                    )

                    _focus(window_title=window_title)
                except Exception:
                    pass
            return _win_click_element(
                title=title,
                class_name=class_name,
                control_type=control_type,
                auto_id=auto_id,
                fuzzy=fuzzy,
                fuzzy_threshold=fuzzy_threshold,
            )
        if _MAC:
            # Implement macOS click via AXPress or mouse fallback
            try:
                search = _mac_find_element(
                    role=role,
                    title=title,
                    fuzzy=fuzzy,
                    fuzzy_threshold=fuzzy_threshold,
                )
                if not search.success or not search.found or not search.best_match:
                    return ElementClickResult(
                        success=False,
                        clicked=False,
                        error=search.error or "Element not found",
                    )
                # Try AXPress if we can resolve element via atomacos
                if _atomacos is not None:
                    app = None
                    try:
                        from code_puppy.tools.gui_cub.accessibility import (
                            get_frontmost_app,
                        )

                        app = get_frontmost_app()
                    except Exception:
                        app = None
                    if app is not None and title:
                        try:
                            # Try exact remainder lookup by title if role missing
                            elems = (
                                app.findAllR(AXRole=role) if role else app.findAllR()
                            )
                            for el in elems:
                                if getattr(el, "AXTitle", None) == title:
                                    try:
                                        el.Press()
                                        return ElementClickResult(
                                            success=True,
                                            clicked=True,
                                            method="ax_press",
                                            element=title,
                                            role=role,
                                        )
                                    except Exception:
                                        break
                        except Exception:
                            pass
                # Fallback to coordinate click using native API (multi-monitor safe)
                if search.best_match.center_x and search.best_match.center_y:
                    try:
                        from .platform import click_mouse_native

                        success, error = click_mouse_native(
                            x=search.best_match.center_x,
                            y=search.best_match.center_y,
                            button="left",
                            clicks=1,
                        )
                        if success:
                            return ElementClickResult(
                                success=True,
                                clicked=True,
                                method="native_click",
                                x=search.best_match.center_x,
                                y=search.best_match.center_y,
                            )
                        else:
                            return ElementClickResult(
                                success=False,
                                clicked=False,
                                error=error or "Native click failed",
                            )
                    except Exception as e:
                        return ElementClickResult(
                            success=False, clicked=False, error=str(e)
                        )
                return ElementClickResult(
                    success=False, clicked=False, error="No coordinates available"
                )
            except Exception as e:
                return ElementClickResult(success=False, clicked=False, error=str(e))
        return ElementClickResult(success=False, clicked=False)
    except Exception as e:
        return ElementClickResult(success=False, error=str(e))


def register_os_unified_tools(agent):
    """Register unified OS-aware UI tools."""

    @agent.tool
    def ui_list_windows(context: RunContext) -> WindowListResult:
        """List visible windows for the current OS.

        Windows: returns windows with hwnd/title/class_name/pid
        macOS: returns windows with owner/title/bounds
        """
        group_id = generate_group_id("ui_list_windows", sys.platform)
        emit_rich(
            f"[bold white on blue] UI LIST WINDOWS 🐻 [/bold white on blue] 🪟 ({sys.platform})",
            message_group=group_id,
        )
        try:
            if _WIN:
                wins = _win_list_windows()
                return WindowListResult(success=True, count=len(wins), windows=wins)
            if _MAC:
                wins = _mac_list_windows()
                return WindowListResult(success=True, count=len(wins), windows=wins)
            emit_warning(
                "[yellow]List windows is not supported on this OS[/yellow]",
                message_group=group_id,
            )
            return WindowListResult(success=False, error="Unsupported OS")
        except Exception as e:
            return WindowListResult(success=False, error=str(e))

    @agent.tool
    def ui_list_elements(
        context: RunContext,
        role: str | None = None,
        control_type: str | None = None,
        class_name: str | None = None,
        mode: str = "flat",
        depth: int = 5,
    ) -> ElementListResult:
        """List elements in the active window for the current OS.

        Windows: uses pywinauto to traverse controls.
        macOS: uses accessibility to list elements grouped by role.
        """
        group_id = generate_group_id("ui_list_elements", sys.platform)
        emit_rich(
            f"[bold white on blue] UI LIST ELEMENTS 🐻 [/bold white on blue] 📋 ({sys.platform})",
            message_group=group_id,
        )
        try:
            if _WIN:
                # Windows list ignores filters here (Windows-specific finder supports them via ui_find_element)
                return _win_list_elements()
            if _MAC:
                # macOS: choose between flat grouped list or hierarchical tree
                if mode == "tree":
                    try:
                        from code_puppy.tools.gui_cub.accessibility import (
                            _build_element_tree,
                        )
                        from code_puppy.tools.gui_cub.result_types import (
                            ElementListResult,
                        )
                        from code_puppy.tools.gui_cub.accessibility import (
                            get_frontmost_app,
                        )

                        app = get_frontmost_app()
                        if not app:
                            return ElementListResult(
                                success=False, error="No frontmost app"
                            )
                        elements = _build_element_tree(app, max_depth=depth)
                        by_type: dict[str, list[dict[str, Any]]] = {}
                        for node in elements:
                            t = node.get("type", "Unknown")
                            by_type.setdefault(t, []).append(node)
                        # Optional filter by role
                        if role:
                            filtered = [n for n in elements if n.get("type") == role]
                            elements = filtered
                        return ElementListResult(
                            success=True,
                            elements=elements,
                            by_type=by_type,
                            types=list(by_type.keys()),
                            total_elements=len(elements),
                        )
                    except Exception as e:
                        return ElementListResult(success=False, error=str(e))
                # Flat mode with optional role filter
                if role:
                    return _mac_list_elements(role=role)
                return _mac_list_elements()
            emit_warning(
                "[yellow]List elements is not supported on this OS[/yellow]",
                message_group=group_id,
            )
            return ElementListResult(success=False, error="Unsupported OS")
        except Exception as e:
            return ElementListResult(success=False, error=str(e))

    @agent.tool
    def ui_find_element(
        context: RunContext,
        title: str | None = None,
        role: str | None = None,
        control_type: str | None = None,
        class_name: str | None = None,
        auto_id: str | None = None,
        fuzzy: bool = True,
        fuzzy_threshold: float = 0.7,
        window_title: str | None = None,
    ) -> ElementSearchResult:
        """Find a UI element by name/role across OS.

        Windows: title/control_type/class_name/auto_id
        macOS: role/title
        """
        group_id = generate_group_id("ui_find_element", sys.platform)
        emit_rich(
            f"[bold white on blue] UI FIND ELEMENT 🐻 [/bold white on blue] 🔍 ({sys.platform})",
            message_group=group_id,
        )
        try:
            if _WIN:
                # If window_title is provided, focus window first
                if window_title:
                    try:
                        from code_puppy.tools.gui_cub.windows_automation import (
                            focus_window as _focus,
                        )

                        _focus(window_title=window_title)
                    except Exception:
                        pass
                return _win_find_element(
                    title=title,
                    class_name=class_name,
                    control_type=control_type,
                    auto_id=auto_id,
                    fuzzy=fuzzy,
                    fuzzy_threshold=fuzzy_threshold,
                )
            if _MAC:
                return _mac_find_element(
                    role=role,
                    title=title,
                    fuzzy=fuzzy,
                    fuzzy_threshold=fuzzy_threshold,
                )
            return ElementSearchResult(success=False, found=False)
        except Exception as e:
            return ElementSearchResult(success=False, error=str(e))

    @agent.tool
    def _wrapped_ui_click_element(
        context: RunContext,
        title: str | None = None,
        role: str | None = None,
        control_type: str | None = None,
        class_name: str | None = None,
        auto_id: str | None = None,
        fuzzy: bool = True,
        fuzzy_threshold: float = 0.7,
        window_title: str | None = None,
    ) -> ElementClickResult:
        """Click a UI element across OS.

        Windows: title/control_type/class_name/auto_id
        macOS: role/title
        """
        return ui_click_element(
            context,
            title,
            role,
            control_type,
            class_name,
            auto_id,
            fuzzy,
            fuzzy_threshold,
            window_title,
        )
