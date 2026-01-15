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


from code_puppy.messaging import emit_error, emit_warning
from ..rich_emit import emit_rich
from code_puppy.tools.common import generate_group_id

from ..constants import ERROR_ATOMACOS_MISSING, ERROR_NO_FRONTMOST_APP
from ..fuzzy_matching import explain_match, fuzzy_match
from ..performance_monitor import get_monitor
from ..result_types import (
    ElementInfo,
    ElementSearchResult,
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
    except Exception:
        # Silently return None - accessibility API is unreliable
        return None


def _element_to_info(elem: Any) -> ElementInfo:
    """Convert atomacos element to ElementInfo model.

    Args:
        elem: atomacos element

    Returns:
        ElementInfo with element properties including comprehensive attributes
    """
    try:
        elem_role = getattr(elem, "AXRole", None)
        elem_title = getattr(elem, "AXTitle", None)
        elem_description = getattr(elem, "AXDescription", None)
        elem_position = getattr(elem, "AXPosition", None)
        elem_size = getattr(elem, "AXSize", None)

        info = ElementInfo(
            role=elem_role,
            title=elem_title,
            description=elem_description,
            # NEW: Comprehensive attributes
            value=getattr(elem, "AXValue", None),
            placeholder=getattr(elem, "AXPlaceholderValue", None),
            help=getattr(elem, "AXHelp", None),
            role_description=getattr(elem, "AXRoleDescription", None),
            identifier=getattr(elem, "AXIdentifier", None),
            subrole=getattr(elem, "AXSubrole", None),
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
    identifier: str | None = None,  # NEW: AXIdentifier exact match
    in_frontmost_app: bool = True,
    fuzzy: bool = True,
    fuzzy_threshold: float = 0.25,  # LOWERED: Allow description-only matches (weight=0.3)
    early_stop_threshold: float = 0.6,  # LOWERED: Match lowered threshold
) -> ElementSearchResult:
    """
    Find a UI element using macOS Accessibility API via atomacos with fuzzy matching.

    OPTIMIZED: Now includes early-stop logic, performance monitoring, and identifier support.

    Args:
        role: Element role (e.g., 'AXButton', 'AXTextField', 'AXStaticText')
        title: Element title/name to search for (supports fuzzy matching!)
        identifier: AXIdentifier for exact match (highest priority, macOS equivalent of AutomationId)
        in_frontmost_app: Search only in frontmost app (True) or system-wide (False)
        fuzzy: Enable fuzzy matching for title (default: True)
        fuzzy_threshold: Minimum similarity score for fuzzy matches (0.0-1.0, default: 0.25)
        early_stop_threshold: Score threshold for early-stop optimization (default: 0.6)

    Returns:
        ElementSearchResult with element info including exact position

    Search Priority:
        1. Identifier exact match (if provided) - MOST RELIABLE
        2. Title exact match
        3. Fuzzy match on title, description, placeholder, help, role_description

    Fuzzy Matching Examples:
        - "Submit" matches: "Submit", "Submit Button", "submitBtn", "btn_submit", "SUBMIT"
        - "Save" matches: "Save", "Save As", "saveButton", "btn-save"
        - "Search" matches placeholder text in search fields
        - Case-insensitive and handles common naming variations
    """
    if not ACCESSIBILITY_AVAILABLE:
        return ElementSearchResult(success=False, error=ERROR_ATOMACOS_MISSING)

    monitor = get_monitor()
    group_id = generate_group_id("find_accessible_element", f"{role}_{title}")
    emit_rich(
        f"[bold white on blue] MAC FIND ACCESSIBLE ELEMENT 🐻 [/bold white on blue] 🔍 role={role} title='{title}' fuzzy={fuzzy}",
        message_group=group_id,
    )

    try:
        # Get app reference
        if in_frontmost_app:
            app = get_frontmost_app()
            if not app:
                return ElementSearchResult(success=False, error=ERROR_NO_FRONTMOST_APP)
            emit_rich(
                "[dim]Searching in frontmost application...[/dim]",
                message_group=group_id,
            )
        else:
            app = get_frontmost_app()
            emit_rich(
                "[dim]Searching in frontmost application (system-wide not fully implemented)...[/dim]",
                message_group=group_id,
            )

        # Strategy 0: Try identifier exact match first (HIGHEST PRIORITY)
        matches = []
        if identifier:
            emit_rich(
                f"[cyan]Trying identifier exact match: '{identifier}'...[/cyan]",
                message_group=group_id,
            )
            try:
                # Try with role filter if provided
                if role:
                    identifier_matches = app.findAllR(
                        AXRole=role, AXIdentifier=identifier
                    )
                else:
                    identifier_matches = app.findAllR(AXIdentifier=identifier)

                if identifier_matches:
                    emit_rich(
                        f"[green]✅ Found {len(identifier_matches)} identifier match(es)![/green]",
                        message_group=group_id,
                    )
                    matches = identifier_matches
            except Exception as e:
                # AXIdentifier might not be supported on all elements
                emit_rich(
                    f"[dim]Identifier search failed: {e}[/dim]",
                    message_group=group_id,
                )

        # Strategy 1: Try exact title match (if no identifier match)
        if not matches and title and role:
            # Exact match with both criteria
            try:
                exact_matches = app.findAllR(AXRole=role, AXTitle=title)
                if exact_matches:
                    emit_rich(
                        f"[green]Found {len(exact_matches)} exact match(es)[/green]",
                        message_group=group_id,
                    )
                    matches = exact_matches
            except Exception:
                pass

        # Strategy 2: If no exact match and fuzzy enabled, do fuzzy search
        if not matches and title and fuzzy:
            emit_rich(
                "[cyan]No exact match, trying fuzzy search...[/cyan]",
                message_group=group_id,
            )

            # Get all elements (filtered by role if provided)
            if role:
                all_elements = app.findAllR(AXRole=role)
            else:
                all_elements = app.findAllR()

            emit_rich(
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
                        # NEW: Comprehensive attribute support
                        "placeholder": getattr(elem, "AXPlaceholderValue", None) or "",
                        "help": getattr(elem, "AXHelp", None) or "",
                        "role_description": getattr(elem, "AXRoleDescription", None)
                        or "",
                        "identifier": getattr(elem, "AXIdentifier", None) or "",
                        "subrole": getattr(elem, "AXSubrole", None) or "",
                    }
                    element_dicts.append(elem_dict)
                except Exception:
                    continue

            # Perform fuzzy matching on ALL text attributes
            with monitor.measure("find_element_fuzzy_search"):
                fuzzy_matches = fuzzy_match(
                    search_text=title,
                    candidates=element_dicts,
                    attribute_names=[
                        "title",
                        "description",
                        "value",
                        "placeholder",
                        "help",
                        "role_description",  # NEW!
                    ],
                    threshold=fuzzy_threshold,
                    attribute_weights={
                        "title": 0.6,
                        "description": 0.3,
                        "placeholder": 0.4,  # High priority for text fields!
                        "value": 0.1,
                        "help": 0.2,
                        "role_description": 0.2,
                    },
                )

            if fuzzy_matches:
                # OPTIMIZATION: Early-stop on confident match
                top_score = fuzzy_matches[0][1] if fuzzy_matches else 0.0
                if top_score > early_stop_threshold:
                    monitor.record_early_stop()
                    emit_rich(
                        f"[green]✓ Early stop - confident match (score: {top_score:.2f} > {early_stop_threshold})[/green]",
                        message_group=group_id,
                    )
                else:
                    monitor.record_full_search()

                emit_rich(
                    f"[green]Found {len(fuzzy_matches)} fuzzy match(es)[/green]",
                    message_group=group_id,
                )

                # Show top 3 matches with scores
                for i, (elem_dict, score) in enumerate(fuzzy_matches[:3]):
                    explanation = explain_match(title, elem_dict["title"], score)
                    emit_rich(
                        f"  [{i + 1}] {elem_dict['role']} - '{elem_dict['title']}' (score: {score:.2f})",
                        message_group=group_id,
                    )
                    emit_rich(
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

        emit_rich(
            f"[green]Found {len(results)} matching element(s)[/green]",
            message_group=group_id,
        )

        # Show first few matches
        for i, (info, _) in enumerate(results[:3]):
            title_str = info.title or "(no title)"
            if info.center_x and info.center_y:
                emit_rich(
                    f"  [{i + 1}] {info.role} - '{title_str}' at ({info.center_x}, {info.center_y})",
                    message_group=group_id,
                )
            else:
                emit_rich(
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
