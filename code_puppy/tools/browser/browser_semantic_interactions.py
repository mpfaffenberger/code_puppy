"""Semantic (accessibility-locator) interaction helpers.

These let qa-kitten act *directly* through Playwright semantic locators
(role/text/label) instead of first discovering an element and then
translating it into a raw CSS/XPath selector. This is the preferred path
for non-visual workflow progression: fewer round-trips, no fragile
selectors, deterministic errors when nothing matches.
"""

from typing import Any, Dict, Optional

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.common import generate_group_id

from .browser_locator_resolver import describe_target, resolve_locator
from .browser_manager import get_session_browser_manager


async def _act_on_semantic(
    strategy: str,
    value: str,
    action: str,
    name: Optional[str] = None,
    exact: bool = False,
    text: Optional[str] = None,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Resolve a semantic locator and perform an action on the first match.

    Shared core for every semantic interaction so click/fill/check don't
    duplicate the resolve-wait-act-diagnose dance (DRY).
    """
    target = describe_target(strategy, value, name)
    group_id = generate_group_id(f"browser_{action}_by_{strategy}", target)
    emit_info(
        f"BROWSER {action.upper()} BY {strategy.upper()}  {target}",
        message_group=group_id,
    )
    try:
        browser_manager = get_session_browser_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        try:
            locator = resolve_locator(page, strategy, value, name=name, exact=exact)
        except ValueError as ve:
            return {"success": False, "error": str(ve)}

        element = locator.first

        # Deterministic "no match" error instead of a raw Playwright timeout.
        if await locator.count() == 0:
            msg = f"No element matched {target}"
            emit_error(msg, message_group=group_id)
            return {"success": False, "error": msg, "target": target}

        await element.wait_for(state="visible", timeout=timeout)

        if action == "click":
            await element.click(timeout=timeout)
        elif action == "fill":
            await element.fill(text or "", timeout=timeout)
        elif action == "check":
            await element.check(timeout=timeout)
        else:  # pragma: no cover - guarded by callers
            return {"success": False, "error": f"Unknown action {action!r}"}

        emit_success(f"{action} on {target}", message_group=group_id)
        result: Dict[str, Any] = {
            "success": True,
            "action": action,
            "strategy": strategy,
            "target": target,
        }
        if text is not None:
            result["text"] = text
        return result

    except Exception as e:
        emit_error(f"{action} failed: {str(e)}", message_group=group_id)
        return {"success": False, "error": str(e), "target": target}


async def click_by_role(
    role: str, name: Optional[str] = None, exact: bool = False, timeout: int = 10000
) -> Dict[str, Any]:
    """Click the first element matching an ARIA role (and optional name)."""
    return await _act_on_semantic(
        "role", role, "click", name=name, exact=exact, timeout=timeout
    )


async def click_by_text(
    text: str, exact: bool = False, timeout: int = 10000
) -> Dict[str, Any]:
    """Click the first element containing the given visible text."""
    return await _act_on_semantic("text", text, "click", exact=exact, timeout=timeout)


async def set_text_by_label(
    label: str, text: str, exact: bool = False, timeout: int = 10000
) -> Dict[str, Any]:
    """Fill the input associated with the given label text."""
    return await _act_on_semantic(
        "label", label, "fill", exact=exact, text=text, timeout=timeout
    )


def register_click_by_role(agent):
    """Register the click-by-role semantic tool."""

    @agent.tool
    async def browser_click_by_role(
        context: RunContext,
        role: str,
        name: Optional[str] = None,
        exact: bool = False,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Click an element by ARIA role (accessibility-first, PREFERRED for
        non-visual progression). No need to discover a selector first.

        Args:
            role: ARIA role (button, link, tab, menuitem, etc.).
            name: Optional accessible name to disambiguate.
            exact: Match name exactly.
            timeout: Timeout in milliseconds.

        Returns:
            Dict with action result or a deterministic no-match error.
        """
        return await click_by_role(role, name=name, exact=exact, timeout=timeout)


def register_click_by_text(agent):
    """Register the click-by-text semantic tool."""

    @agent.tool
    async def browser_click_by_text(
        context: RunContext,
        text: str,
        exact: bool = False,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Click an element by its visible text (PREFERRED for non-visual
        progression over screenshot-guided clicking).

        Args:
            text: Visible text to match.
            exact: Match text exactly.
            timeout: Timeout in milliseconds.

        Returns:
            Dict with action result or a deterministic no-match error.
        """
        return await click_by_text(text, exact=exact, timeout=timeout)


def register_set_text_by_label(agent):
    """Register the fill-by-label semantic tool."""

    @agent.tool
    async def browser_set_text_by_label(
        context: RunContext,
        label: str,
        text: str,
        exact: bool = False,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Type text into the input associated with a label (accessibility-first,
        PREFERRED for non-visual form progression).

        Args:
            label: Label text of the target input.
            text: Text to enter.
            exact: Match label exactly.
            timeout: Timeout in milliseconds.

        Returns:
            Dict with action result or a deterministic no-match error.
        """
        return await set_text_by_label(label, text, exact=exact, timeout=timeout)
