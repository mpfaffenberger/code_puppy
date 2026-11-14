"""The plugins Code Puppy ships beside the runtime's own."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement

from code_puppy.builtin_plugins import PUPPY_PLUGINS


def test_every_shipped_declaration_names_a_plugin_class(
    installed_distribution: None,
) -> None:
    from pydantic_clai2.plugins import Plugin

    assert [plugin.id for plugin in PUPPY_PLUGINS] == [
        "personality",
        "legacy_plugins",
        "claude_code",
    ]
    for plugin in PUPPY_PLUGINS:
        module, _, attribute = plugin.factory.partition(":")
        assert issubclass(getattr(importlib.import_module(module), attribute), Plugin)


def test_claude_code_comes_from_the_right_distribution() -> None:
    """Two PyPI projects have near-identical names; only one is ours.

    ``pydantic-claude-code`` is the dependency. ``pydantic-ai-claude-code`` is
    an unrelated project, although ours is imported as
    ``pydantic_ai_claude_code``. Depending on the wrong one would install a
    stranger's code under the name we import.
    """
    required = {
        Requirement(text).name for text in metadata.requires("code-puppy") or []
    }
    assert "pydantic-claude-code" in required
    assert "pydantic-ai-claude-code" not in required
    owners = metadata.packages_distributions()["pydantic_ai_claude_code"]
    assert owners == ["pydantic-claude-code"]


def test_the_plugins_own_update_notice_is_off(installed_distribution: None) -> None:
    """It would tell users to reinstall a drop-in; here it updates with Code Puppy."""
    from pydantic_ai_claude_code import updates

    assert updates.enabled() is False


def test_claude_code_models_resolve_in_a_real_session(
    home: Path, tmp_path: Path
) -> None:
    """``claude-code:`` reaches the plugin, which asks for a sign-in.

    Credentials are forced to a file under the temp home, so the test never
    reads a real Claude Code sign-in and never calls Anthropic.
    """
    work = tmp_path / "work"
    work.mkdir()
    env = {
        **os.environ,
        "CODE_PUPPY_NO_SPLASH": "1",
        "CLAUDE_CODE_CREDENTIALS": "file",
        "XDG_DATA_HOME": str(home / "data"),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "code_puppy",
            "-m",
            "claude-code:claude-haiku-4-5",
            "-p",
            "hi",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=work,
        timeout=180,
        check=False,
    )
    assert result.returncode != 0
    assert "Sign in to Claude Code first: /login claude-code." in result.stderr
    assert "Unknown model" not in result.stderr
