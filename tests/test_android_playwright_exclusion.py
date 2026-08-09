"""Regression tests for excluding unsupported Playwright features on Android."""

import subprocess
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch


def test_playwright_dependency_excludes_android():
    pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
    dependencies = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]

    assert "playwright>=1.40.0; sys_platform != 'android'" in dependencies


def test_browser_tool_registry_is_empty_on_android():
    from code_puppy.tools import _load_browser_tool_registry

    with patch("code_puppy.tools.sys.platform", "android"):
        assert _load_browser_tool_registry() == {}


def test_android_tools_import_does_not_load_playwright():
    script = """
import platform
import sys
import uuid  # Initialize platform-dependent stdlib state before simulation.
platform.uname()
sys.platform = "android"
import code_puppy.tools as tools
assert not any(name.startswith("browser_") for name in tools.TOOL_REGISTRY)
assert "playwright" not in sys.modules
assert not any(name.startswith("code_puppy.tools.browser") for name in sys.modules)
"""

    subprocess.run([sys.executable, "-c", script], check=True)


def test_playwright_agents_are_skipped_on_android():
    from code_puppy.agents.agent_manager import _builtin_agent_modules_to_skip

    with patch("code_puppy.agents.agent_manager.sys.platform", "android"):
        skipped = _builtin_agent_modules_to_skip()

    assert "agent_qa_kitten" in skipped
    assert "agent_web_retriever" in skipped
