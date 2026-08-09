"""Regression tests for excluding unsupported Playwright features on Android."""

import builtins
import tomllib
from pathlib import Path
from unittest.mock import patch


def test_playwright_dependency_excludes_android():
    pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
    dependencies = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]

    assert "playwright>=1.40.0; sys_platform != 'android'" in dependencies


def test_browser_tool_registry_skips_imports_on_android():
    from code_puppy.tools import _load_browser_tool_registry

    with (
        patch("code_puppy.tools.sys.platform", "android"),
        patch("builtins.__import__", wraps=builtins.__import__) as import_mock,
    ):
        registry = _load_browser_tool_registry()

    imported_modules = [call.args[0] for call in import_mock.call_args_list]
    assert registry == {}
    assert not any(
        module.startswith("code_puppy.tools.browser") for module in imported_modules
    )


def test_playwright_agents_are_skipped_on_android():
    from code_puppy.agents.agent_manager import _builtin_agent_modules_to_skip

    with patch("code_puppy.agents.agent_manager.sys.platform", "android"):
        skipped = _builtin_agent_modules_to_skip()

    assert "agent_qa_kitten" in skipped
    assert "agent_web_retriever" in skipped
