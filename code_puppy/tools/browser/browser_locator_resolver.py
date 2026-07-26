"""Shared Playwright semantic-locator resolution.

Centralizes role/text/label/placeholder/test-id -> Playwright locator
construction so the semantic discovery *and* action tools don't each
reinvent it (DRY). Non-visual QA progression should lean on these
accessibility-first locators instead of raw CSS/XPath or screenshots.
"""

from typing import Optional

# Supported semantic strategies. The value documents which Playwright
# ``page.get_by_*`` accessor backs each strategy.
SEMANTIC_STRATEGIES: dict[str, str] = {
    "role": "get_by_role",
    "text": "get_by_text",
    "label": "get_by_label",
    "placeholder": "get_by_placeholder",
    "test_id": "get_by_test_id",
}


def describe_target(strategy: str, value: str, name: Optional[str] = None) -> str:
    """Human-readable description of a semantic target for diagnostics.

    Keeps error messages deterministic and consistent across every tool
    that resolves a locator.
    """
    if strategy == "role" and name:
        return f"role={value!r} name={name!r}"
    return f"{strategy}={value!r}"


def resolve_locator(
    page,
    strategy: str,
    value: str,
    name: Optional[str] = None,
    exact: bool = False,
):
    """Build a Playwright locator for a semantic strategy.

    Args:
        page: The active Playwright page.
        strategy: One of :data:`SEMANTIC_STRATEGIES` keys.
        value: The primary value (role name, text, label, placeholder, test id).
        name: Accessible name, only used with the ``role`` strategy.
        exact: Whether to match ``value``/``name`` exactly.

    Returns:
        A Playwright locator.

    Raises:
        ValueError: If ``strategy`` is not supported.
    """
    if strategy not in SEMANTIC_STRATEGIES:
        supported = ", ".join(sorted(SEMANTIC_STRATEGIES))
        raise ValueError(
            f"Unknown locator strategy {strategy!r}. Expected one of: {supported}"
        )

    if strategy == "role":
        return page.get_by_role(value, name=name, exact=exact)
    if strategy == "text":
        return page.get_by_text(value, exact=exact)
    if strategy == "label":
        return page.get_by_label(value, exact=exact)
    if strategy == "placeholder":
        return page.get_by_placeholder(value, exact=exact)
    # test_id has no exact/name knobs in Playwright's accessor.
    return page.get_by_test_id(value)
