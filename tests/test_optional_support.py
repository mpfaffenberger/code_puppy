"""Everything the runtime can do is installed with Code Puppy.

pax keeps its cloud sandboxes behind extras, and answers ``/sandbox modal``
with "Modal support is not installed. Install CLAI with it: uv tool install
'pydantic-ai-pax[modal]'" when one is missing. That advice names another
product's package, and following it would not change a Code Puppy install.
Code Puppy depends on every extra instead.
"""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
RUNTIME = "pydantic-ai-pax"


def required_extras() -> set[str]:
    """The pax extras ``pyproject.toml`` asks for."""
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    requirements = map(Requirement, project["dependencies"])
    [runtime] = [r for r in requirements if canonicalize_name(r.name) == RUNTIME]
    return set(runtime.extras)


def test_every_extra_the_runtime_offers_is_required() -> None:
    """A new extra upstream is a new "not installed" message until it is added here."""
    offered = set(metadata.metadata(RUNTIME).get_all("Provides-Extra") or [])
    assert offered, "the runtime no longer declares extras; this test needs rethinking"
    assert required_extras() == offered


def test_no_sandbox_provider_says_its_support_is_not_installed(
    installed_distribution: None, home: Path
) -> None:
    """What is left to say is how to sign in, which is the user's to do."""
    from pydantic_ai_pax.builtin_plugins.sandbox.providers import PROVIDERS

    assert PROVIDERS, "the sandbox providers moved; this test needs rethinking"
    not_installed = {
        name: message
        for name, provider in PROVIDERS.items()
        if (message := provider.missing()) and "not installed" in message
    }
    assert not_installed == {}
