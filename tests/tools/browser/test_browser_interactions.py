"""Comprehensive tests for browser_interactions.py module.

Tests browser element interactions including clicking, typing, form manipulation,
hovering, and other user actions. Achieves 70%+ coverage.
"""

# Import the module directly to avoid circular imports
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "code_puppy"))

from tools.browser.browser_interactions import (
    check_element,
    click_element,
    double_click_element,
    get_element_text,
    get_element_value,
    hover_element,
    register_browser_check,
    register_browser_uncheck,
    register_click_element,
    register_double_click_element,
    register_get_element_text,
    register_get_element_value,
    register_hover_element,
    register_select_option,
    register_set_element_text,
    select_option,
    set_element_text,
    uncheck_element,
)


class BrowserInteractionsBaseTest:
    """Base test class with common mocking for browser interactions."""

    @pytest.fixture
    def mock_browser_manager(self):
        """Mock the camoufox manager and page."""
        manager = MagicMock()
        page = MagicMock()
        manager.get_current_page = AsyncMock(return_value=page)
        return manager, page

    @pytest.fixture
    def mock_locator(self):
        """Mock a Playwright locator with common interaction methods."""
        locator = AsyncMock()
        locator.wait_for = AsyncMock()
        locator.click = AsyncMock()
        locator.dblclick = AsyncMock()
        locator.hover = AsyncMock()
        locator.clear = AsyncMock()
        locator.fill = AsyncMock()
        locator.text_content = AsyncMock()
        locator.input_value = AsyncMock()
        locator.select_option = AsyncMock()
        locator.check = AsyncMock()
        locator.uncheck = AsyncMock()
        return locator

    @pytest.fixture
    def mock_context(self):
        """Mock RunContext for testing registration functions."""
        return MagicMock()


class TestClickElement(BrowserInteractionsBaseTest):
    """Test click_element function and its registration."""

    @pytest.mark.asyncio
    async def test_click_element_basic(self, mock_browser_manager, mock_locator):
        """Test basic element clicking."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await click_element("#submit-button")

            assert result["success"] is True
            assert result["selector"] == "#submit-button"
            assert result["action"] == "left_click"

            page.locator.assert_called_once_with("#submit-button")
            locator.wait_for.assert_called_once_with(state="visible", timeout=10000)
            locator.click.assert_called_once_with(
                force=False, button="left", timeout=10000
            )

    @pytest.mark.asyncio
    async def test_click_element_with_options(self, mock_browser_manager, mock_locator):
        """Test element clicking with custom options."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await click_element(
                selector="#custom-button",
                timeout=5000,
                force=True,
                button="right",
                modifiers=["Control", "Shift"],
            )

            assert result["success"] is True
            assert result["action"] == "right_click"

            locator.wait_for.assert_called_once_with(state="visible", timeout=5000)
            locator.click.assert_called_once_with(
                force=True, button="right", timeout=5000, modifiers=["Control", "Shift"]
            )

    @pytest.mark.asyncio
    async def test_click_element_no_page(self, mock_browser_manager):
        """Test behavior when no active page is available."""
        manager, page = mock_browser_manager
        manager.get_current_page.return_value = None

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            result = await click_element("#button")

            assert result["success"] is False
            assert "No active browser page available" in result["error"]

    @pytest.mark.asyncio
    async def test_click_element_exception(self, mock_browser_manager, mock_locator):
        """Test exception handling during click."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator
            locator.click.side_effect = Exception("Element not clickable")

            result = await click_element("#button")

            assert result["success"] is False
            assert "Element not clickable" in result["error"]
            assert result["selector"] == "#button"

    def test_register_click_element(self, mock_context):
        """Test registration of click_element tool."""
        agent = MagicMock()

        register_click_element(agent)

        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == "browser_click"


class TestDoubleClickElement(BrowserInteractionsBaseTest):
    """Test double_click_element function and its registration."""

    @pytest.mark.asyncio
    async def test_double_click_element_success(
        self, mock_browser_manager, mock_locator
    ):
        """Test successful double-click."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await double_click_element("#double-click-area")

            assert result["success"] is True
            assert result["action"] == "double_click"
            assert result["selector"] == "#double-click-area"

            locator.dblclick.assert_called_once_with(force=False, timeout=10000)

    @pytest.mark.asyncio
    async def test_double_click_element_with_force(
        self, mock_browser_manager, mock_locator
    ):
        """Test double-click with force option."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await double_click_element("#selector", timeout=3000, force=True)

            assert result["success"] is True
            locator.wait_for.assert_called_once_with(state="visible", timeout=3000)
            locator.dblclick.assert_called_once_with(force=True, timeout=3000)

    def test_register_double_click_element(self):
        """Test registration of double_click_element tool."""
        agent = MagicMock()

        register_double_click_element(agent)

        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == "browser_double_click"


class TestHoverElement(BrowserInteractionsBaseTest):
    """Test hover_element function and its registration."""

    @pytest.mark.asyncio
    async def test_hover_element_success(self, mock_browser_manager, mock_locator):
        """Test successful hover over element."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await hover_element("#hover-menu")

            assert result["success"] is True
            assert result["action"] == "hover"
            assert result["selector"] == "#hover-menu"

            locator.hover.assert_called_once_with(force=False, timeout=10000)

    @pytest.mark.asyncio
    async def test_hover_element_force_true(self, mock_browser_manager, mock_locator):
        """Test hover with force=True option."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await hover_element("#menu", timeout=2000, force=True)

            assert result["success"] is True
            locator.hover.assert_called_once_with(force=True, timeout=2000)

    def test_register_hover_element(self):
        """Test registration of hover_element tool."""
        agent = MagicMock()

        register_hover_element(agent)

        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == "browser_hover"


class TestSetElementText(BrowserInteractionsBaseTest):
    """Test set_element_text function and its registration."""

    @pytest.mark.asyncio
    async def test_set_element_text_clear_and_fill(
        self, mock_browser_manager, mock_locator
    ):
        """Test setting text with clear_first=True (default)."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await set_element_text("#input-field", "new text")

            assert result["success"] is True
            assert result["text"] == "new text"
            assert result["action"] == "set_text"

            locator.clear.assert_called_once_with(timeout=10000)
            locator.fill.assert_called_once_with("new text", timeout=10000)

    @pytest.mark.asyncio
    async def test_set_element_text_no_clear(self, mock_browser_manager, mock_locator):
        """Test setting text without clearing first."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await set_element_text("#input", "append text", clear_first=False)

            assert result["success"] is True
            locator.clear.assert_not_called()
            locator.fill.assert_called_once_with("append text", timeout=10000)

    @pytest.mark.asyncio
    async def test_set_element_text_exception(self, mock_browser_manager, mock_locator):
        """Test exception handling during text setting."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator
            locator.fill.side_effect = Exception("Input is read-only")

            result = await set_element_text("#readonly", "text")

            assert result["success"] is False
            assert "Input is read-only" in result["error"]
            assert result["text"] == "text"

    @pytest.mark.asyncio
    async def test_set_element_text_long_text(self, mock_browser_manager, mock_locator):
        """Test setting long text content."""
        manager, page = mock_browser_manager
        locator = mock_locator

        long_text = "a" * 1000  # Long text

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await set_element_text("#textarea", long_text)

            assert result["success"] is True
            assert result["text"] == long_text
            locator.fill.assert_called_once_with(long_text, timeout=10000)

    def test_register_set_element_text(self):
        """Test registration of set_element_text tool."""
        agent = MagicMock()

        register_set_element_text(agent)

        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == "browser_set_text"


class TestGetElementText(BrowserInteractionsBaseTest):
    """Test get_element_text function and its registration."""

    @pytest.mark.asyncio
    async def test_get_element_text_success(self, mock_browser_manager, mock_locator):
        """Test successful text retrieval."""
        manager, page = mock_browser_manager
        locator = mock_locator
        locator.text_content.return_value = "Element content"

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await get_element_text("#content", timeout=5000)

            assert result["success"] is True
            assert result["text"] == "Element content"
            assert result["selector"] == "#content"

            locator.wait_for.assert_called_once_with(state="visible", timeout=5000)
            locator.text_content.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_element_text_empty(self, mock_browser_manager, mock_locator):
        """Test retrieving empty text content."""
        manager, page = mock_browser_manager
        locator = mock_locator
        locator.text_content.return_value = ""

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await get_element_text("#empty")

            assert result["success"] is True
            assert result["text"] == ""

    @pytest.mark.asyncio
    async def test_get_element_text_none(self, mock_browser_manager, mock_locator):
        """Test retrieving None text content."""
        manager, page = mock_browser_manager
        locator = mock_locator
        locator.text_content.return_value = None

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await get_element_text("#None")

            assert result["success"] is True
            assert result["text"] is None

    def test_register_get_element_text(self):
        """Test registration of get_element_text tool."""
        agent = MagicMock()

        register_get_element_text(agent)

        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == "browser_get_text"


class TestGetElementValue(BrowserInteractionsBaseTest):
    """Test get_element_value function and its registration."""

    @pytest.mark.asyncio
    async def test_get_element_value_success(self, mock_browser_manager, mock_locator):
        """Test successful value retrieval from input."""
        manager, page = mock_browser_manager
        locator = mock_locator
        locator.input_value.return_value = "current value"

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await get_element_value("#input-field")

            assert result["success"] is True
            assert result["value"] == "current value"
            assert result["selector"] == "#input-field"

            locator.input_value.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_element_value_empty(self, mock_browser_manager, mock_locator):
        """Test retrieving empty input value."""
        manager, page = mock_browser_manager
        locator = mock_locator
        locator.input_value.return_value = ""

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await get_element_value("#empty-input")

            assert result["success"] is True
            assert result["value"] == ""

    @pytest.mark.asyncio
    async def test_get_element_value_exception(
        self, mock_browser_manager, mock_locator
    ):
        """Test exception during value retrieval."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator
            locator.input_value.side_effect = Exception("Element is not an input")

            result = await get_element_value("#not-input")

            assert result["success"] is False
            assert "Element is not an input" in result["error"]

    def test_register_get_element_value(self):
        """Test registration of get_element_value tool."""
        agent = MagicMock()

        register_get_element_value(agent)

        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == "browser_get_value"


class TestSelectOption(BrowserInteractionsBaseTest):
    """Test select_option function and its registration."""

    @pytest.mark.asyncio
    async def test_select_option_by_value(self, mock_browser_manager, mock_locator):
        """Test selecting option by value."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await select_option("#dropdown", value="option1")

            assert result["success"] is True
            assert result["selection"] == "option1"
            assert result["selector"] == "#dropdown"

            locator.select_option.assert_called_once_with(
                value="option1", timeout=10000
            )

    @pytest.mark.asyncio
    async def test_select_option_by_label(self, mock_browser_manager, mock_locator):
        """Test selecting option by label."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await select_option("#dropdown", label="Option Label")

            assert result["success"] is True
            assert result["selection"] == "Option Label"

            locator.select_option.assert_called_once_with(
                label="Option Label", timeout=10000
            )

    @pytest.mark.asyncio
    async def test_select_option_by_index(self, mock_browser_manager, mock_locator):
        """Test selecting option by index."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await select_option("#dropdown", index=2)

            assert result["success"] is True
            assert result["selection"] == "2"

            locator.select_option.assert_called_once_with(index=2, timeout=10000)

    @pytest.mark.asyncio
    async def test_select_option_no_selection_params(
        self, mock_browser_manager, mock_locator
    ):
        """Test select_option without any selection parameters."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await select_option("#dropdown")

            assert result["success"] is False
            assert "Must specify value, label, or index" in result["error"]
            assert result["selector"] == "#dropdown"

            # Should not call select_option
            locator.select_option.assert_not_called()

    @pytest.mark.asyncio
    async def test_select_option_exception(self, mock_browser_manager, mock_locator):
        """Test exception during option selection."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator
            locator.select_option.side_effect = Exception("Option not found")

            result = await select_option("#dropdown", value="nonexistent")

            assert result["success"] is False
            assert "Option not found" in result["error"]

    def test_register_select_option(self):
        """Test registration of select_option tool."""
        agent = MagicMock()

        register_select_option(agent)

        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == "browser_select_option"


class TestCheckElement(BrowserInteractionsBaseTest):
    """Test check_element function and its registration."""

    @pytest.mark.asyncio
    async def test_check_element_success(self, mock_browser_manager, mock_locator):
        """Test successful checkbox checking."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await check_element("#checkbox")

            assert result["success"] is True
            assert result["action"] == "check"
            assert result["selector"] == "#checkbox"

            locator.check.assert_called_once_with(timeout=10000)

    @pytest.mark.asyncio
    async def test_check_element_custom_timeout(
        self, mock_browser_manager, mock_locator
    ):
        """Test checking with custom timeout."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await check_element("#checkbox", timeout=5000)

            assert result["success"] is True
            locator.wait_for.assert_called_once_with(state="visible", timeout=5000)
            locator.check.assert_called_once_with(timeout=5000)

    @pytest.mark.asyncio
    async def test_check_element_exception(self, mock_browser_manager, mock_locator):
        """Test exception during checkbox checking."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator
            locator.check.side_effect = Exception("Not checkable")

            result = await check_element("#not-checkable")

            assert result["success"] is False
            assert "Not checkable" in result["error"]

    def test_register_browser_check(self):
        """Test registration of check_element tool."""
        agent = MagicMock()

        register_browser_check(agent)

        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == "browser_check"


class TestUncheckElement(BrowserInteractionsBaseTest):
    """Test uncheck_element function and its registration."""

    @pytest.mark.asyncio
    async def test_uncheck_element_success(self, mock_browser_manager, mock_locator):
        """Test successful checkbox unchecking."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            result = await uncheck_element("#checkbox")

            assert result["success"] is True
            assert result["action"] == "uncheck"
            assert result["selector"] == "#checkbox"

            locator.uncheck.assert_called_once_with(timeout=10000)

    @pytest.mark.asyncio
    async def test_uncheck_element_exception(self, mock_browser_manager, mock_locator):
        """Test exception during checkbox unchecking."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator
            locator.uncheck.side_effect = Exception("Not uncheckable")

            result = await uncheck_element("#not-uncheckable")

            assert result["success"] is False
            assert "Not uncheckable" in result["error"]

    def test_register_browser_uncheck(self):
        """Test registration of uncheck_element tool."""
        agent = MagicMock()

        register_browser_uncheck(agent)

        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == "browser_uncheck"


class TestIntegrationScenarios(BrowserInteractionsBaseTest):
    """Integration test scenarios combining multiple interaction functions."""

    @pytest.mark.asyncio
    async def test_form_interaction_workflow(self, mock_browser_manager, mock_locator):
        """Test complete form interaction workflow."""
        manager, page = mock_browser_manager
        locator = mock_locator

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            page.locator.return_value = locator

            # Simulate filling out a form
            text_result = await set_element_text("#username", "testuser")
            value_result = await get_element_value("#username")
            check_result = await check_element("#agree-terms")
            click_result = await click_element("#submit")

            # Verify all operations succeeded
            assert text_result["success"] is True
            assert value_result["success"] is True
            assert check_result["success"] is True
            assert click_result["success"] is True

            # Verify the sequence of calls
            assert page.locator.call_count == 4
            locator.fill.assert_called_once_with("testuser", timeout=10000)
            locator.input_value.assert_called_once()
            locator.check.assert_called_once()
            locator.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_dropdown_interaction_sequence(self, mock_browser_manager):
        """Test dropdown selection and interaction sequence."""
        manager, page = mock_browser_manager

        # Create separate locators for each call to ensure proper mock chain
        dropdown_locator1 = AsyncMock()
        dropdown_locator1.wait_for = AsyncMock()
        dropdown_locator1.select_option = AsyncMock()

        dropdown_locator2 = AsyncMock()
        dropdown_locator2.wait_for = AsyncMock()
        dropdown_locator2.select_option = AsyncMock()

        hover_locator = AsyncMock()
        hover_locator.wait_for = AsyncMock()
        hover_locator.hover = AsyncMock()

        # Configure page.locator to return different locators for different calls
        page.locator.side_effect = [
            dropdown_locator1,  # First select_option call
            dropdown_locator2,  # Second select_option call
            hover_locator,  # hover_element call
        ]

        with patch(
            "tools.browser.browser_interactions.get_camoufox_manager",
            return_value=manager,
        ):
            # Select by value then select by label
            select_result1 = await select_option("#dropdown", value="option1")
            select_result2 = await select_option("#dropdown", label="Another option")
            hover_result = await hover_element("#dropdown-menu")

            assert select_result1["success"] is True
            assert select_result2["success"] is True
            assert hover_result["success"] is True

            # Verify the wait_for and select_option chains were called correctly
            dropdown_locator1.wait_for.assert_called_once_with(
                state="visible", timeout=10000
            )
            dropdown_locator1.select_option.assert_called_once_with(
                value="option1", timeout=10000
            )

            dropdown_locator2.wait_for.assert_called_once_with(
                state="visible", timeout=10000
            )
            dropdown_locator2.select_option.assert_called_once_with(
                label="Another option", timeout=10000
            )

            hover_locator.wait_for.assert_called_once_with(
                state="visible", timeout=10000
            )
            hover_locator.hover.assert_called_once_with(force=False, timeout=10000)


if __name__ == "__main__":
    pytest.main([__file__])
