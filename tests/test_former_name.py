"""``import pydantic_clai2`` must hand back pax's own modules, not copies.

The deprecated alias package answers with a second execution of the same
files, so ``pydantic_clai2.plugins.Plugin`` is not ``pydantic_ai_pax.plugins
.Plugin``. ``pydantic-claude-code`` 0.7.x imports the runtime under the old
name; with copies, its plugin is a ``Plugin`` pax never saw and every
``claude-code:`` model is unknown. See ``code_puppy/former_name.py``.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import re
import subprocess
import sys

import pytest

from code_puppy import former_name


def test_the_old_name_imports_the_new_package() -> None:
    former_name.install()

    assert importlib.import_module("pydantic_clai2") is importlib.import_module(
        "pydantic_ai_pax"
    )


@pytest.mark.parametrize("name", sorted(former_name.FORMER_MODULES))
def test_each_answered_name_is_the_same_module(name: str) -> None:
    former_name.install()

    former = importlib.import_module(name)
    current = importlib.import_module("pydantic_ai_pax" + name[len("pydantic_clai2") :])

    assert former is current


def test_every_old_name_the_claude_code_plugin_imports_is_answered() -> None:
    """Fails when a `pydantic-claude-code` upgrade imports one more old name.

    An unanswered one would raise, and that plugin reads the error as "the
    runtime is not installed" and quietly registers nothing.
    """
    files = importlib.metadata.distribution("pydantic-claude-code").files or []
    imported = {
        name
        for file in files
        if file.suffix == ".py"
        for name in re.findall(r"pydantic_clai2[\w.]*", file.read_text())
    }

    assert imported, "the plugin no longer imports the old name: drop former_name"
    assert imported <= former_name.FORMER_MODULES


def test_any_other_old_name_is_refused_not_run_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``pydantic_clai2`` is pax's package, so Python would find this in pax's folder."""
    former_name.install()
    importlib.import_module("pydantic_clai2")
    monkeypatch.delitem(sys.modules, "pydantic_clai2.config", raising=False)

    with pytest.raises(ModuleNotFoundError, match="import 'pydantic_ai_pax.config'"):
        importlib.import_module("pydantic_clai2.config")
    assert "pydantic_clai2.config" not in sys.modules


def test_the_claude_code_plugin_shares_paxs_modules() -> None:
    """End to end, in a fresh interpreter: no copy of any module it uses."""
    script = (
        "from code_puppy import former_name; former_name.install()\n"
        "from pydantic_ai_claude_code import clai2\n"
        "from pydantic_ai_pax import plugins\n"
        "from pydantic_ai_pax.ui.menus import field_menu, menu_worker\n"
        "assert issubclass(clai2.ClaudeCodePlugin, plugins.Plugin)\n"
        "assert clai2.run_worker is menu_worker.run_worker\n"
        "assert clai2.FieldMenu is field_menu.FieldMenu\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_a_class_under_both_names_is_one_class() -> None:
    former_name.install()

    former = importlib.import_module("pydantic_clai2.plugins")
    current = importlib.import_module("pydantic_ai_pax.plugins")

    assert former.Plugin is current.Plugin


@pytest.mark.parametrize("name", ["commands", "plugins", "ui.menus.field_menu"])
def test_the_old_name_leaves_the_module_its_own_spec(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise pax's module describes the old name, and reloading it runs nothing."""
    former_name.install()
    current = importlib.import_module(f"pydantic_ai_pax.{name}")
    spec = current.__spec__
    # A fresh alias import, whatever earlier tests imported.
    monkeypatch.delitem(sys.modules, f"pydantic_clai2.{name}", raising=False)

    assert importlib.import_module(f"pydantic_clai2.{name}") is current
    assert current.__spec__ is spec
    assert current.__spec__.name == f"pydantic_ai_pax.{name}"


def test_installing_twice_answers_once() -> None:
    former_name.install()
    before = list(__import__("sys").meta_path)
    former_name.install()

    assert __import__("sys").meta_path == before
