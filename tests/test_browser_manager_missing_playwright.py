"""Regression tests for importing browser manager without Playwright."""

from __future__ import annotations

import builtins
import importlib
import sys
from unittest.mock import patch

import pytest


_BROWSER_MANAGER_MODULE = "code_puppy.tools.browser.browser_manager"
_MODULE_NAMES = (
    _BROWSER_MANAGER_MODULE,
    "playwright.async_api",
    "playwright",
)
_MISSING = object()


def _unload_browser_manager_and_playwright() -> None:
    for module_name in _MODULE_NAMES:
        sys.modules.pop(module_name, None)
    importlib.invalidate_caches()


def _restore_modules(originals: dict[str, object]) -> None:
    _unload_browser_manager_and_playwright()
    for module_name, module in originals.items():
        if module is not _MISSING:
            sys.modules[module_name] = module


@pytest.mark.asyncio
async def test_browser_manager_imports_without_playwright_until_used():
    real_import = builtins.__import__

    def block_playwright(name, *args, **kwargs):
        if name == "playwright.async_api":
            raise ModuleNotFoundError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    originals = {
        module_name: sys.modules.get(module_name, _MISSING)
        for module_name in _MODULE_NAMES
    }
    try:
        _unload_browser_manager_and_playwright()
        with patch("builtins.__import__", side_effect=block_playwright):
            browser_manager = importlib.import_module(_BROWSER_MANAGER_MODULE)

        manager = browser_manager.BrowserManager(session_id="missing-playwright-test")
        with pytest.raises(RuntimeError, match="Playwright is not installed"):
            await manager._initialize_browser()
    finally:
        _restore_modules(originals)
