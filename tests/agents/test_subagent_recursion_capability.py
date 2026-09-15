"""Contract tests for ``SubagentRecursionGuard`` (wrap_tool_execute seam).

The sub-agent recursion guards (general ``subagent_recursion_limit`` depth
cap + GPT-5.6 overlay) historically ran at the top of
``_invoke_agent_impl``. They are now delivered as a pydantic-ai capability
on the ``wrap_tool_execute`` seam, with the in-tool check retained as guest
custody. These tests pin:

- the seam denies before the tool body runs (impl never entered) with the
  byte-identical denial output the in-tool guard produced;
- the GPT-5.6 overlay and the general cap keep their verdict order;
- ``invoke_agent_with_model`` empty-``model_name`` rejection keeps its
  historical precedence over the recursion guard;
- non-guarded tools and under-limit calls pass through untouched;
- guest custody (agents without the capability) still denies, identically;
- both construction sites wire the guard, conditionally on the agent's
  declared tool surface.
"""

import asyncio
from typing import Any, List

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from code_puppy.agents._subagent_recursion import (
    GUARDED_TOOL_NAMES,
    SubagentRecursionGuard,
    build_subagent_recursion_guard,
)
from code_puppy.i18n import t
from code_puppy.tools import subagent_invocation as si
from code_puppy.tools.agent_tools import (
    AgentInvokeOutput,
    AgentInvokeWithModelOutput,
)
from code_puppy.tools.subagent_usage_metrics import build_invoke_output

# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _make_agent(tool_call: ToolCallPart, *, with_capability: bool) -> Agent:
    """Agent that issues ``tool_call`` once, then finishes."""

    def model_fn(messages: List[Any], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[tool_call])
        return ModelResponse(parts=[TextPart("done")])

    agent = Agent(
        FunctionModel(model_fn),
        retries=3,
        capabilities=[SubagentRecursionGuard()] if with_capability else [],
    )
    si.register_invoke_agent(agent)
    si.register_invoke_agent_with_model(agent)
    return agent


def _tool_return(result: Any, tool_name: str) -> Any:
    """Extract the ToolReturnPart content the model saw for ``tool_name``."""
    for message in result.all_messages():
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart) and part.tool_name == tool_name:
                return part.content
    raise AssertionError(f"no ToolReturnPart for {tool_name!r}")


@pytest.fixture
def impl_spy(monkeypatch):
    """Replace ``_invoke_agent_impl`` with a recording stub."""
    calls: List[dict] = []

    async def _spy(**kwargs: Any) -> AgentInvokeOutput:
        calls.append(kwargs)
        return build_invoke_output(
            include_usage_metrics=kwargs.get("include_usage_metrics", False),
            response="spy-response",
            agent_name=kwargs["agent_name"],
            session_id="spy-session",
            model_name=kwargs.get("model_name"),
        )

    monkeypatch.setattr(si, "_invoke_agent_impl", _spy)
    return calls


@pytest.fixture
def emitted(monkeypatch):
    """Capture ``emit_error`` calls from the subagent_invocation module."""
    records: List[str] = []
    monkeypatch.setattr(
        si, "emit_error", lambda msg, **kwargs: records.append(str(msg))
    )
    return records


def _block_general(monkeypatch) -> None:
    """Depth 0 already meets a limit of 0: every invocation is denied."""
    monkeypatch.setattr(si, "get_subagent_recursion_limit", lambda: 0)


def _block_gpt_5_6(monkeypatch) -> None:
    """GPT-5.6 caller, overlay cap 0; the general cap stays permissive."""
    monkeypatch.setattr(si, "get_subagent_recursion_limit", lambda: 10)
    monkeypatch.setattr(si, "get_subagent_model_name", lambda: "gpt-5.6-codex")
    monkeypatch.setattr(si, "get_subagent_recursion_limit_gpt_5_6", lambda: 0)


_INVOKE_CALL = ToolCallPart(
    tool_name="invoke_agent",
    args={"agent_name": "helper", "prompt": "p", "session_id": "keep-me"},
)


# ---------------------------------------------------------------------------
# Seam denial
# ---------------------------------------------------------------------------


def test_seam_denies_general_depth_limit(monkeypatch, impl_spy, emitted):
    _block_general(monkeypatch)
    agent = _make_agent(_INVOKE_CALL, with_capability=True)

    result = asyncio.run(agent.run("go"))

    assert impl_spy == []  # tool body never entered
    output = _tool_return(result, "invoke_agent")
    expected_error = t("subagent.recursion_limit_reached", limit=0, agent="helper")
    assert isinstance(output, AgentInvokeOutput)
    assert not isinstance(output, AgentInvokeWithModelOutput)
    assert output.error == expected_error
    assert output.response is None
    assert output.agent_name == "helper"
    # Historical blocked path never echoed the caller's session_id.
    assert output.session_id is None
    assert output.model_name is None
    assert emitted == [expected_error]


def test_seam_denies_gpt_5_6_overlay(monkeypatch, impl_spy, emitted):
    _block_gpt_5_6(monkeypatch)
    agent = _make_agent(_INVOKE_CALL, with_capability=True)

    result = asyncio.run(agent.run("go"))

    assert impl_spy == []
    output = _tool_return(result, "invoke_agent")
    expected_error = t(
        "subagent.gpt_5_6_recursion_blocked", agent="helper", depth=1, limit=0
    )
    assert output.error == expected_error
    assert emitted == [expected_error]


def test_general_cap_precedes_gpt_5_6_overlay(monkeypatch, impl_spy):
    """Both caps tripped -> the general message wins (historical if/elif order)."""
    _block_gpt_5_6(monkeypatch)
    monkeypatch.setattr(si, "get_subagent_recursion_limit", lambda: 0)
    agent = _make_agent(_INVOKE_CALL, with_capability=True)

    result = asyncio.run(agent.run("go"))

    output = _tool_return(result, "invoke_agent")
    assert output.error == t(
        "subagent.recursion_limit_reached", limit=0, agent="helper"
    )


def test_seam_passes_when_under_limit(monkeypatch, impl_spy, emitted):
    monkeypatch.setattr(si, "get_subagent_recursion_limit", lambda: 10)
    agent = _make_agent(_INVOKE_CALL, with_capability=True)

    result = asyncio.run(agent.run("go"))

    assert len(impl_spy) == 1
    assert impl_spy[0]["agent_name"] == "helper"
    assert impl_spy[0]["session_id"] == "keep-me"
    output = _tool_return(result, "invoke_agent")
    assert output.response == "spy-response"
    assert emitted == []


def test_non_gpt_caller_ignores_overlay(monkeypatch, impl_spy):
    _block_gpt_5_6(monkeypatch)
    monkeypatch.setattr(si, "get_subagent_model_name", lambda: "claude-sonnet")
    agent = _make_agent(_INVOKE_CALL, with_capability=True)

    asyncio.run(agent.run("go"))

    assert len(impl_spy) == 1


# ---------------------------------------------------------------------------
# invoke_agent_with_model flavor
# ---------------------------------------------------------------------------


def test_with_model_flavor_denies_with_usage_shape(monkeypatch, impl_spy, emitted):
    _block_general(monkeypatch)
    call = ToolCallPart(
        tool_name="invoke_agent_with_model",
        args={"agent_name": "helper", "prompt": "p", "model_name": "  m1  "},
    )
    agent = _make_agent(call, with_capability=True)

    result = asyncio.run(agent.run("go"))

    assert impl_spy == []
    output = _tool_return(result, "invoke_agent_with_model")
    assert isinstance(output, AgentInvokeWithModelOutput)
    assert output.error == t(
        "subagent.recursion_limit_reached", limit=0, agent="helper"
    )
    # Normalized exactly as the tool wrapper normalizes before the impl guard.
    assert output.model_name == "m1"
    assert output.input_tokens is None
    assert output.num_requests is None
    assert output.duration_ms is None


def test_empty_model_name_precedence_over_guard(monkeypatch, impl_spy, emitted):
    """Blank model_name is rejected by the tool itself, ahead of the guard."""
    _block_general(monkeypatch)
    call = ToolCallPart(
        tool_name="invoke_agent_with_model",
        args={"agent_name": "helper", "prompt": "p", "model_name": "   "},
    )
    agent = _make_agent(call, with_capability=True)

    result = asyncio.run(agent.run("go"))

    assert impl_spy == []  # wrapper's empty-model check returns before impl
    output = _tool_return(result, "invoke_agent_with_model")
    assert output.error == "model_name cannot be empty"
    assert emitted == ["model_name cannot be empty"]


# ---------------------------------------------------------------------------
# Pass-through and guest custody
# ---------------------------------------------------------------------------


def test_non_guarded_tools_pass_through(monkeypatch, impl_spy):
    _block_general(monkeypatch)
    call = ToolCallPart(tool_name="other_tool", args={"q": "hi"})
    agent = _make_agent(call, with_capability=True)

    async def other_tool(ctx, q: str) -> str:
        return f"ran-{q}"

    agent._function_toolset.add_function(other_tool, takes_ctx=True, name="other_tool")

    result = asyncio.run(agent.run("go"))
    assert _tool_return(result, "other_tool") == "ran-hi"


def test_guest_custody_denies_identically(monkeypatch, emitted):
    """Without the capability, the in-tool guard denies with identical bytes."""
    _block_general(monkeypatch)

    capability_agent = _make_agent(_INVOKE_CALL, with_capability=True)
    guest_agent = _make_agent(_INVOKE_CALL, with_capability=False)

    seam_output = _tool_return(asyncio.run(capability_agent.run("go")), "invoke_agent")
    guest_output = _tool_return(asyncio.run(guest_agent.run("go")), "invoke_agent")

    assert seam_output == guest_output
    assert guest_output.error == t(
        "subagent.recursion_limit_reached", limit=0, agent="helper"
    )
    # One denial emit per custody, same message both times.
    assert emitted == [guest_output.error, guest_output.error]


def test_seam_preempts_in_tool_guard(monkeypatch):
    """With the capability, the real impl body is never entered when denied."""
    _block_general(monkeypatch)
    entered: List[str] = []
    original_impl = si._invoke_agent_impl

    async def _tracking_impl(**kwargs: Any):
        entered.append(kwargs["agent_name"])
        return await original_impl(**kwargs)

    monkeypatch.setattr(si, "_invoke_agent_impl", _tracking_impl)
    monkeypatch.setattr(si, "emit_error", lambda *a, **k: None)
    agent = _make_agent(_INVOKE_CALL, with_capability=True)

    asyncio.run(agent.run("go"))
    assert entered == []


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_conditional_splice_shapes():
    assert build_subagent_recursion_guard(["invoke_agent"]) != []
    assert build_subagent_recursion_guard(["invoke_agent_with_model", "x"]) != []
    assert build_subagent_recursion_guard(["read_file"]) == []
    assert build_subagent_recursion_guard([]) == []
    assert build_subagent_recursion_guard(None) == []
    guard = build_subagent_recursion_guard(list(GUARDED_TOOL_NAMES))
    assert len(guard) == 1 and isinstance(guard[0], SubagentRecursionGuard)


def test_capability_visible_in_agent_tree():
    """The guard is discoverable via the public capability visitor."""
    agent = Agent(
        FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("hi")])),
        capabilities=[*build_subagent_recursion_guard(["invoke_agent"])],
    )
    seen: List[Any] = []

    def _visit(cap):
        if isinstance(cap, SubagentRecursionGuard):
            seen.append(cap)
        return cap

    agent.root_capability.apply(_visit)
    assert len(seen) == 1


def test_builder_wires_guard_from_tool_surface():
    """Source pin: the builder splices the guard from ``agent_tools``."""
    import inspect

    from code_puppy.agents import _builder

    src = inspect.getsource(_builder.build_pydantic_agent)
    assert "agent_tools = agent.get_available_tools()" in src
    cap_block = src[src.find("capabilities=[") :]
    assert "*build_subagent_recursion_guard(agent_tools)" in cap_block
    # The tool surface must be read before the closure first runs (probe pass).
    assert src.find("agent_tools = agent.get_available_tools()") < src.find(
        "def _new_pydantic_agent"
    )


def test_subagent_site_wires_guard_from_tool_surface():
    """Source pin: the temp-agent site splices the guard from ``agent_tools``."""
    import inspect

    src = inspect.getsource(si._invoke_agent_impl)
    assert "agent_tools = agent_config.get_available_tools()" in src
    cap_block = src[src.find("capabilities=[") :]
    assert "*build_subagent_recursion_guard(agent_tools)" in cap_block
    # Read before construction so the splice sees the declared tool surface.
    assert src.find("agent_tools = agent_config.get_available_tools()") < src.find(
        "temp_agent = Agent("
    )


def test_verdict_helper_allows_by_default(monkeypatch):
    monkeypatch.setattr(si, "get_subagent_recursion_limit", lambda: 10)
    monkeypatch.setattr(si, "get_subagent_model_name", lambda: None)
    assert si.recursion_guard_error("helper") is None
