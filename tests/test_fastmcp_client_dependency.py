"""The FastMCP *client* capability is a first-party requirement.

``code_puppy.mcp_`` imports ``fastmcp.client.*`` directly. ``fastmcp-slim``
ships those modules behind its ``client`` extra and raises
``ImportError("FastMCP client support is not installed. Install fastmcp or
fastmcp-slim[client].")`` when the extra's dependencies are absent.

Relying on ``pydantic-ai-slim[mcp]`` to drag the extra in makes that import a
side effect of somebody else's packaging. These tests pin the declaration and,
more importantly, prove the symbols actually import in the resolved
environment -- a dependency string alone never proved anything.
"""

import ast
import importlib
import tomllib
from importlib.metadata import metadata
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = "fastmcp-slim"
EXTRA = "client"


def _read_toml(name):
    with (ROOT / name).open("rb") as stream:
        return tomllib.load(stream)


def _declared_requirement():
    dependencies = _read_toml("pyproject.toml")["project"]["dependencies"]
    return next(
        requirement
        for requirement in map(Requirement, dependencies)
        if requirement.name == DISTRIBUTION
    )


def test_client_extra_is_declared_as_a_direct_dependency():
    requirement = _declared_requirement()
    assert requirement.extras == {EXTRA}
    assert not requirement.marker  # Needed on every platform, never optional.


def test_declared_range_agrees_with_pydantic_ai_mcp_extra():
    """Our range and pydantic-ai's must never select different majors.

    Both constrain the same import path, so a version satisfying one but not
    the other would mean two installed distributions fighting over
    ``fastmcp/``.
    """
    ours = _declared_requirement().specifier
    theirs = next(
        Requirement(value).specifier
        for value in metadata("pydantic-ai-slim").get_all("Requires-Dist")
        if Requirement(value).name == DISTRIBUTION
        and "extra == 'mcp'" in value
        and "mcp-tasks" not in value
    )
    assert ours == theirs


def test_lock_materialises_the_client_extra():
    packages = {item["name"]: item for item in _read_toml("uv.lock")["package"]}
    assert {"name": DISTRIBUTION, "extra": [EXTRA]} in packages["code-puppy"][
        "dependencies"
    ]
    assert (
        Version(packages[DISTRIBUTION]["version"]) in _declared_requirement().specifier
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
    """Regression for the installed-but-unusable environment.

    A bare ``fastmcp-slim`` satisfies ``import fastmcp`` and fails here, which
    is exactly how the preview build surfaced the error at MCP startup. This
    imports for real and is deliberately not skippable: a missing client extra
    is the defect under test, not an excuse to pass.
    """
    assert hasattr(importlib.import_module(module), symbol)


def test_every_fastmcp_import_is_covered_by_the_declaration():
    """No shipped module may reach past the extra we declare."""
    roots = set()
    for path in (ROOT / "code_puppy").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "fastmcp"
            ):
                roots.add(node.module.split(".")[1] if "." in node.module else "")
            elif isinstance(node, ast.Import):
                roots.update(
                    alias.name.split(".")[1]
                    for alias in node.names
                    if alias.name.startswith("fastmcp.")
                )
    # "" means bare ``from fastmcp import ...``, always available.
    assert roots <= {"", EXTRA}
