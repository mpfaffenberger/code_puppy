"""Plugin transforms at the final model-message boundary."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from code_puppy import callbacks
from code_puppy.agents._model_message_transform import build_model_message_transform


@pytest.fixture(autouse=True)
def isolate_callbacks():
    callbacks.clear_callbacks("transform_model_messages")
    yield
    callbacks.clear_callbacks("transform_model_messages")


def _message(content: str) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=content)])


def _contents(messages: list[ModelMessage]) -> list[str]:
    return [
        part.content
        for message in messages
        for part in message.parts
        if isinstance(part, UserPromptPart) and isinstance(part.content, str)
    ]


async def test_callbacks_compose_in_order_and_isolate_failures():
    observed: list[list[str]] = []

    def first(_agent_name, messages):
        messages.append(_message("first"))

    async def broken(_agent_name, _messages):
        raise RuntimeError("broken plugin")

    async def third(_agent_name, messages):
        observed.append(_contents(messages))
        messages.append(_message("third"))

    callbacks.register_callback("transform_model_messages", first)
    callbacks.register_callback("transform_model_messages", broken)
    callbacks.register_callback("transform_model_messages", third)
    messages: list[ModelMessage] = []

    await callbacks.on_transform_model_messages("code-puppy", messages)

    assert observed == [["first"]]
    assert _contents(messages) == ["first", "third"]


async def test_disabled_plugin_callback_is_filtered(monkeypatch):
    callbacks.set_loading_context("disabled-transform")

    def callback(_agent_name, messages):
        messages.append(_message("disabled"))

    callbacks.register_callback("transform_model_messages", callback)
    callbacks.clear_loading_context()
    monkeypatch.setattr(
        callbacks, "_get_disabled_plugins", lambda: {"disabled-transform"}
    )
    messages: list[ModelMessage] = []

    await callbacks.on_transform_model_messages(None, messages)

    assert messages == []


async def test_transform_is_after_history_processing_and_request_only():
    model_requests: list[list[str]] = []
    transformed_agents: list[str | None] = []

    def model(messages, _info):
        model_requests.append(_contents(messages))
        if len(model_requests) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name="continue_run", args={}, tool_call_id="1")
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    def process_history(messages):
        return [_message("history-processed"), *messages]

    async def transform(agent_name, messages):
        transformed_agents.append(agent_name)
        assert "history-processed" in _contents(messages)
        messages.insert(0, _message("transformed"))

    callbacks.register_callback("transform_model_messages", transform)
    agent = Agent(
        FunctionModel(model),
        capabilities=[
            ProcessHistory(process_history),
            build_model_message_transform("code-puppy"),
        ],
    )

    @agent.tool_plain
    def continue_run() -> str:
        return "continue"

    result = await agent.run("start")

    assert transformed_agents == ["code-puppy", "code-puppy"]
    assert all(messages[0] == "transformed" for messages in model_requests)
    assert "transformed" not in _contents(result.all_messages())


async def test_streaming_uses_the_same_request_only_transform():
    called: list[str | None] = []

    def transform(agent_name, messages):
        called.append(agent_name)
        messages.insert(0, _message("transformed"))

    async def handle_events(_ctx, stream):
        async for _event in stream:
            pass

    callbacks.register_callback("transform_model_messages", transform)
    agent = Agent(
        TestModel(custom_output_text="done"),
        capabilities=[build_model_message_transform("code-puppy")],
    )

    result = await agent.run("start", event_stream_handler=handle_events)

    assert called
    assert set(called) == {"code-puppy"}
    assert "transformed" not in _contents(result.all_messages())


class _AgentConfig:
    name = "test-agent"

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
        return "Test instructions"

    def get_available_tools(self):
        return []

    def get_message_history(self):
        return self._message_history

    def set_message_history(self, history):
        self._message_history = history

    def __getattr__(self, item):
        if item.startswith("__"):
            raise AttributeError(item)
        return lambda *_args, **_kwargs: 0


def _load_test_model(*_args, **_kwargs):
    return TestModel(custom_output_text="done"), "test-model"


async def test_main_agent_construction_installs_transform():
    from code_puppy.agents import _builder

    called: list[str | None] = []
    callbacks.register_callback(
        "transform_model_messages",
        lambda agent_name, _messages: called.append(agent_name),
    )
    config = _AgentConfig()
    config.name = "code-puppy"
    with (
        patch.object(_builder, "load_model_with_fallback", _load_test_model),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **_kwargs: []),
        patch.object(_builder, "make_model_settings", lambda *_args, **_kwargs: None),
        patch(
            "code_puppy.tools.register_tools_for_agent", lambda *_args, **_kwargs: None
        ),
    ):
        agent = _builder.build_pydantic_agent(config)
        await agent.run("start")

    assert called
    assert set(called) == {"code-puppy"}


async def test_subagent_construction_installs_transform():
    from code_puppy.tools import subagent_invocation

    called: list[str | None] = []
    callbacks.register_callback(
        "transform_model_messages",
        lambda agent_name, _messages: called.append(agent_name),
    )
    config = _AgentConfig()
    with (
        patch("code_puppy.agents.agent_manager.load_agent", return_value=config),
        patch("code_puppy.agents._builder.load_model_with_fallback", _load_test_model),
        patch(
            "code_puppy.model_factory.make_model_settings",
            lambda *_args, **_kwargs: None,
        ),
        patch("code_puppy.config.get_value", return_value="true"),
    ):
        result = await subagent_invocation._invoke_agent_impl(
            context=SimpleNamespace(), agent_name="test-agent", prompt="start"
        )

    assert result.error is None
    assert called
    assert set(called) == {"test-agent"}
