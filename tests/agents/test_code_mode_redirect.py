"""run_code failures a retry cannot fix are redirected, not retried to death."""

import json

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelRetry, ToolFailed, UnexpectedModelBehavior
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from code_puppy.agents._code_mode import build_speculative_code_mode
from code_puppy.agents._code_mode_guidance import CODE_MODE_GUIDANCE
from code_puppy.agents._code_mode_redirect import (
    MAX_REDIRECTS,
    SHELL_TOOL_NAME,
    RunCodeRedirect,
    _Failures,
    missing_name,
    redirect_hint,
)

SUBPROCESS_ERROR = (
    "Runtime error:\nTraceback (most recent call last):\n"
    '  File "<python-input-0>", line 1, in <module>\n'
    "    import subprocess as sp\n"
    "ModuleNotFoundError: No module named 'subprocess'"
)


@pytest.fixture
def flag(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.agents._code_mode.get_speculative_code_mode_enabled",
        lambda: True,
    )


class TestMissingName:
    @pytest.mark.parametrize(
        ("message", "name"),
        [
            (SUBPROCESS_ERROR, "subprocess"),
            ("ModuleNotFoundError: No module named 'urllib'", "urllib"),
            ("ModuleNotFoundError: No module named 'a.b'", "a"),
            ("AttributeError: module 'os' has no attribute 'system'", "os.system"),
            ("NameError: name 'x' is not defined", None),
            ("AttributeError: module 'json' has no attribute 'x'", None),
        ],
    )
    def test_reads_the_missing_module(self, message, name):
        assert missing_name(message) == name


class TestRedirectHint:
    @pytest.mark.parametrize("name", ["subprocess", "os.system", "os.popen"])
    def test_processes_go_to_the_shell_tool(self, name):
        hint = redirect_hint(name, SHELL_TOOL_NAME)
        assert f"await {SHELL_TOOL_NAME}(command=" in hint
        assert "Do not resend the same code." in hint

    def test_network_goes_to_curl(self):
        assert "`curl`" in redirect_hint("socket", SHELL_TOOL_NAME)

    def test_other_modules_go_to_the_tool_functions(self):
        assert "`read_file`" in redirect_hint("shutil", SHELL_TOOL_NAME)

    def test_without_a_shell_tool_none_is_promised(self):
        hint = redirect_hint("subprocess", None)
        assert SHELL_TOOL_NAME not in hint
        assert "no shell tool" in hint


class TestFailures:
    def test_first_missing_module_is_a_retry_with_the_redirect(self):
        answer = _Failures().answer("import subprocess", SUBPROCESS_ERROR, "sh")
        assert isinstance(answer, ModelRetry)
        assert answer.message.startswith(SUBPROCESS_ERROR)
        assert "await sh(command=" in answer.message

    def test_same_missing_module_again_is_final_even_in_other_code(self):
        failures = _Failures()
        failures.answer("import subprocess", SUBPROCESS_ERROR, "sh")
        answer = failures.answer(
            "import subprocess as s\ns.run([])", SUBPROCESS_ERROR, "sh"
        )
        assert isinstance(answer, ToolFailed)
        assert "not retried" in answer.message

    def test_identical_snippet_and_error_is_final(self):
        failures = _Failures()
        error = "File \"<python-input-{}>\", line 1\nKeyError: 'x'"
        assert isinstance(failures.answer("d['x']", error.format(0), "sh"), ModelRetry)
        # Only the feed number differs, and whitespace does not count.
        answer = failures.answer("d['x'] \n", error.format(1), "sh")
        assert isinstance(answer, ToolFailed)

    def test_a_changed_snippet_still_gets_its_retry(self):
        failures = _Failures()
        failures.answer("d['x']", "KeyError: 'x'", "sh")
        assert isinstance(failures.answer("d['y']", "KeyError: 'x'", "sh"), ModelRetry)

    def test_redirects_are_capped_so_the_retry_budget_still_ends_a_loop(self):
        failures = _Failures()
        answers = [
            failures.answer("import subprocess", SUBPROCESS_ERROR, "sh")
            for _ in range(MAX_REDIRECTS + 2)
        ]
        assert [type(a) for a in answers] == [
            ModelRetry,
            *[ToolFailed] * MAX_REDIRECTS,
            ModelRetry,
        ]


class TestWiring:
    def test_names_the_shell_tool_only_when_the_agent_has_it(self, flag):
        def redirect(tools):
            return next(
                c
                for c in build_speculative_code_mode(tools)
                if isinstance(c, RunCodeRedirect)
            )

        assert redirect([SHELL_TOOL_NAME]).shell_tool == SHELL_TOOL_NAME
        assert redirect(["read_file"]).shell_tool is None

    def test_guidance_names_the_missing_process_and_network_calls(self):
        for name in ("`os.system`", "`os.popen`", "`socket`"):
            assert name in CODE_MODE_GUIDANCE


def _model_sending(snippets):
    """A model that sends each snippet in turn as `run_code`, then answers."""
    requests = 0

    async def respond(messages, info):
        nonlocal requests
        requests += 1
        if requests <= len(snippets):
            args = json.dumps({"code": snippets[requests - 1]})
            yield {0: DeltaToolCall(name="run_code", json_args=args)}
        else:
            yield "done"

    return FunctionModel(stream_function=respond)


def _run_code_returns(result):
    return [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "run_code"
    ]


@pytest.mark.asyncio
async def test_repeated_blocked_import_no_longer_kills_the_run(flag):
    """Three identical `import subprocess` snippets used to exhaust the retries."""
    agent = Agent(
        _model_sending(["import subprocess as sp"] * 3),
        capabilities=build_speculative_code_mode([SHELL_TOOL_NAME]),
    )

    result = await agent.run("go")

    assert result.output == "done"
    returns = _run_code_returns(result)
    assert [r.outcome for r in returns] == ["retried", "failed", "failed"]
    assert f"await {SHELL_TOOL_NAME}(command=" in str(returns[0].content)


@pytest.mark.asyncio
async def test_a_model_that_ignores_every_redirect_still_stops(flag):
    agent = Agent(
        _model_sending(["import subprocess as sp"] * 20),
        capabilities=build_speculative_code_mode([SHELL_TOOL_NAME]),
    )

    with pytest.raises(UnexpectedModelBehavior, match="exceeded max retries"):
        await agent.run("go")
