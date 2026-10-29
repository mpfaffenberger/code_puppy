"""The Anthropic SDK stays off the startup path and loads on first real use."""

import os
import subprocess
import sys
from pathlib import Path

from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from code_puppy.agents._foreign_thinking import strip_foreign_thinking

REPO_ROOT = Path(__file__).resolve().parents[1]

LOADED_ANTHROPIC = (
    "import sys; print(sorted(m for m in sys.modules if m == 'anthropic' "
    "or m.startswith(('anthropic.', 'pydantic_ai.models.anthropic', "
    "'pydantic_ai.providers.anthropic'))))"
)


def _run_in_clean_interpreter(code: str, home: Path) -> str:
    env = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PYTHONPATH": str(REPO_ROOT),
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=home,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    return result.stdout.strip()


def test_pre_prompt_import_does_not_load_anthropic_sdk(tmp_path):
    output = _run_in_clean_interpreter(
        f"import code_puppy.main; {LOADED_ANTHROPIC}", tmp_path
    )

    assert output == "[]"


def test_non_anthropic_model_does_not_load_anthropic_sdk(tmp_path):
    code = (
        "from pydantic_ai.messages import ModelResponse\n"
        "from pydantic_ai.models.function import FunctionModel\n"
        "from code_puppy.agents._foreign_thinking import strip_foreign_thinking\n"
        "model = FunctionModel(lambda _m, _i: ModelResponse(parts=[]))\n"
        "strip_foreign_thinking([], model)\n"
        f"{LOADED_ANTHROPIC}"
    )

    assert _run_in_clean_interpreter(code, tmp_path) == "[]"


def test_anthropic_model_loads_sdk_on_first_use_and_still_strips(tmp_path):
    code = (
        "from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart\n"
        "from pydantic_ai.models.anthropic import AnthropicModel\n"
        "from pydantic_ai.providers.anthropic import AnthropicProvider\n"
        "from code_puppy.agents._foreign_thinking import strip_foreign_thinking\n"
        "model = AnthropicModel('claude-sonnet-5', "
        "provider=AnthropicProvider(api_key='offline'))\n"
        "foreign = ThinkingPart('gemini', signature='g', provider_name='google')\n"
        "messages = [ModelResponse(parts=[foreign, TextPart('done')])]\n"
        "cleaned = strip_foreign_thinking(messages, model)\n"
        "print(cleaned[0].parts == [TextPart('done')])\n"
        "import sys; print('anthropic' in sys.modules)\n"
    )

    assert _run_in_clean_interpreter(code, tmp_path).splitlines() == [
        "True",
        "True",
    ]


def test_wrapped_anthropic_model_still_strips_foreign_thinking():
    model = WrapperModel(
        AnthropicModel("claude-sonnet-5", provider=AnthropicProvider(api_key="offline"))
    )
    foreign = ThinkingPart("gemini", signature="g", provider_name="google")
    messages = [ModelResponse(parts=[foreign, TextPart("done")])]

    cleaned = strip_foreign_thinking(messages, model)

    assert cleaned[0].parts == [TextPart("done")]


def test_non_anthropic_history_is_passed_through_unchanged():
    model = FunctionModel(lambda _m, _i: ModelResponse(parts=[]))
    messages = [ModelResponse(parts=[ThinkingPart("x", provider_name="google")])]

    assert strip_foreign_thinking(messages, model) is messages
