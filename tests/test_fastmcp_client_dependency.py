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


def _fastmcp_imports(source):
    """Split a module's fastmcp imports into subpackages and root symbols.

    ``from fastmcp.client import x`` yields the subpackage ``client``;
    ``from fastmcp import Client`` yields the root symbol ``Client``. The two
    need different checks, because the root re-exports both client and server
    objects and only the former is covered by the extra we declare.
    """
    subpackages, root_symbols = set(), set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "fastmcp":
                root_symbols.update(alias.name for alias in node.names)
            elif module.startswith("fastmcp."):
                subpackages.add(module.split(".")[1])
        elif isinstance(node, ast.Import):
            subpackages.update(
                alias.name.split(".")[1]
                for alias in node.names
                if alias.name.startswith("fastmcp.")
            )
    return subpackages, root_symbols


def _shipped_fastmcp_imports():
    subpackages, root_symbols = set(), set()
    for path in (ROOT / "code_puppy").rglob("*.py"):
        found = _fastmcp_imports(path.read_text(encoding="utf-8"))
        subpackages |= found[0]
        root_symbols |= found[1]
    return subpackages, root_symbols


def test_client_extra_is_declared_as_a_direct_dependency():
    requirement = _declared_requirement()
    assert requirement.extras == {EXTRA}
    assert not requirement.marker  # Needed on every platform, never optional.


def test_declared_range_agrees_with_pydantic_ai_mcp_extra():
    """Keep our supported-version policy in step with pydantic-ai's.

    Both edges name the same distribution, so a mismatch does not install two
    copies -- it means a pydantic-ai upgrade silently moved the supported
    fastmcp range out from under a range we still advertise. This fails then,
    so the move is a decision rather than an accident.
    """
    from importlib.metadata import metadata

    ours = _declared_requirement().specifier
    theirs = next(
        requirement.specifier
        for requirement in map(
            Requirement, metadata("pydantic-ai-slim").get_all("Requires-Dist")
        )
        if requirement.name == DISTRIBUTION
        and requirement.marker
        and requirement.marker.evaluate({"extra": "mcp"})
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

    A bare ``fastmcp-slim`` satisfies ``import fastmcp`` yet raises the
    reported client-support ImportError here. This imports for real and is
    deliberately not skippable: a missing client extra is the defect under
    test, not an excuse to pass.
    """
    assert hasattr(importlib.import_module(module), symbol)


def test_shipped_subpackage_imports_stay_within_the_declared_extra():
    subpackages, _ = _shipped_fastmcp_imports()
    assert subpackages <= {EXTRA}


def test_shipped_root_imports_resolve_under_the_declared_extra():
    """The fastmcp root re-exports server objects too, and those still fail.

    Resolving each symbol for real is the only honest check: the root module
    imports fine under a client-only install and raises lazily per attribute.
    """
    fastmcp = importlib.import_module("fastmcp")
    _, root_symbols = _shipped_fastmcp_imports()
    for symbol in sorted(root_symbols):
        assert getattr(fastmcp, symbol)


def test_root_import_guard_rejects_server_only_symbols():
    """Keeps the guard above honest -- it must not pass everything.

    ``FastMCP`` is the server entry point; under ``fastmcp-slim[client]`` it
    raises the server-support ImportError, so a module importing it would be
    undeclared just like the client case was.
    """
    _, root_symbols = _fastmcp_imports("from fastmcp import FastMCP")
    assert root_symbols == {"FastMCP"}
    with pytest.raises(ImportError, match="server support is not installed"):
        getattr(importlib.import_module("fastmcp"), "FastMCP")
