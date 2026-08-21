"""Contract tests for the ``McpToolsets`` capability.

Pins the parity story for moving MCP server delivery off the
``Agent(toolsets=...)`` constructor kwarg and onto the ``get_toolset()``
capability seam:

* normalization matches the kwarg byte-for-byte (AbstractToolsets kept in
  order, non-toolsets wrapped in ``DynamicToolset`` and appended after);
* the delivered toolsets surface through the public ``agent.toolsets``
  property (what the DBOS durable wrapper reads);
* ``Agent.override(toolsets=...)`` replaces capability toolsets exactly as
  it replaced constructor toolsets (what DBOS relies on per run);
* ``Agent.__aenter__`` enters the delivered toolset (MCP lifecycle);
* tools delivered via the capability are actually callable end-to-end.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import CombinedToolset, DynamicToolset, FunctionToolset

from code_puppy.agents._mcp_toolsets import McpToolsets


class _EnterCountingToolset(FunctionToolset):
    """FunctionToolset that counts async-context enters/exits."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enter_count = 0
        self.exit_count = 0

    async def __aenter__(self):
        self.enter_count += 1
        return await super().__aenter__()

    async def __aexit__(self, *exc_info):
        self.exit_count += 1
        return await super().__aexit__(*exc_info)


def _echo_toolset(tool_name: str = "mcp_echo") -> FunctionToolset:
    toolset = FunctionToolset()

    def echo(text: str) -> str:
        """Echo text back."""
        return f"echo: {text}"

    toolset.add_function(echo, takes_ctx=False, name=tool_name)
    return toolset


# ---------------------------------------------------------------------------
# Pure capability contract
# ---------------------------------------------------------------------------


def test_empty_servers_deliver_no_toolset():
    assert McpToolsets([]).get_toolset() is None
    assert McpToolsets().get_toolset() is None


def test_single_server_delivered_by_identity():
    server = _echo_toolset()
    assert McpToolsets([server]).get_toolset() is server


def test_multiple_servers_combined_in_order():
    first, second = _echo_toolset("one"), _echo_toolset("two")
    delivered = McpToolsets([first, second]).get_toolset()
    assert isinstance(delivered, CombinedToolset)
    assert list(delivered.toolsets) == [first, second]


def test_non_toolset_entries_wrapped_dynamic_and_appended_after():
    """Parity with ``Agent(toolsets=...)``: AbstractToolsets first (in
    order), everything else wrapped in DynamicToolset after them."""

    def factory(_ctx):  # a ToolsetFunc, as the kwarg accepted
        return None

    static = _echo_toolset()
    delivered = McpToolsets([factory, static]).get_toolset()
    assert isinstance(delivered, CombinedToolset)
    inner = list(delivered.toolsets)
    assert inner[0] is static
    assert isinstance(inner[1], DynamicToolset)


def test_get_toolset_is_stable_across_calls():
    capability = McpToolsets([_echo_toolset("one"), _echo_toolset("two")])
    assert capability.get_toolset() is capability.get_toolset()


def test_not_spec_constructible():
    assert McpToolsets.get_serialization_name() is None


# ---------------------------------------------------------------------------
# pydantic-ai integration parity
# ---------------------------------------------------------------------------


def _toolset_leaves(agent: Agent) -> list:
    """Collect leaf toolsets reachable from ``agent.toolsets``.

    Walks the same wrapper chain DBOS's ``visit_and_replace`` recurses
    through (``CombinedToolset.toolsets`` / ``WrapperToolset.wrapped``), so
    membership here proves the durable wrapper can find and dbosify the
    delivered MCP toolsets.
    """
    leaves = []

    def walk(toolset):
        children = getattr(toolset, "toolsets", None)
        if children is not None:
            for child in children:
                walk(child)
        elif (wrapped := getattr(toolset, "wrapped", None)) is not None:
            walk(wrapped)
        else:
            leaves.append(toolset)

    for toolset in agent.toolsets:
        walk(toolset)
    return leaves


def _build_agent(servers, **kwargs) -> Agent:
    return Agent(
        model=TestModel(custom_output_text="woof"),
        name="cap-test",
        capabilities=[McpToolsets(servers)],
        **kwargs,
    )


def test_delivered_toolsets_surface_on_public_property():
    """DBOSAgent reads ``wrapped.toolsets`` and dbosifies via
    ``visit_and_replace`` — the capability-delivered server must be a
    reachable leaf of that public property."""
    server = _echo_toolset()
    agent = _build_agent([server])
    assert any(leaf is server for leaf in _toolset_leaves(agent))


def test_delivered_toolsets_visit_and_replaceable():
    """The exact traversal DBOSAgent performs reaches the MCP leaf."""
    server = _echo_toolset()
    agent = _build_agent([server])
    visited = []

    def visitor(leaf):
        visited.append(leaf)
        return leaf

    for toolset in agent.toolsets:
        toolset.visit_and_replace(visitor)
    assert any(leaf is server for leaf in visited)


def test_override_toolsets_replaces_capability_toolsets():
    """Same replace semantics the kwarg had — DBOS overrides per run."""
    server = _echo_toolset()
    replacement = _echo_toolset("replacement_tool")
    agent = _build_agent([server])
    with agent.override(toolsets=[replacement]):
        toolsets = agent.toolsets
        assert all(ts is not server for ts in toolsets)
        assert any(ts is replacement for ts in toolsets)


async def test_aenter_enters_delivered_toolset():
    server = _EnterCountingToolset()
    agent = _build_agent([server])
    async with agent:
        assert server.enter_count == 1
    assert server.exit_count == 1
    # Re-entrancy stays a no-op inside one entered context, as before.
    async with agent:
        async with agent:
            pass
    assert server.enter_count == 2
    assert server.exit_count == 2


async def test_capability_delivered_tool_is_callable_end_to_end():
    """The model can call a tool that only exists via McpToolsets."""

    def model_function(messages, info: AgentInfo) -> ModelResponse:
        assert any(t.name == "mcp_echo" for t in info.function_tools)
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="mcp_echo", args={"text": "woof"})]
            )
        tool_return = messages[-1].parts[0]
        return ModelResponse(parts=[TextPart(f"got {tool_return.content}")])

    agent = Agent(
        model=FunctionModel(model_function),
        name="cap-test",
        capabilities=[McpToolsets([_echo_toolset()])],
    )
    result = await agent.run("hi")
    assert result.output == "got echo: woof"


# ---------------------------------------------------------------------------
# Builder integration: the real construction path delivers via the capability
# ---------------------------------------------------------------------------


class _FakeAgentConfig:
    """Minimal BaseAgent-shaped config (pattern from test_agent_span_naming)."""

    name = "code-puppy"
    display_name = "Code Puppy"

    def __init__(self):
        self._message_history = []
        self._compacted_message_hashes = set()
        self._puppy_rules = None

    @contextmanager
    def temporary_model_name_override(self, _model_name):
        yield

    def get_model_name(self):
        return "test-model"

    def get_full_system_prompt(self):
        return "You are a test agent."

    def get_available_tools(self):
        return []

    def get_message_history(self):
        return self._message_history

    def set_message_history(self, history):
        self._message_history = history

    def __getattr__(self, item):
        if item.startswith("__"):
            raise AttributeError(item)
        return lambda *a, **k: 0


def _build_with_servers(servers):
    from code_puppy.agents import _builder

    cfg = _FakeAgentConfig()
    with (
        patch.object(
            _builder,
            "load_model_with_fallback",
            lambda *a, **k: (TestModel(custom_output_text="woof"), "test-model"),
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **k: servers),
        patch.object(_builder, "make_model_settings", lambda *a, **k: None),
        patch("code_puppy.tools.register_tools_for_agent", lambda *a, **k: None),
    ):
        return _builder.build_pydantic_agent(cfg), cfg


def test_builder_delivers_mcp_servers_via_capability():
    server = _echo_toolset()
    built, cfg = _build_with_servers([server])
    assert not built._user_toolsets  # nothing rides the kwarg any more
    assert any(leaf is server for leaf in _toolset_leaves(built))
    # The plugin-facing attribute contract is unchanged.
    assert cfg._mcp_servers == [server]


def test_builder_collision_filter_still_applies():
    """A server tool colliding with a registered tool is hidden, exactly as
    the pre-capability two-pass filter guaranteed."""
    from code_puppy.agents import _builder

    server = _echo_toolset("read_file")

    def fake_register(agent, *_a, **_k):
        # Simulate the registry contributing a colliding native tool name.
        agent._tools = {"read_file": SimpleNamespace()}

    cfg = _FakeAgentConfig()
    with (
        patch.object(
            _builder,
            "load_model_with_fallback",
            lambda *a, **k: (TestModel(custom_output_text="woof"), "test-model"),
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **k: [server]),
        patch.object(_builder, "make_model_settings", lambda *a, **k: None),
        patch("code_puppy.tools.register_tools_for_agent", fake_register),
    ):
        built = _builder.build_pydantic_agent(cfg)

    delivered = built.root_capability.get_toolset()
    assert delivered is not None
    assert delivered is not server  # the FilteredToolset wrapper rode along
