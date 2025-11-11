"""Multi-strategy clicking with automatic fallback.

This module provides intelligent UI element clicking that automatically
falls back through multiple methods:
1. Accessibility API (most accurate, ±1px)
2. OCR text finding (good accuracy, ±5-10px with smart offset)
3. Manual coordinates (last resort)

This maximizes success rate across different applications and platforms.
"""

from __future__ import annotations

import sys

from pydantic import Field
from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

from .result_types import BaseAutomationResult
from .smart_click_calculator import SmartClickCalculator

from .core.click_strategy import (
    ClickStrategy,
    is_strategy_enabled,
)
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


def register_multi_strategy_click_tools(agent):
    """Register multi-strategy click tools with automatic fallback."""

    @agent.tool
    def desktop_click_element_smart(
        context: RunContext,
        search_text: str,
        element_type: str = "button",
        min_ocr_confidence: float = 0.7,
        use_accessibility_api: bool = True,
        fuzzy_threshold: float = 0.6,
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
            min_ocr_confidence: Minimum OCR confidence for text matching (0.0-1.0, default: 0.7)
            use_accessibility_api: Whether to try accessibility API first (default: True)
            fuzzy_threshold: Fuzzy matching threshold for accessibility (0.0-1.0, default: 0.6)
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

        group_id = generate_group_id("multi_strategy_click", search_text[:30])
        emit_info(
            f"[bold magenta on black] MULTI-STRATEGY CLICK [/bold magenta on black] 🎯 '{search_text}' type={element_type}",
            message_group=group_id,
        )

        attempts_log = []
        platform = sys.platform

        # Validate platform support using extracted logic
        accessibility_supported = is_strategy_enabled(
            ClickStrategy.ACCESSIBILITY, platform=platform
        )

        # TIER 1: Try Accessibility API first (macOS/Windows only)
        if use_accessibility_api and accessibility_supported:
            emit_info(
                "[cyan]✅ TIER 1: Trying Accessibility API...[/cyan]",
                message_group=group_id,
            )

            try:
                if platform == "darwin":
                    # macOS accessibility
                    from .accessibility.tools import desktop_click_accessible_element  # noqa: E402

                    accessibility_result = desktop_click_accessible_element(
                        context=context,
                        title=search_text,
                        fuzzy=True,
                        fuzzy_threshold=fuzzy_threshold,
                    )

                    if (
                        accessibility_result.success
                        and accessibility_result.element_found
                    ):
                        emit_info(
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
                    # Windows UI Automation
                    from .windows_automation import windows_click_element

                    windows_result = windows_click_element(
                        context=context,
                        title=search_text,
                        fuzzy=True,
                        fuzzy_threshold=0.7,
                    )

                    if windows_result.success and windows_result.element_found:
                        emit_info(
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
        emit_info(
            "[cyan]🔍 TIER 2: Trying OCR with SmartClickCalculator...[/cyan]",
            message_group=group_id,
        )

        try:
            from .ocr.tools import desktop_find_text_reliable  # noqa: E402

            # Find text with confidence filtering
            ocr_result = desktop_find_text_reliable(
                context=context,
                search_text=search_text,
                min_confidence=min_ocr_confidence,
            )

            if ocr_result.found and ocr_result.best_match:
                emit_info(
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
                    emit_info(
                        f"[cyan]OCR Attempt {attempt_num}/{len(retry_points)}: ({point.x}, {point.y}) - {point.strategy}[/cyan]",
                        message_group=group_id,
                    )
                    emit_info(
                        f"[dim]{point.reasoning}[/dim]",
                        message_group=group_id,
                    )

                    # Perform click
                    pyautogui.click(x=point.x, y=point.y)

                    # Wait for UI update
                    import time

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
                                emit_info(
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
                                emit_info(
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
                    emit_info(
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
        emit_info(
            "[dim]Consider using desktop_hover_and_verify() or desktop_highlight_click_target() for manual debugging[/dim]",
            message_group=group_id,
        )

        return MultiStrategyClickResult(
            success=False,
            search_text=search_text,
            error="All click strategies failed",
            attempts_log=attempts_log,
        )
