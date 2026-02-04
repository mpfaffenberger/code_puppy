"""Multi-strategy clicking with automatic fallback.

This module provides intelligent UI element clicking that automatically
falls back through multiple methods:
1. Accessibility API (most accurate, ±1px)
2. OCR text finding (good accuracy, ±5-10px with smart offset)
3. Manual coordinates (last resort)

This maximizes success rate across different applications and platforms.

PLATFORM-SPECIFIC THRESHOLD NOTES:
==================================

OCR Confidence (min_ocr_confidence):
- macOS (Vision Framework): Reports 0.3-0.6 for clean UI text (internal model scores,
  NOT calibrated probabilities). Use 0.25-0.5 threshold.
- Windows (WinRT OCR): Always returns 1.0 (no confidence scores available).
  Threshold is effectively ignored but kept for API consistency.

Fuzzy Matching (fuzzy_threshold):
- macOS (atomacos): Uses AXTitle/AXDescription matching. Default 0.6 works well.
- Windows (UI Automation): Uses Name/AutomationId/Value matching. Slightly higher
  threshold (0.7) recommended due to different text normalization.

The defaults are tuned for cross-platform compatibility. Adjust per-platform
if needed for specific applications.
"""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING, Any

from pydantic import Field
from pydantic_ai import RunContext

if TYPE_CHECKING:
    from pydantic_ai import Agent
from code_puppy.messaging import emit_error, emit_warning
from .rich_emit import emit_rich
from code_puppy.tools.common import generate_group_id

from .result_types import BaseAutomationResult
from .smart_click_calculator import SmartClickCalculator
from .platform_defaults import get_default_ocr_confidence, get_default_fuzzy_threshold

from .dependencies import PYAUTOGUI_AVAILABLE

if PYAUTOGUI_AVAILABLE:
    import pyautogui
else:
    pyautogui = None


class MultiStrategyClickResult(BaseAutomationResult):
    """Result from multi-strategy click attempt."""

    search_text: str = ""
    successful_method: str | None = Field(
        None,
        description="Method that succeeded (accessibility, ocr, manual)",
    )
    click_x: int = 0
    click_y: int = 0
    attempts_log: list[str] = Field(
        default_factory=list,
        description="Log of all methods attempted",
    )
    ocr_confidence: float | None = None
    offset_used: tuple[int, int] | None = None


def register_multi_strategy_click_tools(agent: "Agent[Any, Any]") -> None:
    """Register multi-strategy click tools with automatic fallback."""
    # Guard against double registration
    marker = "_gui_cub_multi_strategy_click_tools_registered"
    if getattr(agent, marker, False):
        return
    setattr(agent, marker, True)

    @agent.tool
    def desktop_click_element_smart(
        context: RunContext,
        search_text: str,
        element_type: str = "button",
        min_ocr_confidence: float | None = None,
        use_accessibility_api: bool = True,
        fuzzy_threshold: float | None = None,
        max_ocr_retries: int = 3,
        verify_click: bool = True,
        verify_text: str | None = None,
    ) -> MultiStrategyClickResult:
        """
        Intelligent multi-strategy clicking with automatic fallback.

        This is the ULTIMATE click tool! It tries multiple methods automatically:

        **TIER 1: Accessibility API** (±1px accuracy)
        - macOS: Uses atomacos with fuzzy matching
        - Windows: Uses UI Automation


        **TIER 2: OCR with Smart Offset** (±5-10px accuracy)
        - Uses desktop_find_text_reliable() with confidence filtering
        - Applies SmartClickCalculator offset correction
        - Retries with multiple offsets if needed

        **TIER 3: Manual Coordinates** (requires user input)
        - Falls back to user-provided coordinates
        - Only if other methods fail

        Args:
            search_text: Text to find and click (button label, link text, etc.)
            element_type: Type of element - one of:
                         "button", "link", "checkbox", "radio_button",
                         "text_field", "dropdown", "icon", "menu_item", "tab", "generic"
            min_ocr_confidence: Minimum OCR confidence for text matching (0.0-1.0).
                               Default: None (uses platform default: 0.5 on both platforms)
                               Platform notes:
                               - macOS (Vision): Uses internal scores (0.3-0.6 typical)
                               - Windows (WinRT): Always returns 1.0, threshold ignored
            use_accessibility_api: Whether to try accessibility API first (default: True)
            fuzzy_threshold: Fuzzy matching threshold for accessibility (0.0-1.0).
                            Default: None (uses platform default: 0.6 macOS, 0.7 Windows)
            max_ocr_retries: Maximum OCR click attempts with different offsets (default: 3)
            verify_click: Whether to verify click success by checking if element disappeared
            verify_text: Optional text to verify after clicking (e.g., "Success", "Saved")

        Returns:
            MultiStrategyClickResult with details of successful method

        Examples:
            # Simple button click (tries all methods automatically)
            result = desktop_click_element_smart(search_text="Submit")

            # Link click with verification
            result = desktop_click_element_smart(
                search_text="Learn More",
                element_type="link",
                verify_text="Welcome"
            )

            # Checkbox with high confidence requirement
            result = desktop_click_element_smart(
                search_text="I agree",
                element_type="checkbox",
                min_ocr_confidence=0.8
            )

            # Skip accessibility API (OCR only)
            result = desktop_click_element_smart(
                search_text="OK",
                use_accessibility_api=False
            )
        """
        if not PYAUTOGUI_AVAILABLE:
            return MultiStrategyClickResult(
                success=False,
                error="PyAutoGUI not available",
                search_text=search_text,
            )

        # Apply platform-specific defaults if not explicitly provided
        if min_ocr_confidence is None:
            min_ocr_confidence = get_default_ocr_confidence()
        if fuzzy_threshold is None:
            fuzzy_threshold = get_default_fuzzy_threshold()

        group_id = generate_group_id("multi_strategy_click", search_text[:30])
        emit_rich(
            f"[bold magenta on black] MULTI-STRATEGY CLICK [/bold magenta on black] 🎯 '{search_text}' type={element_type}",
            message_group=group_id,
        )

        attempts_log = []
        platform = sys.platform

        # Check if accessibility API is supported on this platform
        # Accessibility is only available on macOS and Windows
        accessibility_supported = platform in ("darwin", "win32")

        # TIER 1: Try Accessibility API first (macOS/Windows only)
        if use_accessibility_api and accessibility_supported:
            emit_rich(
                "[cyan]✅ TIER 1: Trying Accessibility API...[/cyan]",
                message_group=group_id,
            )

            try:
                if platform == "darwin":
                    # macOS accessibility via atomacos
                    # Uses AXTitle/AXDescription matching
                    # Platform default (0.6) is tuned for macOS - see platform_defaults.py
                    from .accessibility.tools import desktop_click_accessible_element  # noqa: E402

                    accessibility_result = desktop_click_accessible_element(
                        context=context,
                        title=search_text,
                        fuzzy=True,
                        fuzzy_threshold=fuzzy_threshold,  # Uses platform default (0.6) or user override
                    )

                    if (
                        accessibility_result.success
                        and accessibility_result.element_found
                    ):
                        emit_rich(
                            f"[bold green]✅ SUCCESS via Accessibility API! Clicked at ({accessibility_result.click_x}, {accessibility_result.click_y})[/bold green]",
                            message_group=group_id,
                        )
                        attempts_log.append(
                            f"Accessibility API: SUCCESS at ({accessibility_result.click_x}, {accessibility_result.click_y})"
                        )

                        return MultiStrategyClickResult(
                            success=True,
                            search_text=search_text,
                            successful_method="accessibility",
                            click_x=accessibility_result.click_x or 0,
                            click_y=accessibility_result.click_y or 0,
                            attempts_log=attempts_log,
                        )
                    else:
                        attempts_log.append(
                            f"Accessibility API: FAILED - {accessibility_result.error or 'Element not found'}"
                        )
                        emit_warning(
                            f"[yellow]Accessibility API failed: {accessibility_result.error or 'Element not found'}[/yellow]",
                            message_group=group_id,
                        )

                elif platform == "win32":
                    # Windows UI Automation via pywinauto
                    # Uses Name/AutomationId/Value matching
                    # Platform default (0.7) is higher than macOS (0.6) due to
                    # different text normalization - see platform_defaults.py
                    from .windows_automation import click_element as _win_click

                    windows_result = _win_click(
                        title=search_text,
                        fuzzy=True,
                        fuzzy_threshold=fuzzy_threshold,  # Uses platform default (0.7) or user override
                    )

                    if windows_result.success and windows_result.clicked:
                        emit_rich(
                            "[bold green]✅ SUCCESS via Windows UI Automation![/bold green]",
                            message_group=group_id,
                        )
                        attempts_log.append("Windows UI Automation: SUCCESS")

                        return MultiStrategyClickResult(
                            success=True,
                            search_text=search_text,
                            successful_method="accessibility",
                            click_x=0,
                            click_y=0,
                            attempts_log=attempts_log,
                        )
                    else:
                        attempts_log.append(
                            f"Windows UI Automation: FAILED - {windows_result.error or 'Element not found'}"
                        )
                        emit_warning(
                            f"[yellow]Windows UI Automation failed: {windows_result.error or 'Element not found'}[/yellow]",
                            message_group=group_id,
                        )

            except Exception as e:
                attempts_log.append(f"Accessibility API: EXCEPTION - {e}")
                emit_warning(
                    f"[yellow]Accessibility API exception: {e}[/yellow]",
                    message_group=group_id,
                )
        else:
            if not use_accessibility_api:
                attempts_log.append("Accessibility API: SKIPPED (disabled)")
            else:
                attempts_log.append(f"Accessibility API: SKIPPED (platform={platform})")

        # TIER 2: Try OCR with Smart Offset
        # See platform_defaults.py for OCR confidence threshold details:
        # - macOS (Vision Framework): Returns 0.3-0.6 for clean text
        # - Windows (WinRT): Always returns 1.0, threshold ignored
        emit_rich(
            "[cyan]🔍 TIER 2: Trying OCR with SmartClickCalculator...[/cyan]",
            message_group=group_id,
        )

        try:
            # Use OCR tool layer (proper abstraction)
            from .ocr.tools import desktop_find_text_reliable  # noqa: E402

            # Find text with confidence filtering
            # Uses platform default (0.5) or user override - see platform_defaults.py
            ocr_result = desktop_find_text_reliable(
                context=context,
                search_text=search_text,
                min_confidence=min_ocr_confidence,
            )

            if ocr_result.found and ocr_result.best_match:
                emit_rich(
                    f"[green]OCR found '{search_text}' with confidence {ocr_result.best_match.confidence:.2f}[/green]",
                    message_group=group_id,
                )

                # Use SmartClickCalculator to get optimal click points
                retry_points = SmartClickCalculator.generate_retry_points(
                    bbox=ocr_result.best_match,
                    element_type=element_type,  # type: ignore
                    num_points=max_ocr_retries,
                )

                # Try each click point
                for attempt_num, point in enumerate(retry_points, 1):
                    emit_rich(
                        f"[cyan]OCR Attempt {attempt_num}/{len(retry_points)}: ({point.x}, {point.y}) - {point.strategy}[/cyan]",
                        message_group=group_id,
                    )
                    emit_rich(
                        f"[dim]{point.reasoning}[/dim]",
                        message_group=group_id,
                    )

                    # Perform click using native API (multi-monitor safe)
                    from .platform import click_mouse_native

                    click_success, click_error = click_mouse_native(
                        x=point.x, y=point.y, button="left", clicks=1
                    )
                    if not click_success:
                        emit_error(
                            f"[red]Native click failed: {click_error}[/red]",
                            message_group=group_id,
                        )
                        # Continue anyway - the click might have partially worked

                    # Wait for UI update
                    time.sleep(0.3)

                    # Verify if requested
                    if verify_click or verify_text:
                        # Check if element disappeared (common success pattern)
                        if verify_click:
                            from .ocr.tools import desktop_find_text  # noqa: E402

                            verify_result = desktop_find_text(
                                context=context,
                                search_text=search_text,
                            )
                            if not verify_result.found:
                                emit_rich(
                                    f"[bold green]✅ SUCCESS via OCR! Element '{search_text}' disappeared after click.[/bold green]",
                                    message_group=group_id,
                                )
                                attempts_log.append(
                                    f"OCR Attempt {attempt_num}: SUCCESS - Element disappeared"
                                )
                                return MultiStrategyClickResult(
                                    success=True,
                                    search_text=search_text,
                                    successful_method="ocr",
                                    click_x=point.x,
                                    click_y=point.y,
                                    attempts_log=attempts_log,
                                    ocr_confidence=ocr_result.best_match.confidence,
                                    offset_used=(point.offset_x, point.offset_y),
                                )

                        # Check for verification text
                        if verify_text:
                            from .ocr.tools import desktop_find_text  # noqa: E402

                            verify_result = desktop_find_text(
                                context=context,
                                search_text=verify_text,
                            )
                            if verify_result.found:
                                emit_rich(
                                    f"[bold green]✅ SUCCESS via OCR! Verification text '{verify_text}' appeared.[/bold green]",
                                    message_group=group_id,
                                )
                                attempts_log.append(
                                    f"OCR Attempt {attempt_num}: SUCCESS - Verification text appeared"
                                )
                                return MultiStrategyClickResult(
                                    success=True,
                                    search_text=search_text,
                                    successful_method="ocr",
                                    click_x=point.x,
                                    click_y=point.y,
                                    attempts_log=attempts_log,
                                    ocr_confidence=ocr_result.best_match.confidence,
                                    offset_used=(point.offset_x, point.offset_y),
                                )

                    attempts_log.append(
                        f"OCR Attempt {attempt_num}: Clicked but verification inconclusive"
                    )

                # If no verification was requested, assume first click worked
                if not verify_click and not verify_text:
                    emit_rich(
                        f"[green]✅ Clicked via OCR at ({retry_points[0].x}, {retry_points[0].y}) (no verification requested)[/green]",
                        message_group=group_id,
                    )
                    return MultiStrategyClickResult(
                        success=True,
                        search_text=search_text,
                        successful_method="ocr",
                        click_x=retry_points[0].x,
                        click_y=retry_points[0].y,
                        attempts_log=attempts_log,
                        ocr_confidence=ocr_result.best_match.confidence,
                        offset_used=(
                            retry_points[0].offset_x,
                            retry_points[0].offset_y,
                        ),
                    )

                # All OCR attempts failed verification
                emit_warning(
                    "[yellow]OCR clicks completed but verification failed[/yellow]",
                    message_group=group_id,
                )
                attempts_log.append("OCR: All attempts failed verification")

            else:
                attempts_log.append(
                    f"OCR: Text not found or low confidence (< {min_ocr_confidence})"
                )
                emit_warning(
                    f"[yellow]OCR failed: {ocr_result.error or 'Text not found'}[/yellow]",
                    message_group=group_id,
                )

        except Exception as e:
            attempts_log.append(f"OCR: EXCEPTION - {e}")
            emit_warning(
                f"[yellow]OCR exception: {e}[/yellow]",
                message_group=group_id,
            )

        # TIER 3: All methods failed
        emit_error(
            "[red]❌ All click strategies FAILED![/red]",
            message_group=group_id,
        )
        emit_rich(
            "[dim]Consider using desktop_hover_and_verify() or desktop_highlight_click_target() for manual debugging[/dim]",
            message_group=group_id,
        )

        return MultiStrategyClickResult(
            success=False,
            search_text=search_text,
            error="All click strategies failed",
            attempts_log=attempts_log,
        )
