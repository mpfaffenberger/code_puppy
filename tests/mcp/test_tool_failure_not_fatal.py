"""A failing MCP tool must not end the agent run.

Behavioral counterpart to the wiring assertions in ``test_managed_server``,
run against a real stdio MCP server: ``"retry"`` kills the run once the budget
is spent, ``"failed"`` survives. Mock-based tests alone would keep passing if
pydantic-ai ever redefined these semantics.
"""

import sys
import textwrap

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

# A server whose only tool always raises, mimicking the reported JS error.
_SERVER_SOURCE = textwrap.dedent(
    """
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("boom")

    @mcp.tool()
    def evaluate_script(script: str) -> str:
        "Evaluate a script in the page."
        raise RuntimeError("Error: Cannot read properties of null (reading 'click')")

    if __name__ == "__main__":
        mcp.run()
    """
).strip()

RETRIES = 3
ANSWER = "The tool failed; carrying on."


@pytest.fixture
def failing_server(tmp_path):
    """Path to a stdio MCP server whose single tool always fails."""
    script = tmp_path / "always_fails_server.py"
    script.write_text(_SERVER_SOURCE)
    return script


def _model_that_keeps_calling(tool_name: str, calls: dict):
    """Calls ``tool_name`` past the retry budget, then answers.

    Going past the budget is the point — that boundary is where the default
    behavior raises instead of letting the model continue.
    """

    def model_fn(messages, info):
        calls["n"] += 1
        if calls["n"] <= RETRIES + 2:
            return ModelResponse(
                parts=[ToolCallPart(tool_name, {"script": "el.click()"})]
            )
        return ModelResponse(parts=[TextPart(ANSWER)])

    return model_fn


async def _run_with(behavior: str, server_script) -> str:
    """Run an agent against the always-failing server; return its output."""
    from fastmcp.client.transports import StdioTransport
    from pydantic_ai.mcp import MCPToolset

    toolset = MCPToolset(
        StdioTransport(command=sys.executable, args=[str(server_script)]),
        tool_error_behavior=behavior,
        prefer_tasks=False,
    ).prefixed("boom")

    calls = {"n": 0}
    agent = Agent(
        FunctionModel(_model_that_keeps_calling("boom_evaluate_script", calls)),
        toolsets=[toolset],
        retries=RETRIES,
    )
    result = await agent.run("Click the button.")
    return result.output


@pytest.mark.asyncio
async def test_failing_tool_does_not_kill_the_run(failing_server):
    """Our setting: the model sees the failure and finishes the turn."""
    assert await _run_with("failed", failing_server) == ANSWER


@pytest.mark.asyncio
async def test_default_retry_behavior_would_kill_the_run(failing_server):
    """Characterize the default we are deliberately overriding.

    If this ever stops raising, pydantic-ai changed its retry semantics and
    the override above should be re-evaluated rather than blindly kept.
    """
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    with pytest.raises(UnexpectedModelBehavior, match="exceeded max retries"):
        await _run_with("retry", failing_server)
