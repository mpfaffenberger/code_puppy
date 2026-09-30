"""Tests for the flag-switched speculative CodeMode wiring (`code_puppy.agents._code_mode`)."""

import ast
import importlib
import importlib.metadata
import json
import warnings
from importlib.metadata import requires
from unittest.mock import Mock, patch

import pytest
from packaging.requirements import Requirement
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition
from pydantic_ai_harness.code_mode import CodeMode
from pydantic_monty import ResourceLimits

from code_puppy.agents import _code_mode
from code_puppy.agents._code_mode import (
    NATIVE_TOOLS,
    SANDBOXED_READ_ONLY_TOOLS,
    DeclaredSpeculation,
    SilenceToolOutput,
    _sandbox_tool,
    bind_declared_speculation,
    build_speculative_code_mode,
    sandbox_mount_path,
)
from code_puppy.agents._code_mode_guidance import CODE_MODE_GUIDANCE, CodeModeGuidance
from code_puppy.agents._wire_tool_names import StreamedToolNameNormalizer
from code_puppy.agents.agent_code_puppy import CodePuppyAgent
from code_puppy.capabilities.eager_timing import EagerTiming


def _leaves(capability):
    children = getattr(capability, "capabilities", None)
    if children is None:
        return [capability]
    out = []
    for child in children:
        out.extend(_leaves(child))
    return out


@pytest.fixture
def flag(monkeypatch):
    state = {"enabled": True}
    monkeypatch.setattr(
        "code_puppy.agents._code_mode.get_speculative_code_mode_enabled",
        lambda: state["enabled"],
    )
    return state


class TestBuildSpeculativeCodeMode:
    def test_only_native_tools_stay_out_of_run_code(self):
        ctx = Mock(spec=RunContext)
        assert NATIVE_TOOLS == {
            "create_file",
            "replace_in_file",
            "load_image_for_analysis",
        }
        for name in NATIVE_TOOLS:
            assert not _sandbox_tool(ctx, ToolDefinition(name=name))
        for name in (
            *SANDBOXED_READ_ONLY_TOOLS,
            "delete_file",
            "delete_snippet",
            "agent_run_shell_command",
            "some_future_tool",
        ):
            assert _sandbox_tool(ctx, ToolDefinition(name=name))

    def test_disabled_by_config_returns_empty(self, flag):
        flag["enabled"] = False
        assert build_speculative_code_mode(list(SANDBOXED_READ_ONLY_TOOLS)) == []

    def test_no_agent_opt_in_is_required(self, flag):
        """The flag alone decides; there is no per-agent attribute to set."""
        tools = CodePuppyAgent().get_available_tools()

        code_mode, silencer, timing, normalizer, guidance = build_speculative_code_mode(
            tools
        )

        assert isinstance(code_mode, CodeMode)
        assert code_mode.tools is _sandbox_tool
        assert code_mode.eager is True
        assert list(code_mode.speculate) == list(SANDBOXED_READ_ONLY_TOOLS)
        assert isinstance(silencer, SilenceToolOutput)
        assert isinstance(timing, EagerTiming)
        assert isinstance(normalizer, StreamedToolNameNormalizer)
        assert isinstance(guidance, CodeModeGuidance)

    def test_sandbox_gets_workspace_mount_and_os_access(self, flag):
        import os

        code_mode, *_ = build_speculative_code_mode(["read_file"])

        assert code_mode.mount is not None
        # Monty canonicalizes (``\\?\C:\...`` on Windows): compare identity.
        assert os.path.samefile(code_mode.mount.host_path, os.getcwd())
        assert code_mode.mount.virtual_path == sandbox_mount_path(os.getcwd())
        assert code_mode.mount.mode == "read-write"
        assert code_mode.os_access is not None

    def test_guidance_names_the_mount_actually_used(self, flag):
        import os

        code_mode, *_, guidance = build_speculative_code_mode(["read_file"])

        assert guidance.host_path == os.getcwd()
        assert guidance.mount_path == code_mode.mount.virtual_path
        assert f"`{code_mode.mount.virtual_path}`" in guidance.get_instructions()


class TestSandboxMountPath:
    @pytest.mark.parametrize(
        ("host", "mount"),
        [
            ("/home/mike/proj", "/home/mike/proj"),
            (r"C:\Users\mike\proj", "/c/Users/mike/proj"),
            ("D:/work/proj", "/d/work/proj"),
            ("C:\\", "/c"),
            (r"\\server\share\proj", "/server/share/proj"),
        ],
    )
    def test_translates_to_an_absolute_posix_path(self, host, mount):
        assert sandbox_mount_path(host) == mount

    def test_undeclared_tools_are_never_speculated(self, flag):
        """A tool that does not declare ``speculatable`` is never launched early."""
        capability, *_ = build_speculative_code_mode(
            ["read_file", "grep", "some_future_tool"]
        )

        assert capability.tools is _sandbox_tool
        assert list(capability.speculate) == ["read_file", "grep"]


@pytest.mark.asyncio
async def test_run_code_executes_trivial_snippet_with_compatible_monty(flag):
    """Harness 0.35 excludes Monty 1.x, which removed max_duration_secs."""
    assert importlib.metadata.version("pydantic-ai-harness") == "0.35.0"
    monty_requirement = next(
        Requirement(dependency)
        for dependency in requires("code-puppy") or []
        if Requirement(dependency).name == "pydantic-monty"
    )
    assert monty_requirement.specifier.contains("0.0.23")
    assert not monty_requirement.specifier.contains("1.0.0")
    assert "max_duration_secs" in ResourceLimits.__annotations__

    assert "2" in await _run_snippet("1 + 1")


@pytest.mark.asyncio
async def test_sandbox_pathlib_reaches_the_real_workspace(flag):
    """The mount works end to end on this OS (Windows used to crash the build)."""
    import os

    mount = sandbox_mount_path(os.getcwd())
    code = f"import pathlib\npathlib.Path({mount!r} + '/pyproject.toml').exists()"

    assert "True" in await _run_snippet(code)


async def _run_snippet(code: str) -> str:
    """Drive one ``run_code`` call through a real sandbox; return its output."""
    requests = 0

    async def respond(messages, info):
        nonlocal requests
        requests += 1
        if requests == 1:
            args = json.dumps({"code": code})
            yield {0: DeltaToolCall(name="run_code", json_args=args)}
        else:
            yield "done"

    agent = Agent(
        FunctionModel(stream_function=respond),
        capabilities=build_speculative_code_mode([]),
    )
    result = await agent.run("go")
    assert result.output == "done"
    returns = [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "run_code"
    ]
    assert len(returns) == 1
    return str(returns[0].content)


class TestCodeModeGuidance:
    def test_guidance_rides_as_capability_instructions(self):
        text = CodeModeGuidance("/home/p", "/home/p").get_instructions()
        assert text.startswith(CODE_MODE_GUIDANCE)
        assert "`/home/p` (same as the host path)" in text

    def test_translated_mount_explains_both_spellings(self):
        text = CodeModeGuidance(r"C:\p", "/c/p").get_instructions()
        assert "`/c/p` is the host directory `C:\\p`" in text
        assert "take host paths" in text
        assert "takes mount paths" in text

    def test_guidance_does_not_claim_the_real_path_is_mounted(self):
        """False on Windows, where the mount is a POSIX spelling."""
        assert "real absolute path" not in CODE_MODE_GUIDANCE

    def test_guidance_teaches_the_native_write_contract(self):
        assert "run_code" in CODE_MODE_GUIDANCE
        assert "literal" in CODE_MODE_GUIDANCE
        for name in NATIVE_TOOLS:
            assert f"`{name}`" in CODE_MODE_GUIDANCE
        assert "as native tools, outside `run_code`" in CODE_MODE_GUIDANCE
        assert "Speculative Puppy" not in CODE_MODE_GUIDANCE


def test_missing_return_schema_warning_is_silenced_but_collisions_are_not():
    """Schema-less MCP tools are routine; a hidden tool is a real problem."""
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        importlib.reload(_code_mode)

        warnings.warn(
            "CodeMode: tool 'blender_get_screenshot_of_window_as_image' has no "
            "return schema; its signature will show `-> Any`",
            UserWarning,
        )
        assert not captured

        warnings.warn(
            "CodeMode: tool 'a-b' (sanitized to 'a_b') collides with 'a_b'",
            UserWarning,
        )
        assert len(captured) == 1


def test_only_generated_invalid_escape_warnings_are_suppressed():
    """Streaming AST probes must not flood the terminal with SyntaxWarnings."""
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        importlib.reload(_code_mode)

        for _ in range(3):
            ast.parse(r'pattern = "\("')
        assert not captured

        ast.parse(r'pattern = "\("', filename="project_file.py")
        warnings.warn("another syntax warning", SyntaxWarning)
        warnings.warn("runtime warning", RuntimeWarning)

    assert len(captured) == 3
    assert "invalid escape sequence" in str(captured[0].message)
    assert str(captured[1].message) == "another syntax warning"
    assert captured[2].category is RuntimeWarning


class TestDeclaredSpeculation:
    """Tools opt into early launch via ``metadata={"speculatable": True}``."""

    @staticmethod
    def _agent():
        agent = Agent(TestModel())

        @agent.tool_plain(metadata={"speculatable": True})
        def smart_grep(query: str) -> str:
            """A plugin tool that declares itself speculatable."""
            return query

        @agent.tool_plain
        def run_shell(command: str) -> str:
            """Undeclared: must never launch early."""
            return command

        @agent.tool_plain(metadata={"speculatable": "yes"})
        def fuzzy(value: str) -> str:
            """Truthy but not literally True: not a declaration."""
            return value

        return agent

    def test_unbound_is_exactly_the_trio_the_agent_declares(self):
        speculate = DeclaredSpeculation(["read_file", "grep"])
        assert list(speculate) == ["read_file", "grep"]

    def test_bound_adds_declared_tools_only(self):
        speculate = DeclaredSpeculation(["grep"])
        speculate.bind(self._agent())
        assert list(speculate) == ["grep", "smart_grep"]

    async def test_for_run_freezes_the_resolved_allowlist(self, flag):
        code_mode, *_ = build_speculative_code_mode(["grep"])
        agent = self._agent()
        code_mode.speculate.bind(agent)
        clone = await code_mode.for_run(Mock(spec=RunContext))
        assert clone._speculation.allowlist == frozenset({"grep", "smart_grep"})

    def test_bind_finds_code_mode_through_root_capability(self, flag):
        code_mode, *_ = build_speculative_code_mode(["grep"])
        agent = Agent(TestModel(), capabilities=[code_mode])

        @agent.tool_plain(metadata={"speculatable": True})
        def smart_grep(query: str) -> str:
            """Declared."""
            return query

        bind_declared_speculation(agent)
        assert "smart_grep" in list(code_mode.speculate)

    def test_bind_is_a_noop_without_code_mode(self):
        bind_declared_speculation(Agent(TestModel()))  # must not raise


class TestBuilderIntegration:
    def _build(self, agent, register=lambda *_args, **_kwargs: None):
        from code_puppy.agents import _builder

        with (
            patch.object(
                _builder,
                "load_model_with_fallback",
                lambda *_args, **_kwargs: (TestModel(), "test-model"),
            ),
            patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
            patch.object(_builder, "load_mcp_servers", lambda **_kwargs: []),
            patch.object(
                _builder, "make_model_settings", lambda *_args, **_kwargs: None
            ),
            patch("code_puppy.tools.register_tools_for_agent", register),
        ):
            return _builder.build_pydantic_agent(agent)

    def _code_modes(self, pydantic_agent):
        return [
            leaf
            for leaf in _leaves(pydantic_agent._root_capability)
            if isinstance(leaf, CodeMode)
        ]

    def test_any_agent_gets_code_mode_when_flag_is_on(self, flag):
        code_modes = self._code_modes(self._build(CodePuppyAgent()))

        assert len(code_modes) == 1
        # Name, not identity: the warnings test above reloads the module.
        assert code_modes[0].tools.__name__ == _sandbox_tool.__name__
        assert list(code_modes[0].speculate) == list(SANDBOXED_READ_ONLY_TOOLS)

    def test_builder_speculates_registered_plugin_tools(self, flag):
        """Plugin tools arrive via register_agent_tools, never in
        get_available_tools(); the builder must still speculate them."""

        def register(pydantic_agent, *_args, **_kwargs):
            @pydantic_agent.tool_plain(metadata={"speculatable": True})
            def smart_grep(query: str) -> str:
                """Plugin tool."""
                return query

        code_modes = self._code_modes(self._build(CodePuppyAgent(), register))
        assert "smart_grep" in list(code_modes[0].speculate)

    def test_flag_off_keeps_native_tools(self, flag):
        flag["enabled"] = False
        assert not self._code_modes(self._build(CodePuppyAgent()))
