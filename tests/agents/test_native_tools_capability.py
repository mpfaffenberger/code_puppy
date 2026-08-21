"""Contract tests for the ``NativeTools`` capability.

Pins the promotion of native tool delivery from post-construction
``@agent.tool`` registration (``register_tools_for_agent(pydantic_agent, ...)``)
to a first-class pydantic-ai capability riding the ``get_toolset()`` seam.

Feature-parity checklist covered here:

- registry semantics (expansion, unknown-tool skip) flow through unchanged,
  because ``build_native_toolset`` delegates to ``register_tools_for_agent``;
- per-tool schema/retry metadata is identical between the old and new
  registration targets (``Agent.tool`` vs ``FunctionToolset.tool``);
- capability-delivered tools genuinely dispatch through ``Agent.run()``;
- the builder delivers tools ONLY via the capability (the agent's internal
  function toolset stays empty -- the one observable divergence);
- MCP collision filtering now works off the native toolset's names (the old
  probe introspected ``probe_agent._tools``, removed in pydantic-ai v2, so
  the filter had silently become a no-op);
- ``_extract_pydantic_agent_tools`` (context-overhead estimators) finds
  tools in both the capability shape and the legacy shape.
"""

from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset

from code_puppy.agents._native_tools import NativeTools, build_native_toolset
from code_puppy.agents.base_agent import _extract_pydantic_agent_tools


class _FakeAgentConfig:
    """Minimal BaseAgent-shaped config for driving the real build paths."""

    name = "test-puppy"
    display_name = "Test Puppy"

    def __init__(self, tools=None):
        self._message_history = []
        self._compacted_message_hashes = set()
        self._puppy_rules = None
        self._tools = list(tools or [])

    @contextmanager
    def temporary_model_name_override(self, _model_name):
        yield

    def get_model_name(self):
        return "test-model"

    def get_full_system_prompt(self):
        return "You are a test agent."

    def get_available_tools(self):
        return list(self._tools)

    def get_message_history(self):
        return self._message_history

    def set_message_history(self, history):
        self._message_history = history

    def __getattr__(self, item):
        # Misc numeric config probes used by history processors.
        if item.startswith("__"):
            raise AttributeError(item)
        return lambda *a, **k: 0


def _fake_load_model_with_fallback(*_args, **_kwargs):
    return TestModel(custom_output_text="woof", call_tools=[]), "test-model"


@contextmanager
def _builder_patches(*extra):
    from code_puppy.agents import _builder

    patches = (
        patch.object(
            _builder, "load_model_with_fallback", _fake_load_model_with_fallback
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "make_model_settings", lambda *a, **k: None),
        *extra,
    )
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield


# ---------------------------------------------------------------------------
# build_native_toolset: registry semantics ride through unchanged
# ---------------------------------------------------------------------------


def test_build_native_toolset_registers_requested_tools():
    toolset = build_native_toolset(["read_file", "list_files"])
    assert "read_file" in toolset.tools
    assert "list_files" in toolset.tools


def test_edit_file_expansion_preserved():
    """The deprecated compound tool expands; the original is not registered."""
    toolset = build_native_toolset(["edit_file"])
    assert "edit_file" not in toolset.tools
    for expanded in ("create_file", "replace_in_file", "delete_snippet"):
        assert expanded in toolset.tools


def test_unknown_tool_skipped_not_raised():
    toolset = build_native_toolset(["__no_such_tool__", "read_file"])
    assert "read_file" in toolset.tools
    assert "__no_such_tool__" not in toolset.tools


# ---------------------------------------------------------------------------
# NativeTools contract
# ---------------------------------------------------------------------------


def test_get_toolset_returns_toolset_when_populated():
    toolset = build_native_toolset(["read_file"])
    cap = NativeTools(toolset)
    assert cap.get_toolset() is toolset


def test_get_toolset_inert_when_empty():
    """A tool-less agent contributes no toolset at all -- same chain as the
    old registration path, which likewise added nothing."""
    cap = NativeTools(FunctionToolset())
    assert cap.get_toolset() is None


def test_serialization_name_opt_out():
    assert NativeTools.get_serialization_name() is None


def test_tool_metadata_parity_with_agent_tool_registration():
    """``Agent.tool`` and ``FunctionToolset.tool`` must produce identical
    per-tool metadata for the same register function."""
    from code_puppy.tools.file_operations import register_read_file

    legacy_agent = Agent(model=None, retries=3)
    register_read_file(legacy_agent)
    toolset = build_native_toolset(["read_file"])

    legacy_tool = legacy_agent._function_toolset.tools["read_file"]
    cap_tool = toolset.tools["read_file"]

    assert legacy_tool.name == cap_tool.name
    assert legacy_tool.description == cap_tool.description
    assert legacy_tool.takes_ctx == cap_tool.takes_ctx
    # Both leave the per-tool budget unset, deferring to the agent-level
    # ``retries`` at get_tools time -- the retry-parity linchpin.
    assert legacy_tool.max_retries is None
    assert cap_tool.max_retries is None


@pytest.mark.asyncio
async def test_capability_tool_dispatches_through_agent_run():
    """Real framework dispatch: a capability-delivered tool executes."""
    calls = []
    toolset = FunctionToolset()

    @toolset.tool
    def fetch_stick(ctx: RunContext, length: int) -> str:
        """Fetch a stick of the given length."""
        calls.append(length)
        return f"stick[{length}]"

    agent = Agent(
        model=TestModel(),
        retries=3,
        capabilities=[NativeTools(toolset)],
    )
    result = await agent.run("fetch!")
    assert calls, "capability-delivered tool was never executed"
    assert "stick[" in result.output


# ---------------------------------------------------------------------------
# Builder integration: main-agent path
# ---------------------------------------------------------------------------


def test_builder_delivers_tools_via_capability_only():
    from code_puppy.agents import _builder

    cfg = _FakeAgentConfig(tools=["read_file"])
    with _builder_patches(patch.object(_builder, "load_mcp_servers", lambda **k: [])):
        built = _builder.build_pydantic_agent(cfg)

    # The one observable divergence, pinned: the agent's internal function
    # toolset stays empty; tools live in the capability toolset.
    assert built._function_toolset.tools == {}
    extracted = _extract_pydantic_agent_tools(built)
    assert extracted is not None and "read_file" in extracted


@pytest.mark.asyncio
async def test_builder_collision_filter_hides_mcp_duplicate():
    """MCP tools shadowing native names are filtered; unique ones survive.

    On main the filter was inert (``probe_agent._tools`` no longer exists in
    pydantic-ai v2), so a genuine collision would have raised a conflict
    error at run time. Sourcing names from the native toolset restores the
    documented behaviour.
    """
    from code_puppy.agents import _builder

    mcp_like = FunctionToolset()

    @mcp_like.tool
    def read_file(ctx: RunContext, path: str) -> str:
        """Colliding MCP tool -- must be hidden."""
        return "mcp"

    @mcp_like.tool
    def unique_mcp_tool(ctx: RunContext) -> str:
        """Non-colliding MCP tool -- must stay visible."""
        return "mcp"

    cfg = _FakeAgentConfig(tools=["read_file"])
    with _builder_patches(
        patch.object(_builder, "load_mcp_servers", lambda **k: [mcp_like])
    ):
        built = _builder.build_pydantic_agent(cfg)

    model = TestModel(custom_output_text="woof", call_tools=[])
    result = await built.run("hi", model=model)
    assert result.output == "woof"

    visible = [t.name for t in model.last_model_request_parameters.function_tools]
    # Membership (not equality): harness capabilities contribute their own
    # tools (e.g. ToolOutputLimits' read_tool_result).
    assert "unique_mcp_tool" in visible
    # Exactly one read_file: the native one; the MCP shadow was filtered
    # (a surviving duplicate would have raised before we got here).
    assert visible.count("read_file") == 1


def test_probe_builder_tools_countable():
    """The stripped probe used by context estimators still exposes tools."""
    from code_puppy.agents import _builder

    cfg = _FakeAgentConfig(tools=["read_file", "list_files"])
    with _builder_patches():
        probe = _builder.build_tool_probe_for_agent(cfg)

    assert probe is not None
    extracted = _extract_pydantic_agent_tools(probe)
    assert extracted is not None
    assert {"read_file", "list_files"} <= set(extracted)


# ---------------------------------------------------------------------------
# Builder integration: sub-agent path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subagent_path_delivers_tools_via_capability():
    from code_puppy.tools import subagent_invocation as si

    cfg = _FakeAgentConfig(tools=["read_file"])
    captured = {}

    def capture_wrap(_agent_config, pydantic_agent, **_kwargs):
        captured["agent"] = pydantic_agent
        return pydantic_agent

    with (
        patch("code_puppy.agents.agent_manager.load_agent", return_value=cfg),
        patch(
            "code_puppy.agents._builder.load_model_with_fallback",
            _fake_load_model_with_fallback,
        ),
        patch("code_puppy.model_factory.make_model_settings", lambda *a, **k: None),
        patch("code_puppy.config.get_value", return_value="true"),  # no MCP
        patch.object(si, "on_wrap_pydantic_agent", capture_wrap),
    ):
        out = await si._invoke_agent_impl(
            context=SimpleNamespace(),
            agent_name="test-puppy",
            prompt="fetch me a stick",
        )

    assert out.error is None
    built = captured["agent"]
    assert built._function_toolset.tools == {}
    extracted = _extract_pydantic_agent_tools(built)
    assert extracted is not None and "read_file" in extracted


# ---------------------------------------------------------------------------
# _extract_pydantic_agent_tools: both shapes
# ---------------------------------------------------------------------------


def test_extractor_still_handles_legacy_agent_tool_registration():
    agent = Agent(model=None, retries=3)

    @agent.tool
    def legacy_tool(ctx: RunContext, x: int) -> str:
        """A tool registered the old way."""
        return str(x)

    extracted = _extract_pydantic_agent_tools(agent)
    assert extracted is not None and "legacy_tool" in extracted


def test_extractor_none_for_none_agent():
    assert _extract_pydantic_agent_tools(None) is None
