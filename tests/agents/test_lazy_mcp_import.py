"""Importing the agent stack must not import the MCP client stack.

``code_puppy.mcp_`` pulls in fastmcp and the mcp SDK. Agents only need it
once MCP servers are actually loaded, so ``_builder`` and ``_runtime`` import
it on first use. Checked in a fresh interpreter, since this test session has
long since imported everything.
"""

import subprocess
import sys

from code_puppy.agents import _runtime


def _modules_after(statement: str) -> set[str]:
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; {statement}; print('\\n'.join(sys.modules))",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return set(out.split())


def test_importing_agents_does_not_import_code_puppy_mcp():
    modules = _modules_after("import code_puppy.agents")

    assert "code_puppy.agents._builder" in modules
    assert "code_puppy.agents._runtime" in modules
    assert "code_puppy.mcp_" not in modules


def test_mcp_error_type_is_the_sdk_protocol_error():
    from mcp.shared import exceptions

    error_type = _runtime._mcp_error_type()

    assert error_type is getattr(
        exceptions, "McpError", getattr(exceptions, "MCPError", None)
    )
    assert issubclass(error_type, Exception)
