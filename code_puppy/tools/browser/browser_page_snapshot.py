"""Cheap structured page-state snapshot for DOM-first QA progression.

Instead of taking a screenshot and visually reasoning about "did the
action work", qa-kitten can call ``browser_page_snapshot`` to get a
compact, deterministic view of the page: URL, title, headings, buttons
(with accessible names), links, inputs, and key ARIA metadata. This is
faster, cheaper, and immune to window moves / monitor differences.

Screenshots remain the right tool for *visual* assertions (layout,
color, occlusion, visual diff) - this is for functional progression.
"""

from typing import Any, Dict

from pydantic_ai import RunContext

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.common import generate_group_id

from .browser_manager import get_session_browser_manager

# One JS pass gathers everything so we make a single round-trip to the
# page rather than N Playwright calls. ``limit`` caps each collection so
# huge pages don't blow up the tool output.
_SNAPSHOT_JS = """
(limit) => {
  const isVisible = (el) => {
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const accName = (el) =>
    (el.getAttribute('aria-label')
      || el.getAttribute('title')
      || (el.textContent || '').trim()
      || el.getAttribute('value')
      || '').slice(0, 120);
  const take = (nodes) => Array.from(nodes).filter(isVisible).slice(0, limit);

  const headings = take(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).map((el) => ({
    level: el.tagName.toLowerCase(),
    text: (el.textContent || '').trim().slice(0, 120),
  }));
  const buttons = take(
    document.querySelectorAll('button,[role="button"],input[type="submit"],input[type="button"]')
  ).map((el) => ({
    name: accName(el),
    disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
  }));
  const links = take(document.querySelectorAll('a[href]')).map((el) => ({
    text: (el.textContent || '').trim().slice(0, 120),
    href: el.getAttribute('href'),
  }));
  const inputs = take(
    document.querySelectorAll('input,textarea,select')
  ).map((el) => ({
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type'),
    name: el.getAttribute('name'),
    placeholder: el.getAttribute('placeholder'),
    label: el.getAttribute('aria-label'),
    test_id: el.getAttribute('data-testid') || el.getAttribute('data-test-id'),
    value: (el.value || '').slice(0, 120),
    checked: el.checked === true,
  }));
  const landmarks = take(
    document.querySelectorAll('[role],nav,main,header,footer,aside,form')
  ).map((el) => ({
    role: el.getAttribute('role') || el.tagName.toLowerCase(),
    label: el.getAttribute('aria-label'),
  }));

  const bodyText = (document.body ? document.body.innerText : '') || '';
  return {
    url: window.location.href,
    title: document.title,
    visible_text: bodyText.replace(/\\s+/g, ' ').trim().slice(0, 2000),
    headings,
    buttons,
    links,
    inputs,
    landmarks,
  };
}
"""


async def get_page_snapshot(limit: int = 25) -> Dict[str, Any]:
    """Return a compact structured snapshot of the current page state.

    Args:
        limit: Max items collected per category (buttons, links, inputs...).

    Returns:
        Dict with ``success`` plus URL/title/visible_text and structured
        lists of headings, buttons, links, inputs, and landmarks, or an
        error dict if no page is available.
    """
    group_id = generate_group_id("browser_page_snapshot", "snapshot")
    emit_info("BROWSER PAGE SNAPSHOT  gathering DOM state", message_group=group_id)
    try:
        browser_manager = get_session_browser_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        snapshot = await page.evaluate(_SNAPSHOT_JS, limit)

        emit_success(
            "Snapshot: "
            f"{len(snapshot.get('buttons', []))} buttons, "
            f"{len(snapshot.get('links', []))} links, "
            f"{len(snapshot.get('inputs', []))} inputs",
            message_group=group_id,
        )

        return {"success": True, **snapshot}

    except Exception as e:
        return {"success": False, "error": str(e)}


def register_get_page_snapshot(agent):
    """Register the page snapshot tool."""

    @agent.tool
    async def browser_page_snapshot(
        context: RunContext,
        limit: int = 25,
    ) -> Dict[str, Any]:
        """
        Get a cheap, structured snapshot of the current page's DOM state.

        PREFER THIS over a screenshot when validating functional progression
        (did the page change / did the element appear / what's the value now).
        Returns URL, title, visible text excerpt, headings, buttons with
        accessible names, links, inputs (with values/placeholders/test-ids),
        and ARIA landmarks. Reserve screenshots for true visual assertions.

        Args:
            limit: Max items per category (buttons/links/inputs/etc).

        Returns:
            Dict with structured page state, or an error dict.
        """
        return await get_page_snapshot(limit=limit)
