"""``import pydantic_clai2`` must hand back pax's own modules, not copies.

The deprecated alias package answers with a second execution of the same
files, so ``pydantic_clai2.plugins.Plugin`` is not ``pydantic_ai_pax.plugins
.Plugin``. ``pydantic-claude-code`` 0.7.x imports the runtime under the old
name; with copies, its plugin is a ``Plugin`` pax never saw and every
``claude-code:`` model is unknown. See ``code_puppy/former_name.py``.
"""

from __future__ import annotations

import importlib

import pytest

from code_puppy import former_name


def test_the_old_name_imports_the_new_package() -> None:
    former_name.install()

    assert importlib.import_module("pydantic_clai2") is importlib.import_module(
        "pydantic_ai_pax"
    )


@pytest.mark.parametrize("name", ["commands", "plugins"])
def test_a_submodule_is_the_same_module(name: str) -> None:
    former_name.install()

    former = importlib.import_module(f"pydantic_clai2.{name}")
    current = importlib.import_module(f"pydantic_ai_pax.{name}")

    assert former is current


def test_a_class_under_both_names_is_one_class() -> None:
    former_name.install()

    former = importlib.import_module("pydantic_clai2.plugins")
    current = importlib.import_module("pydantic_ai_pax.plugins")

    assert former.Plugin is current.Plugin


def test_installing_twice_answers_once() -> None:
    former_name.install()
    before = list(__import__("sys").meta_path)
    former_name.install()

    assert __import__("sys").meta_path == before
