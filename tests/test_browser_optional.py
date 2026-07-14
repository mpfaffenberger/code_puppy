"""Browser automation must be an optional capability.

Playwright has no wheels for some platforms (e.g. Android/Termux), so it is an
optional ``[browser]`` extra. Importing ``code_puppy.tools`` must not crash when
Playwright is unavailable; browser tools should only fail when actually invoked.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def test_tools_import_without_playwright():
    script = textwrap.dedent(
        """
        import sys

        # Simulate a platform where Playwright is not installed.
        sys.modules["playwright"] = None
        sys.modules["playwright.async_api"] = None

        # Must not raise even though Playwright is unavailable.
        import code_puppy.tools  # noqa: F401
        from code_puppy.tools.browser import browser_manager  # noqa: F401

        # The stub keeps the module importable but inert.
        from playwright.async_api import async_playwright

        try:
            async_playwright()
        except RuntimeError:
            print("OK")
        else:
            raise AssertionError("expected RuntimeError from stubbed async_playwright")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "OK"
