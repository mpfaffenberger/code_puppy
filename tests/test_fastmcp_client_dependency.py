"""code_puppy.mcp_ imports fastmcp.client directly, so it declares the client extra."""

import importlib
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_client_extra_is_a_direct_dependency():
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert any(
        requirement.name == "fastmcp-slim"
        and "client" in requirement.extras
        and not requirement.marker
        for requirement in map(Requirement, project["dependencies"])
    )


@pytest.mark.parametrize(
    "module",
    [
        "code_puppy.mcp_.blocking_startup",
        "code_puppy.mcp_.managed_server",
        "code_puppy.mcp_.http_auth",
    ],
)
def test_mcp_modules_import(module):
    # Exercise the shipped imports instead of keeping a second symbol inventory.
    # Deliberately not skippable: bare fastmcp-slim imports fine, then fails here.
    importlib.import_module(module)
