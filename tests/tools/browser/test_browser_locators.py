"""Comprehensive tests for browser_locators.py module.

Tests element locator strategies — role/text/label/placeholder/test-id lookups,
XPath queries, button and link enumeration — plus every no-active-page and
exception branch. The shared ``get_by_*`` family is table-driven; the link and
button tests keep their distinct filter assertions.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.browser_locators import (
    find_buttons,
    find_by_label,
    find_by_placeholder,
    find_by_role,
    find_by_test_id,
    find_by_text,
    find_links,
    register_find_buttons,
    register_find_by_label,
    register_find_by_placeholder,
    register_find_by_role,
    register_find_by_test_id,
    register_find_by_text,
    register_find_links,
    register_run_xpath_query,
    run_xpath_query,
)

MOD = "code_puppy.tools.browser.browser_locators"


@contextmanager
def _mgr(manager):
    with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
        yield


class BrowserLocatorsBaseTest:
    """Base fixtures for mocking the browser manager, page and locator."""

    @pytest.fixture
    def mock_browser_manager(self):
        manager = AsyncMock()
        page = AsyncMock()
        page.get_by_role = MagicMock()
        page.get_by_text = MagicMock()
        page.get_by_label = MagicMock()
        page.get_by_placeholder = MagicMock()
        page.get_by_test_id = MagicMock()
        page.locator = MagicMock()
        manager.get_current_page.return_value = page
        return manager, page

    @pytest.fixture
    def mock_locator(self):
        locator = AsyncMock()
        first_mock = MagicMock()
        first_mock.wait_for = AsyncMock()
        locator.first = first_mock
        locator.count = AsyncMock(return_value=1)
        locator.nth = MagicMock()
        element = MagicMock()
        element.is_visible = AsyncMock(return_value=True)
        element.text_content = AsyncMock(return_value="Test Content")
        element.evaluate = AsyncMock(return_value="div")
        element.get_attribute = AsyncMock(return_value=None)
        element.input_value = AsyncMock(return_value="test value")
        locator.nth.return_value = element
        return locator, element


# Shared get_by_* family table: role / text / label / placeholder / test-id.
#   fn, query, call_kwargs   -> operation invocation
#   page_attr, page_call     -> mocked page accessor + expected call
#   wait_timeout             -> expected wait_for() timeout
#   setup                    -> element method return-values to configure
#   result, checks           -> expected result dict / element dict fields
GET_BY = [
    {
        "name": "role",
        "fn": find_by_role,
        "query": "button",
        "call_kwargs": {"name": "Submit", "exact": False, "timeout": 5000},
        "page_attr": "get_by_role",
        "page_call": (("button",), {"name": "Submit", "exact": False}),
        "wait_timeout": 5000,
        "result": {"role": "button", "name": "Submit", "count": 1},
        "checks": [("text", "Test Content"), ("visible", True)],
    },
    {
        "name": "text",
        "fn": find_by_text,
        "query": "Click me",
        "call_kwargs": {"exact": False, "timeout": 3000},
        "page_attr": "get_by_text",
        "page_call": (("Click me",), {"exact": False}),
        "wait_timeout": 3000,
        "result": {"search_text": "Click me", "exact": False, "count": 1},
    },
    {
        "name": "label",
        "fn": find_by_label,
        "query": "Username",
        "page_attr": "get_by_label",
        "page_call": (("Username",), {"exact": False}),
        "setup": {
            "evaluate": "input",
            "get_attribute": "text",
            "input_value": "user input",
        },
        "result": {"label_text": "Username", "count": 1},
        "checks": [("tag", "input"), ("type", "text"), ("value", "user input")],
    },
    {
        "name": "placeholder",
        "fn": find_by_placeholder,
        "query": "Enter your email",
        "page_attr": "get_by_placeholder",
        "page_call": (("Enter your email",), {"exact": False}),
        "setup": {
            "get_attribute": "Enter your email",
            "input_value": "test@example.com",
        },
        "result": {"placeholder_text": "Enter your email", "count": 1},
        "checks": [("placeholder", "Enter your email"), ("value", "test@example.com")],
    },
    {
        "name": "test_id",
        "fn": find_by_test_id,
        "query": "submit-button",
        "page_attr": "get_by_test_id",
        "page_call": (("submit-button",), {}),
        "result": {"test_id": "submit-button", "count": 1},
        "checks": [("test_id", "submit-button")],
    },
]

# All locator entry points (for no-active-page + exception branches).
LOCATOR_OPS = [
    ("role", find_by_role, ("button",), "get_by_role"),
    ("text", find_by_text, ("hello",), "get_by_text"),
    ("label", find_by_label, ("email",), "get_by_label"),
    ("placeholder", find_by_placeholder, ("search",), "get_by_placeholder"),
    ("test-id", find_by_test_id, ("btn",), "get_by_test_id"),
    ("xpath", run_xpath_query, ("//div",), "locator"),
    ("buttons", find_buttons, (), "get_by_role"),
    ("links", find_links, (), "get_by_role"),
]


class TestFindBySuccess(BrowserLocatorsBaseTest):
    """Shared success-path coverage for the get_by_* family."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("op", GET_BY, ids=lambda op: op["name"])
    async def test_find_success(self, mock_browser_manager, mock_locator, op):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        for method, value in op.get("setup", {}).items():
            getattr(element, method).return_value = value

        with _mgr(manager):
            getattr(page, op["page_attr"]).return_value = locator
            result = await op["fn"](op["query"], **op.get("call_kwargs", {}))

        assert result["success"] is True
        for key, value in op["result"].items():
            assert result[key] == value
        assert len(result["elements"]) == 1
        for key, value in op.get("checks", []):
            assert result["elements"][0][key] == value
        call_args, call_kwargs = op["page_call"]
        getattr(page, op["page_attr"]).assert_called_once_with(
            *call_args, **call_kwargs
        )
        locator.first.wait_for.assert_called_once_with(
            state="visible", timeout=op.get("wait_timeout", 10000)
        )
        locator.count.assert_called_once()


class TestFailureBranches(BrowserLocatorsBaseTest):
    """No-active-page and exception branches for every locator entry point."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name,fn,args,page_attr",
        LOCATOR_OPS,
        ids=[
            "role",
            "text",
            "label",
            "placeholder",
            "test-id",
            "xpath",
            "buttons",
            "links",
        ],
    )
    async def test_no_active_page(
        self, mock_browser_manager, name, fn, args, page_attr
    ):
        manager, page = mock_browser_manager
        manager.get_current_page.return_value = None
        with _mgr(manager):
            result = await fn(*args)
        assert result["success"] is False
        assert "No active browser page available" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name,fn,args,page_attr",
        LOCATOR_OPS,
        ids=[
            "role",
            "text",
            "label",
            "placeholder",
            "test-id",
            "xpath",
            "buttons",
            "links",
        ],
    )
    async def test_locator_exception(self, name, fn, args, page_attr):
        manager = AsyncMock()
        page = MagicMock()
        manager.get_current_page.return_value = page
        getattr(page, page_attr).side_effect = RuntimeError("locator failed")
        with _mgr(manager):
            result = await fn(*args)
        assert result["success"] is False


class TestGetByEdges(BrowserLocatorsBaseTest):
    """Distinct per-strategy edge cases."""

    @pytest.mark.asyncio
    async def test_find_by_role_multiple_elements(
        self, mock_browser_manager, mock_locator
    ):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        locator.count.return_value = 3
        locator.nth.side_effect = [element, element, element]
        with _mgr(manager):
            page.get_by_role.return_value = locator
            result = await find_by_role("link")
        assert result["success"] is True
        assert result["count"] == 3
        assert len(result["elements"]) == 3

    @pytest.mark.asyncio
    async def test_find_by_text_exact_match(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator, _ = mock_locator
        with _mgr(manager):
            page.get_by_text.return_value = locator
            result = await find_by_text("Submit", exact=True)
        assert result["success"] is True
        assert result["exact"] is True
        page.get_by_text.assert_called_once_with("Submit", exact=True)

    @pytest.mark.asyncio
    async def test_find_by_text_no_results(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        locator.count.return_value = 0
        element.is_visible.return_value = False
        with _mgr(manager):
            page.get_by_text.return_value = locator
            result = await find_by_text("Nonexistent text")
        assert result["success"] is True
        assert result["count"] == 0
        assert len(result["elements"]) == 0

    @pytest.mark.asyncio
    async def test_find_by_label_textarea_element(
        self, mock_browser_manager, mock_locator
    ):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        element.evaluate.return_value = "textarea"
        element.get_attribute.return_value = None
        element.input_value.return_value = "textarea content"
        with _mgr(manager):
            page.get_by_label.return_value = locator
            result = await find_by_label("Description")
        assert result["success"] is True
        assert result["elements"][0]["tag"] == "textarea"
        assert result["elements"][0]["value"] == "textarea content"

    @pytest.mark.asyncio
    async def test_find_by_placeholder_exact(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator, _ = mock_locator
        with _mgr(manager):
            page.get_by_placeholder.return_value = locator
            result = await find_by_placeholder("Search", exact=True)
        assert result["success"] is True
        assert result["exact"] is True
        page.get_by_placeholder.assert_called_once_with("Search", exact=True)

    @pytest.mark.asyncio
    async def test_find_by_test_id_long_text_truncation(
        self, mock_browser_manager, mock_locator
    ):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        long_text = (
            "This is a very long text that exceeds 100 characters and should be "
            "truncated in the result to prevent issues with token limits"
        )
        element.text_content.return_value = long_text
        with _mgr(manager):
            page.get_by_test_id.return_value = locator
            result = await find_by_test_id("long-text-element")
        assert result["success"] is True
        assert len(result["elements"][0]["text"]) <= len(long_text)


class TestXPathQuery(BrowserLocatorsBaseTest):
    """XPath query success, truncation and failure branches."""

    @pytest.mark.asyncio
    async def test_xpath_query_success(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        element.evaluate.return_value = "div"
        element.get_attribute.side_effect = ["container", "main-content"]
        with _mgr(manager):
            page.locator.return_value = locator
            result = await run_xpath_query("//div[@class='container']")
        assert result["success"] is True
        assert result["xpath"] == "//div[@class='container']"
        assert result["elements"][0]["tag"] == "div"
        assert result["elements"][0]["class"] == "container"
        assert result["elements"][0]["id"] == "main-content"
        page.locator.assert_called_once_with("xpath=//div[@class='container']")

    @pytest.mark.asyncio
    async def test_xpath_query_with_long_text(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        long_text = "x" * 150
        element.text_content.return_value = long_text
        element.evaluate.return_value = "p"
        element.get_attribute.return_value = None
        with _mgr(manager):
            page.locator.return_value = locator
            result = await run_xpath_query("//p")
        assert result["success"] is True
        assert result["elements"][0]["text"] == "x" * 100

    @pytest.mark.asyncio
    async def test_xpath_query_invalid_xpath(self, mock_browser_manager):
        manager, page = mock_browser_manager
        with _mgr(manager):
            page.locator.side_effect = Exception("Invalid XPath")
            result = await run_xpath_query("//*[invalid")
        assert result["success"] is False
        assert "Invalid XPath" in result["error"]
        assert result["xpath"] == "//*[invalid"


class TestFindButtons(BrowserLocatorsBaseTest):
    """find_buttons with and without text filters."""

    @pytest.mark.asyncio
    async def test_find_buttons_all(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        locator.count.return_value = 5
        element.text_content.side_effect = [
            "Submit",
            "Cancel",
            "Save",
            "Delete",
            "Close",
        ]
        element.is_visible.return_value = True
        with _mgr(manager):
            page.get_by_role.return_value = locator
            result = await find_buttons()
        assert result["success"] is True
        assert result["text_filter"] is None
        assert result["total_count"] == 5
        assert result["filtered_count"] == 5
        assert len(result["buttons"]) == 5

    @pytest.mark.asyncio
    async def test_find_buttons_with_filter(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        locator.count.return_value = 3
        element.text_content.side_effect = [
            "Submit Form",
            "Cancel Operation",
            "Submit Changes",
        ]
        element.is_visible.return_value = True
        with _mgr(manager):
            page.get_by_role.return_value = locator
            result = await find_buttons(text_filter="Submit")
        assert result["success"] is True
        assert result["text_filter"] == "Submit"
        assert result["total_count"] == 3
        assert result["filtered_count"] == 2
        button_texts = [btn["text"] for btn in result["buttons"]]
        assert "Submit Form" in button_texts
        assert "Submit Changes" in button_texts
        assert "Cancel Operation" not in button_texts

    @pytest.mark.asyncio
    async def test_find_buttons_case_insensitive_filter(
        self, mock_browser_manager, mock_locator
    ):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        locator.count.return_value = 3
        element.text_content.side_effect = ["CANCEL", "cancel", "Cancel"]
        element.is_visible.return_value = True
        with _mgr(manager):
            page.get_by_role.return_value = locator
            result = await find_buttons(text_filter="cancel")
        assert result["success"] is True
        assert result["filtered_count"] == 3

    @pytest.mark.asyncio
    async def test_find_buttons_no_visible_buttons(
        self, mock_browser_manager, mock_locator
    ):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        locator.count.return_value = 2
        element.is_visible.return_value = False
        with _mgr(manager):
            page.get_by_role.return_value = locator
            result = await find_buttons()
        assert result["success"] is True
        assert result["total_count"] == 2
        assert result["filtered_count"] == 0
        assert len(result["buttons"]) == 0


class TestFindLinks(BrowserLocatorsBaseTest):
    """find_links with and without text filters."""

    @pytest.mark.asyncio
    async def test_find_links_success(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        locator.count.return_value = 2
        element.text_content.side_effect = ["Home", "About"]
        element.get_attribute.side_effect = [
            "https://example.com/home",
            "https://example.com/about",
        ]
        element.is_visible.return_value = True
        with _mgr(manager):
            page.get_by_role.return_value = locator
            result = await find_links()
        assert result["success"] is True
        assert result["total_count"] == 2
        assert result["filtered_count"] == 2
        assert len(result["links"]) == 2
        assert result["links"][0]["text"] == "Home"
        assert result["links"][0]["href"] == "https://example.com/home"
        assert result["links"][1]["text"] == "About"
        assert result["links"][1]["href"] == "https://example.com/about"

    @pytest.mark.asyncio
    async def test_find_links_with_filter(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        locator.count = AsyncMock(return_value=3)
        locator.nth.side_effect = [element, element, element]
        element.text_content = AsyncMock(
            side_effect=["Documentation", "API Docs", "Examples"]
        )
        element.get_attribute = AsyncMock(side_effect=["/docs", "/api", "/examples"])
        element.is_visible = AsyncMock(return_value=True)
        page.get_by_role = MagicMock(return_value=locator)
        with _mgr(manager):
            with patch(f"{MOD}.emit_info"):
                result = await find_links(text_filter="docs")
        assert result["success"] is True
        assert result["text_filter"] == "docs"
        assert result["filtered_count"] == 1

    @pytest.mark.asyncio
    async def test_find_links_no_href(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator, element = mock_locator
        locator.count.return_value = 1
        element.text_content.return_value = "Link without href"
        element.get_attribute.return_value = None
        element.is_visible.return_value = True
        with _mgr(manager):
            page.get_by_role.return_value = locator
            result = await find_links()
        assert result["success"] is True
        assert result["links"][0]["href"] is None


class TestIntegrationScenarios(BrowserLocatorsBaseTest):
    """Multiple locator functions on the same mocked page."""

    @pytest.mark.asyncio
    async def test_multiple_locator_functions_same_page(
        self, mock_browser_manager, mock_locator
    ):
        manager, page = mock_browser_manager
        locator, _ = mock_locator
        with _mgr(manager):
            page.get_by_role.return_value = locator
            page.get_by_text.return_value = locator
            page.get_by_test_id.return_value = locator
            role_result = await find_by_role("button")
            text_result = await find_by_text("Click")
            test_id_result = await find_by_test_id("test-button")
        assert all(r["success"] for r in [role_result, text_result, test_id_result])
        page.get_by_role.assert_called_once()
        page.get_by_text.assert_called_once()
        page.get_by_test_id.assert_called_once()


@pytest.mark.parametrize(
    "register_func,expected_tool",
    [
        (register_find_by_role, "browser_find_by_role"),
        (register_find_by_text, "browser_find_by_text"),
        (register_find_by_label, "browser_find_by_label"),
        (register_find_by_placeholder, "browser_find_by_placeholder"),
        (register_find_by_test_id, "browser_find_by_test_id"),
        (register_run_xpath_query, "browser_xpath_query"),
        (register_find_buttons, "browser_find_buttons"),
        (register_find_links, "browser_find_links"),
    ],
    ids=[
        "find_by_role",
        "find_by_text",
        "find_by_label",
        "find_by_placeholder",
        "find_by_test_id",
        "run_xpath_query",
        "find_buttons",
        "find_links",
    ],
)
class TestToolRegistration:
    """Parametrized registration checks for every tool in this module."""

    def test_register_tool(self, register_func, expected_tool):
        agent = MagicMock()
        register_func(agent)
        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == expected_tool


if __name__ == "__main__":
    pytest.main([__file__])
