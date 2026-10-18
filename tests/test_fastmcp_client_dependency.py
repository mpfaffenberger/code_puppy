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
        and requirement.extras == {"client"}
        and not requirement.marker
        for requirement in map(Requirement, project["dependencies"])
    )


@pytest.mark.parametrize(
    ("module", "symbol"),
    [
        ("fastmcp.client.transports", "StdioTransport"),
        ("fastmcp.client.transports", "SSETransport"),
        ("fastmcp.client.transports", "StreamableHttpTransport"),
        ("fastmcp.client.auth", "OAuth"),
    ],
)
def test_client_symbols_import(module, symbol):
    # Deliberately not skippable: bare fastmcp-slim imports fine, then fails here.
    assert hasattr(importlib.import_module(module), symbol)
