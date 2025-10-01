"""Tests for reasoning_effort wiring in BaseAgent reload."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from code_puppy.agents.agent_code_puppy import CodePuppyAgent
from code_puppy.model_factory import (
    DEFAULT_REASONING_EFFORT,
    _normalize_reasoning_effort,
)


@dataclass
class FakeModelSettings:
    kwargs: Dict[str, Any]


@dataclass
class FakeOpenAIModelSettings:
    kwargs: Dict[str, Any]


class FakePydanticAgent:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs
        FakePydanticAgent.instances.append(self)


FakePydanticAgent.instances: List[FakePydanticAgent] = []


def _run_reload(
    monkeypatch: pytest.MonkeyPatch,
    *,
    model_type: str,
    reasoning_effort: Optional[str],
) -> Dict[str, Any]:
    FakePydanticAgent.instances.clear()

    def fake_load_config() -> Dict[str, Dict[str, Any]]:
        model_config: Dict[str, Any] = {"type": model_type}
        if reasoning_effort is not None:
            model_config["reasoning_effort"] = reasoning_effort
        model_config["reasoning_effort"] = _normalize_reasoning_effort(
            "test-model",
            model_config,
        )
        return {"test-model": model_config}

    def fake_get_model(*_args: Any, **_kwargs: Any) -> object:
        return object()

    fake_model_settings_calls: List[FakeModelSettings] = []
    fake_openai_settings_calls: List[FakeOpenAIModelSettings] = []

    def fake_model_settings(**kwargs: Any) -> FakeModelSettings:
        call = FakeModelSettings(kwargs)
        fake_model_settings_calls.append(call)
        return call

    def fake_openai_settings(**kwargs: Any) -> FakeOpenAIModelSettings:
        call = FakeOpenAIModelSettings(kwargs)
        fake_openai_settings_calls.append(call)
        return call

    def fake_register_tools(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "code_puppy.agents.base_agent.ModelFactory.load_config",
        staticmethod(fake_load_config),
    )
    monkeypatch.setattr(
        "code_puppy.agents.base_agent.ModelFactory.get_model",
        staticmethod(fake_get_model),
    )
    monkeypatch.setattr(
        "code_puppy.agents.base_agent.ModelSettings", fake_model_settings
    )
    monkeypatch.setattr(
        "code_puppy.agents.base_agent.OpenAIModelSettings", fake_openai_settings
    )
    monkeypatch.setattr(
        "code_puppy.agents.base_agent.PydanticAgent", FakePydanticAgent
    )
    monkeypatch.setattr(
        "code_puppy.agents.base_agent.BaseAgent.get_model_context_length",
        lambda self: 100_000,
    )
    monkeypatch.setattr(
        "code_puppy.agents.base_agent.BaseAgent.load_mcp_servers", lambda self: []
    )
    monkeypatch.setattr(
        "code_puppy.agents.base_agent.BaseAgent.load_puppy_rules", lambda self: None
    )
    monkeypatch.setattr(CodePuppyAgent, "get_model_name", lambda self: "test-model")
    monkeypatch.setattr(CodePuppyAgent, "get_system_prompt", lambda self: "prompt")
    monkeypatch.setattr(
        "code_puppy.agents.base_agent.console.print", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "code_puppy.tools.register_tools_for_agent", fake_register_tools
    )

    agent = CodePuppyAgent()
    agent.reload_code_generation_agent()

    result = {
        "openai_calls": fake_openai_settings_calls,
        "model_calls": fake_model_settings_calls,
        "agent_instances": FakePydanticAgent.instances.copy(),
    }
    return result


@pytest.mark.parametrize(
    "model_type,reasoning,expected",
    [
        ("openrouter", "high", "high"),
        ("custom_openai", "weird", DEFAULT_REASONING_EFFORT),
    ],
)
def test_openai_compatible_models_apply_reasoning(
    monkeypatch: pytest.MonkeyPatch,
    model_type: str,
    reasoning: Optional[str],
    expected: str,
) -> None:
    outcome = _run_reload(monkeypatch, model_type=model_type, reasoning_effort=reasoning)

    assert len(outcome["openai_calls"]) == 1
    assert outcome["model_calls"] == []
    call_kwargs = outcome["openai_calls"][0].kwargs
    assert call_kwargs["openai_reasoning_effort"] == expected


def test_non_openai_models_skip_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    outcome = _run_reload(
        monkeypatch,
        model_type="anthropic",
        reasoning_effort="high",
    )

    assert outcome["openai_calls"] == []
    assert len(outcome["model_calls"]) == 1
    assert "openai_reasoning_effort" not in outcome["model_calls"][0].kwargs
