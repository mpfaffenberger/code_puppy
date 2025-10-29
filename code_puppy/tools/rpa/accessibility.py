"""Accessibility API integration for pixel-perfect UI automation on macOS using atomacos."""

from __future__ import annotations

import sys
from typing import Any

# Check if we're on macOS and atomacos is available
if sys.platform != "darwin":
    ACCESSIBILITY_AVAILABLE = False
    atomacos = None
else:
    try:
        import atomacos

        ACCESSIBILITY_AVAILABLE = True
    except ImportError:
        ACCESSIBILITY_AVAILABLE = False
        atomacos = None

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

from .constants import ERROR_ATOMACOS_MISSING, ERROR_NO_FRONTMOST_APP
from .fuzzy_matching import fuzzy_match, explain_match
from .result_types import (
    ElementClickResult,
    ElementInfo,
    ElementListResult,
    ElementSearchResult,
    WindowListResult,
)


def get_frontmost_app():
    """Get the frontmost (active) application.

    Note: atomacos.getFrontmostApp() has known issues and often returns
    the wrong application or hangs. Using alternative approach.
    """
    if not ACCESSIBILITY_AVAILABLE:
        return None

    try:
        # Use AppKit/NSWorkspace to get frontmost app reliably
        from AppKit import NSWorkspace

        workspace = NSWorkspace.sharedWorkspace()
        frontmost_app = workspace.frontmostApplication()
        app_name = frontmost_app.localizedName()

        # Now get atomacos reference by name
        app_ref = atomacos.getAppRefByLocalizedName(app_name)
        return app_ref
    except Exception as e:
        # Silently return None - accessibility API is unreliable
        return None


def _element_to_info(elem: Any) -> ElementInfo:
    """Convert atomacos element to ElementInfo model.

    Args:
        elem: atomacos element

    Returns:
        ElementInfo with element properties
    """
    try:
        elem_role = getattr(elem, "AXRole", None)
        elem_title = getattr(elem, "AXTitle", None)
        elem_description = getattr(elem, "AXDescription", None)
        elem_position = getattr(elem, "AXPosition", None)
        elem_size = getattr(elem, "AXSize", None)

        info = ElementInfo(
            role=elem_role, title=elem_title, description=elem_description
        )

        # Calculate position and center
        if elem_position and elem_size:
            x = int(elem_position[0])
            y = int(elem_position[1])
            width = int(elem_size[0])
            height = int(elem_size[1])

            info.x = x
            info.y = y
            info.width = width
            info.height = height
            info.center_x = x + width // 2
            info.center_y = y + height // 2

        return info
    except Exception:
        # Return basic info if something fails
        return ElementInfo()


def find_accessible_element(
    role: str | None = None,
    title: str | None = None,
    in_frontmost_app: bool = True,
    fuzzy: bool = True,
    fuzzy_threshold: float = 0.6,
) -> ElementSearchResult:
    """
    Find a UI element using macOS Accessibility API via atomacos with fuzzy matching.

    Args:
        role: Element role (e.g., 'AXButton', 'AXTextField', 'AXStaticText')
        title: Element title/name to search for (supports fuzzy matching!)
        in_frontmost_app: Search only in frontmost app (True) or system-wide (False)
        fuzzy: Enable fuzzy matching for title (default: True)
        fuzzy_threshold: Minimum similarity score for fuzzy matches (0.0-1.0, default: 0.6)

    Returns:
        ElementSearchResult with element info including exact position

    Fuzzy Matching Examples:
        - "Submit" matches: "Submit", "Submit Button", "submitBtn", "btn_submit", "SUBMIT"
        - "Save" matches: "Save", "Save As", "saveButton", "btn-save"
        - Case-insensitive and handles common naming variations
    """
    if not ACCESSIBILITY_AVAILABLE:
        return ElementSearchResult(success=False, error=ERROR_ATOMACOS_MISSING)

    group_id = generate_group_id("find_accessible_element", f"{role}_{title}")
    emit_info(
        f"[bold white on blue] FIND ACCESSIBLE ELEMENT [/bold white on blue] 🔍 role={role} title='{title}' fuzzy={fuzzy}",
        message_group=group_id,
    )

    try:
        # Get app reference
        if in_frontmost_app:
            app = get_frontmost_app()
            if not app:
                return ElementSearchResult(success=False, error=ERROR_NO_FRONTMOST_APP)
            emit_info(
                "[dim]Searching in frontmost application...[/dim]",
                message_group=group_id,
            )
        else:
            app = get_frontmost_app()
            emit_info(
                "[dim]Searching in frontmost application (system-wide not fully implemented)...[/dim]",
                message_group=group_id,
            )

        # Strategy 1: Try exact match first (fastest)
        matches = []
        if title and role:
            # Exact match with both criteria
            try:
                exact_matches = app.findAllR(AXRole=role, AXTitle=title)
                if exact_matches:
                    emit_info(
                        f"[green]Found {len(exact_matches)} exact match(es)[/green]",
                        message_group=group_id,
                    )
                    matches = exact_matches
            except Exception:
                pass

        # Strategy 2: If no exact match and fuzzy enabled, do fuzzy search
        if not matches and title and fuzzy:
            emit_info(
                "[cyan]No exact match, trying fuzzy search...[/cyan]",
                message_group=group_id,
            )

            # Get all elements (filtered by role if provided)
            if role:
                all_elements = app.findAllR(AXRole=role)
            else:
                all_elements = app.findAllR()

            emit_info(
                f"[dim]Searching through {len(all_elements)} elements...[/dim]",
                message_group=group_id,
            )

            # Convert elements to dictionaries for fuzzy matching
            element_dicts = []
            for elem in all_elements:
                try:
                    elem_dict = {
                        "element": elem,  # Store reference
                        "title": getattr(elem, "AXTitle", None) or "",
                        "description": getattr(elem, "AXDescription", None) or "",
                        "role": getattr(elem, "AXRole", None) or "",
                        "value": getattr(elem, "AXValue", None) or "",
                    }
                    element_dicts.append(elem_dict)
                except Exception:
                    continue

            # Perform fuzzy matching on title, description, and value
            fuzzy_matches = fuzzy_match(
                search_text=title,
                candidates=element_dicts,
                attribute_names=["title", "description", "value"],
                threshold=fuzzy_threshold,
            )

            if fuzzy_matches:
                emit_info(
                    f"[green]Found {len(fuzzy_matches)} fuzzy match(es)[/green]",
                    message_group=group_id,
                )

                # Show top 3 matches with scores
                for i, (elem_dict, score) in enumerate(fuzzy_matches[:3]):
                    explanation = explain_match(title, elem_dict["title"], score)
                    emit_info(
                        f"  [{i + 1}] {elem_dict['role']} - '{elem_dict['title']}' (score: {score:.2f})",
                        message_group=group_id,
                    )
                    emit_info(
                        f"      {explanation}",
                        message_group=group_id,
                    )

                # Extract raw elements
                matches = [elem_dict["element"] for elem_dict, _ in fuzzy_matches]
            else:
                emit_warning(
                    f"[yellow]No fuzzy matches found with threshold {fuzzy_threshold}[/yellow]",
                    message_group=group_id,
                )

        # Strategy 3: If only role specified (no title)
        elif role and not title:
            try:
                matches = app.findAllR(AXRole=role)
            except Exception:
                pass

        if not matches:
            emit_warning(
                "[yellow]No elements found matching criteria[/yellow]",
                message_group=group_id,
            )
            return ElementSearchResult(success=True, found=False, matches=[])

        # Convert matches to ElementInfo models
        results = []
        for elem in matches:
            try:
                info = _element_to_info(elem)
                # Store raw element for potential direct interaction
                # (Note: Can't serialize to Pydantic, so we'll handle separately)
                results.append((info, elem))
            except Exception:
                continue

        emit_info(
            f"[green]Found {len(results)} matching element(s)[/green]",
            message_group=group_id,
        )

        # Show first few matches
        for i, (info, _) in enumerate(results[:3]):
            title_str = info.title or "(no title)"
            if info.center_x and info.center_y:
                emit_info(
                    f"  [{i + 1}] {info.role} - '{title_str}' at ({info.center_x}, {info.center_y})",
                    message_group=group_id,
                )
            else:
                emit_info(
                    f"  [{i + 1}] {info.role} - '{title_str}' (no position)",
                    message_group=group_id,
                )

        # Extract just ElementInfo for serialization
        element_infos = [info for info, _ in results]

        return ElementSearchResult(
            success=True,
            found=True,
            count=len(element_infos),
            matches=element_infos,
            best_match=element_infos[0] if element_infos else None,
        )

    except Exception as e:
        emit_error(
            f"[red]Accessibility search failed: {str(e)}[/red]",
            message_group=group_id,
        )
        return ElementSearchResult(success=False, error=str(e))


def list_accessible_elements(
    role: str | None = None, in_frontmost_app: bool = True
) -> ElementListResult:
    """
    List all accessible UI elements, optionally filtered by role.

    Args:
        role: Optional role filter (e.g., 'AXButton', 'AXTextField')
        in_frontmost_app: Search only in frontmost app (True) or system-wide (False)

    Returns:
        ElementListResult with list of elements
    """
    if not ACCESSIBILITY_AVAILABLE:
        return ElementListResult(success=False, error=ERROR_ATOMACOS_MISSING)

    group_id = generate_group_id("list_accessible_elements", str(role))
    emit_info(
        f"[bold white on blue] LIST ACCESSIBLE ELEMENTS [/bold white on blue] 📋 role={role}",
        message_group=group_id,
    )

    try:
        app = get_frontmost_app()
        if not app:
            return ElementListResult(success=False, error=ERROR_NO_FRONTMOST_APP)

        # Find elements
        if role:
            elements = app.findAllR(AXRole=role)
        else:
            elements = app.findAllR()

        # Group by role
        by_role = {}
        for elem in elements:
            try:
                elem_role = getattr(elem, "AXRole", "Unknown")
                elem_title = getattr(elem, "AXTitle", None)
                elem_description = getattr(elem, "AXDescription", None)

                if elem_role not in by_role:
                    by_role[elem_role] = []

                by_role[elem_role].append(
                    {"title": elem_title, "description": elem_description}
                )
            except Exception:
                continue

        emit_info(
            f"[green]Found {len(elements)} elements across {len(by_role)} roles[/green]",
            message_group=group_id,
        )

        for role_name, elems in sorted(by_role.items()):
            emit_info(f"  {role_name}: {len(elems)} elements", message_group=group_id)

        return ElementListResult(
            success=True,
            total_elements=len(elements),
            by_role=by_role,
            roles=list(by_role.keys()),
        )

    except Exception as e:
        emit_error(
            f"[red]Failed to list elements: {str(e)}[/red]", message_group=group_id
        )
        return ElementListResult(success=False, error=str(e))


def _build_element_tree(app_ref, max_depth: int = 5) -> list[dict[str, Any]]:
    """Traverse the accessibility tree for the frontmost app and build a list of nodes.

    Each node contains: type(role), title, description, depth. This mirrors Windows parity.
    """
    nodes: list[dict[str, Any]] = []

    def safe_children(elem):
        try:
            return elem.AXChildren
        except Exception:
            return []

    def traverse(elem, depth=0):
        if depth > max_depth:
            return
        try:
            role = getattr(elem, "AXRole", None) or "Unknown"
            title = getattr(elem, "AXTitle", None)
            description = getattr(elem, "AXDescription", None)
            nodes.append(
                {
                    "type": role,
                    "name": title,
                    "description": description,
                    "depth": depth,
                }
            )
            for child in safe_children(elem):
                traverse(child, depth + 1)
        except Exception:
            return

    try:
        root = app_ref.AXFocusedWindow or app_ref
        traverse(root, 0)
    except Exception:
        pass

    return nodes


def _list_macos_windows() -> list[dict[str, Any]]:
    """List visible windows on macOS using Quartz APIs."""
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID,
        )  # type: ignore
    except Exception:
        return []

    windows = (
        CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
        or []
    )
    out: list[dict[str, Any]] = []
    for win in windows:
        try:
            layer = win.get("kCGWindowLayer", 0)
            if layer != 0:
                continue  # Skip non-app windows (status bar, etc.)
            owner = win.get("kCGWindowOwnerName")
            title = win.get("kCGWindowName")
            bounds = win.get("kCGWindowBounds", {})
            out.append(
                {
                    "owner": owner,
                    "title": title,
                    "bounds": bounds,
                }
            )
        except Exception:
            continue
    return out


def register_accessibility_tools(agent):
    """Register accessibility API tools for macOS."""

    @agent.tool
    def desktop_list_windows(context: RunContext) -> WindowListResult:
        """
        List visible application windows on macOS using Quartz APIs.

        Returns a WindowListResult with windows containing owner(name), title, and bounds.

        Note: macOS only.
        """
        if not ACCESSIBILITY_AVAILABLE:
            return WindowListResult(success=False, error=ERROR_ATOMACOS_MISSING)

        group_id = generate_group_id("desktop_list_windows", "all")
        emit_info(
            "[bold white on blue] MAC LIST WINDOWS [/bold white on blue] 🪟",
            message_group=group_id,
        )
        wins = _list_macos_windows()
        return WindowListResult(success=True, count=len(wins), windows=wins)

    @agent.tool
    def desktop_list_accessible_tree(
        context: RunContext, max_depth: int = 5
    ) -> ElementListResult:
        """
        List a hierarchical accessibility element tree for the frontmost app.

        Returns an ElementListResult with elements and by_type to mirror Windows parity.

        Args:
            max_depth: Maximum recursion depth (default: 5)

        Note: macOS only. Requires atomacos.
        """
        if not ACCESSIBILITY_AVAILABLE:
            return ElementListResult(success=False, error=ERROR_ATOMACOS_MISSING)

        group_id = generate_group_id("desktop_list_accessible_tree", str(max_depth))
        emit_info(
            "[bold white on blue] ACCESSIBILITY TREE [/bold white on blue] 🌲",
            message_group=group_id,
        )

        app = get_frontmost_app()
        if not app:
            return ElementListResult(success=False, error=ERROR_NO_FRONTMOST_APP)

        elements = _build_element_tree(app, max_depth=max_depth)
        by_type: dict[str, list[dict[str, Any]]] = {}
        for node in elements:
            t = node.get("type", "Unknown")
            by_type.setdefault(t, []).append(node)

        emit_info(
            f"[green]Tree contains {len(elements)} nodes across {len(by_type)} types[/green]",
            message_group=group_id,
        )

        return ElementListResult(
            success=True,
            elements=elements,
            by_type=by_type,
            types=list(by_type.keys()),
            total_elements=len(elements),
        )

    @agent.tool
    def desktop_find_accessible_element(
        context: RunContext,
        role: str | None = None,
        title: str | None = None,
        in_frontmost_app: bool = True,
        fuzzy: bool = True,
        fuzzy_threshold: float = 0.6,
    ) -> ElementSearchResult:
        """
        Find UI element using macOS Accessibility API with PIXEL-PERFECT accuracy and FUZZY MATCHING.

        This is the most accurate way to locate UI elements on macOS!
        Now with intelligent fuzzy matching for flexible element finding.

        Args:
            role: Element role - common values:
                  - 'AXButton' - Buttons
                  - 'AXTextField' - Text input fields
                  - 'AXStaticText' - Text labels
                  - 'AXMenuItem' - Menu items
                  - 'AXCheckBox' - Checkboxes
                  - 'AXRadioButton' - Radio buttons
                  - 'AXPopUpButton' - Dropdown menus
                  - 'AXWindow' - Windows
            title: Element title/name (supports fuzzy matching!)
                   Examples:
                   - "Submit" matches: "Submit", "Submit Form", "submitBtn", "btn_submit"
                   - "Save" matches: "Save", "Save As...", "saveButton", "btn-save"
            in_frontmost_app: Search only in active app (faster) vs system-wide
            fuzzy: Enable intelligent fuzzy matching (default: True)
            fuzzy_threshold: Minimum similarity score (0.0-1.0, default: 0.6)
                            Higher = stricter matching, Lower = more permissive

        Returns:
            ElementSearchResult with exact element position and properties
            - If found: center_x, center_y for pixel-perfect clicking!
            - Multiple matches returned if found, sorted by match quality

        Examples:
            - desktop_find_accessible_element(role="AXButton", title="Save")
            - desktop_find_accessible_element(title="Submit")  # Fuzzy matches "Submit Button", "submitBtn", etc.
            - desktop_find_accessible_element(role="AXButton", title="close", fuzzy_threshold=0.8)  # Stricter matching
            - desktop_find_accessible_element(title="login", fuzzy=False)  # Exact match only

        Note: macOS only. Requires atomacos library.
        """
        return find_accessible_element(
            role=role,
            title=title,
            in_frontmost_app=in_frontmost_app,
            fuzzy=fuzzy,
            fuzzy_threshold=fuzzy_threshold,
        )

    @agent.tool
    def desktop_list_accessible_elements(
        context: RunContext,
        role: str | None = None,
        in_frontmost_app: bool = True,
    ) -> ElementListResult:
        """
        List all accessible UI elements in the frontmost app.

        Useful for discovering what elements are available and their roles.

        Args:
            role: Optional role filter (e.g., 'AXButton' to list only buttons)
            in_frontmost_app: Search only in active app vs system-wide

        Returns:
            ElementListResult with elements grouped by role

        Examples:
            - desktop_list_accessible_elements()  # List all elements
            - desktop_list_accessible_elements(role="AXButton")  # List only buttons

        Note: macOS only. Requires atomacos library.
        """
        return list_accessible_elements(role=role, in_frontmost_app=in_frontmost_app)

    @agent.tool
    def desktop_click_accessible_element(
        context: RunContext,
        role: str | None = None,
        title: str | None = None,
        in_frontmost_app: bool = True,
        fuzzy: bool = True,
        fuzzy_threshold: float = 0.6,
    ) -> ElementClickResult:
        """
        Find and click a UI element using Accessibility API with FUZZY MATCHING (MOST ACCURATE!).

        This combines intelligent element finding and clicking in one step.
        Uses fuzzy matching to handle common UI element naming variations.

        Args:
            role: Element role (e.g., 'AXButton')
            title: Element title/name to search for (supports fuzzy matching!)
                   Examples: "Submit" matches "Submit Button", "submitBtn", "btn_submit"
            in_frontmost_app: Search only in active app
            fuzzy: Enable intelligent fuzzy matching (default: True)
            fuzzy_threshold: Minimum similarity score (0.0-1.0, default: 0.6)

        Returns:
            ElementClickResult with success status and click coordinates

        Examples:
            - desktop_click_accessible_element(role="AXButton", title="Save")
            - desktop_click_accessible_element(title="Submit")  # Fuzzy matches variations
            - desktop_click_accessible_element(title="close", fuzzy_threshold=0.8)  # Stricter

        Note: macOS only. Uses native AX Press action or mouse click.
        """
        # Find the element with fuzzy matching
        result = find_accessible_element(
            role=role,
            title=title,
            in_frontmost_app=in_frontmost_app,
            fuzzy=fuzzy,
            fuzzy_threshold=fuzzy_threshold,
        )

        if not result.success or not result.found:
            return ElementClickResult(
                success=False, error=result.error or "Element not found"
            )

        best_match = result.best_match
        if not best_match:
            return ElementClickResult(success=False, error="No element found")

        # We need to re-find the element to get the raw atomacos reference
        # (since we can't serialize it in Pydantic models)
        # This is a bit inefficient but necessary for the architecture
        group_id = generate_group_id("desktop_click_accessible", f"{role}_{title}")

        try:
            app = get_frontmost_app()
            if not app:
                return ElementClickResult(success=False, error=ERROR_NO_FRONTMOST_APP)

            search_criteria = {}
            if role:
                search_criteria["AXRole"] = role
            if title:
                search_criteria["AXTitle"] = title

            if search_criteria:
                matches = app.findAllR(**search_criteria)
            else:
                matches = []

            if matches:
                element_ref = matches[0]
                # Try native Press action first
                try:
                    element_ref.Press()
                    emit_info(
                        f"[green]Pressed '{best_match.title}' using native AX Press[/green]",
                        message_group=group_id,
                    )
                    return ElementClickResult(
                        success=True,
                        clicked=True,
                        method="ax_press",
                        element=best_match.title,
                        role=best_match.role,
                    )
                except Exception:
                    pass  # Fall through to mouse click

        except Exception:
            pass  # Fall through to mouse click

        # Fallback: Click at element center using mouse
        if best_match.center_x is None or best_match.center_y is None:
            return ElementClickResult(
                success=False, error="Could not determine element position"
            )

        try:
            import pyautogui

            pyautogui.click(x=best_match.center_x, y=best_match.center_y)

            emit_info(
                f"[green]Clicked '{best_match.title}' at ({best_match.center_x}, {best_match.center_y})[/green]",
                message_group=group_id,
            )

            return ElementClickResult(
                success=True,
                clicked=True,
                method="mouse_click",
                element=best_match.title,
                role=best_match.role,
                x=best_match.center_x,
                y=best_match.center_y,
            )
        except Exception as e:
            return ElementClickResult(success=False, error=f"Click failed: {str(e)}")

    @agent.tool
    def desktop_get_accessible_element_value(
        context: RunContext,
        role: str | None = None,
        title: str | None = None,
        in_frontmost_app: bool = True,
        fuzzy: bool = True,
        fuzzy_threshold: float = 0.6,
    ) -> ElementSearchResult:
        """
        Get the AXValue (text/value) of an accessible element using fuzzy matching.

        Use cases:
        - Verify-before-type: confirm target is a text field (AXTextField)
        - Verify-after-type: read AXValue to confirm entered text

        Args:
            role: Element role (e.g., 'AXTextField')
            title: Element title/name (supports fuzzy matching)
            in_frontmost_app: Search only in active app vs system-wide
            fuzzy: Enable fuzzy matching on title/description/value
            fuzzy_threshold: Minimum similarity score (default 0.6)

        Returns:
            ElementSearchResult where best_match.value is populated if available
        """
        result = find_accessible_element(
            role=role,
            title=title,
            in_frontmost_app=in_frontmost_app,
            fuzzy=fuzzy,
            fuzzy_threshold=fuzzy_threshold,
        )

        # Populate value field by re-querying AXValue when possible
        try:
            if (
                result.success
                and result.found
                and result.best_match
                and ACCESSIBILITY_AVAILABLE
            ):
                app = get_frontmost_app()
                if app:
                    # Try exact match first
                    search_criteria = {}
                    if role:
                        search_criteria["AXRole"] = role
                    if title:
                        search_criteria["AXTitle"] = title
                    matches = app.findAllR(**search_criteria) if search_criteria else []
                    if matches:
                        elem = matches[0]
                        ax_value = getattr(elem, "AXValue", None)
                        if ax_value is not None:
                            result.best_match.value = str(ax_value)
            return result
        except Exception:
            return result
