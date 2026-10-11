"""Code mode nudges toward batching: guidance, run_code description, full nested values."""

import json

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_ai.tools import ToolDefinition

from code_puppy.agents import _output_limits
from code_puppy.agents._code_mode import build_speculative_code_mode
from code_puppy.agents._code_mode_guidance import (
    CODE_MODE_GUIDANCE,
    RUN_CODE_BATCHING_NOTE,
    RUN_CODE_TOOL_NAME,
    CodeModeGuidance,
)
from code_puppy.agents._output_limits import (
    build_tool_output_limits,
    reaches_the_model,
)
from code_puppy.tools import file_operations
from code_puppy.tools.file_operations import READ_FILE_TOKEN_GUARD, _read_file

BIG = "needle-" + "x" * 50_000


@pytest.fixture
def code_mode_on(monkeypatch, tmp_path):
    for module in ("_code_mode", "_output_limits"):
        monkeypatch.setattr(
            f"code_puppy.agents.{module}.get_speculative_code_mode_enabled",
            lambda: True,
        )
    monkeypatch.setattr(_output_limits, "get_tool_output_limit_chars", lambda: 10_000)
    monkeypatch.setattr(_output_limits, "CONFIG_DIR", str(tmp_path))


def _tool(name: str) -> ToolDefinition:
    return ToolDefinition(name=name, description=f"{name} description")


class TestGuidance:
    def test_leads_with_batching_over_round_trips(self):
        assert "Write programs, not single calls" in CODE_MODE_GUIDANCE
        for habit in ("Batch:", "Chain:", "Loop:", "Filter in code:"):
            assert habit in CODE_MODE_GUIDANCE

    def test_names_sandbox_gaps_instead_of_promising_glob(self):
        unavailable = CODE_MODE_GUIDANCE.split("NOT available:")[1].split("\n- ")[0]
        for missing in ("`Path.glob`", "`Path.rglob`", "`os.walk`", "`subprocess`"):
            assert missing in unavailable
        assert "write, glob, and stat" not in CODE_MODE_GUIDANCE

    def test_examples_narrow_optional_result_fields(self):
        """The sandbox type checker rejects unnarrowed `str | None` fields.

        An unguarded `sorted({m["file_path"] ...})` in an earlier example
        caused half of all run_code errors in the A/B runs.
        """
        assert 'if m["file_path"]' in CODE_MODE_GUIDANCE
        assert '["content"] or ""' in CODE_MODE_GUIDANCE
        assert '["content"][:' not in CODE_MODE_GUIDANCE

    def test_speculation_no_longer_forbids_computed_arguments(self):
        assert "Loops and computed\narguments are still fine" in CODE_MODE_GUIDANCE
        assert "Never introduce a variable" not in CODE_MODE_GUIDANCE


@pytest.mark.asyncio
async def test_batching_note_rides_on_run_code_only():
    tools = [_tool(RUN_CODE_TOOL_NAME), _tool("create_file")]

    run_code, create_file = await CodeModeGuidance("/p", "/p").prepare_tools(
        None, tools
    )

    assert run_code.description == "run_code description" + RUN_CODE_BATCHING_NOTE
    assert create_file == tools[1]


class TestReachesTheModel:
    @pytest.mark.parametrize("name", [RUN_CODE_TOOL_NAME, "create_file"])
    def test_model_facing_returns_are_bounded(self, name):
        assert reaches_the_model(None, _tool(name))

    def test_sandboxed_returns_stay_whole(self):
        assert not reaches_the_model(None, _tool("read_file"))

    def test_plugin_native_tools_are_bounded(self):
        native = ToolDefinition(name="shot", metadata={"code_mode_native": True})
        assert reaches_the_model(None, native)

    def test_code_mode_off_bounds_everything(self, monkeypatch):
        monkeypatch.setattr(
            _output_limits, "get_speculative_code_mode_enabled", lambda: False
        )
        monkeypatch.setattr(_output_limits, "get_tool_output_limit_chars", lambda: 10)
        (cap,) = build_tool_output_limits()
        assert cap.tool_filter == "all"


class TestReadFileTokenGuard:
    """Whole-file reads: refused natively, whole inside the sandbox."""

    @pytest.fixture
    def big_file(self, tmp_path):
        path = tmp_path / "big.py"
        path.write_text("x = 1\n" * (READ_FILE_TOKEN_GUARD * 4 // 6 + 100))
        return path

    def _set_code_mode(self, monkeypatch, enabled: bool) -> None:
        monkeypatch.setattr(
            file_operations, "get_speculative_code_mode_enabled", lambda: enabled
        )

    def test_native_read_of_huge_file_is_refused(self, monkeypatch, big_file):
        self._set_code_mode(monkeypatch, False)
        out = _read_file(None, str(big_file))
        assert out.content is None
        assert "10,000 tokens" in (out.error or "")

    def test_sandboxed_read_of_huge_file_is_whole(self, monkeypatch, big_file):
        """A refusal there reaches code as `content=None`, read as an empty file."""
        self._set_code_mode(monkeypatch, True)
        out = _read_file(None, str(big_file))
        assert out.error is None
        assert out.content == big_file.read_text()
        assert out.num_tokens > READ_FILE_TOKEN_GUARD

    def test_file_exactly_at_the_guard_validates(self, monkeypatch, tmp_path):
        """The guard refuses only *above* the limit, so the limit itself must fit."""
        self._set_code_mode(monkeypatch, False)
        path = tmp_path / "edge.txt"
        path.write_text("y" * (READ_FILE_TOKEN_GUARD * 4))
        assert _read_file(None, str(path)).num_tokens == READ_FILE_TOKEN_GUARD


async def _run_code_return(code: str) -> str:
    """One ``run_code`` call against a sandboxed ``big_tool``; return its content."""
    requests = 0

    async def respond(messages, info):
        nonlocal requests
        requests += 1
        if requests == 1:
            args = json.dumps({"code": code})
            yield {0: DeltaToolCall(name=RUN_CODE_TOOL_NAME, json_args=args)}
        else:
            yield "done"

    agent = Agent(
        FunctionModel(stream_function=respond),
        capabilities=[*build_tool_output_limits(), *build_speculative_code_mode([])],
    )

    @agent.tool_plain
    def big_tool() -> str:
        return BIG

    result = await agent.run("go")
    (ret,) = [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == RUN_CODE_TOOL_NAME
    ]
    return str(ret.content)


@pytest.mark.asyncio
async def test_nested_results_reach_the_snippet_whole(code_mode_on):
    content = await _run_code_return("r = await big_tool()\nlen(r)")
    assert str(len(BIG)) in content
    assert "stored to handle" not in content


@pytest.mark.asyncio
async def test_run_code_own_oversized_return_is_still_spilled(code_mode_on):
    content = await _run_code_return("await big_tool()")
    assert BIG not in content
    assert "stored to handle" in content
