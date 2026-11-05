"""Responses routing gates, not claims about remote model visual perception."""

import base64
import json

import httpx2
import pytest
from pydantic_ai import Agent, BinaryContent, ToolReturn
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models import override_allow_model_requests
from pydantic_ai_harness.code_mode import CodeMode

from code_puppy.agents._code_mode import _sandbox_tool
from code_puppy.model_factory import ModelFactory, _uses_responses_api


IMAGE = b"native-screenshot-contract-fixture"


def config(alias="vision", model_type="custom_openai_responses"):
    return {
        alias: {
            "type": model_type,
            "name": "opaque-server-model",
            "max_retries": 0,
            "custom_endpoint": {
                "url": "https://route.invalid/v1",
                "api_key": "test-only",
            },
        }
    }


def response(output):
    return {
        "id": "resp_contract",
        "object": "response",
        "created_at": 1,
        "model": "opaque-server-model",
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "output": output,
    }


def text_output():
    return {
        "type": "message",
        "id": "msg_contract",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "received", "annotations": []}],
    }


def install_transport(model, handler):
    client = model._provider.client._client
    client._transport = httpx2.MockTransport(handler)
    client._mounts = {}
    # Disable SDK retries so negative tests exercise protocol choice once.
    model._provider.client.max_retries = 0
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capture_name", ["computer_get_app_state", "new_capture_plugin"]
)
async def test_native_tool_image_reaches_responses_wire(capture_name):
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append((request.url.path, payload))
        assert request.url.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer test-only"
        assert payload["model"] == "opaque-server-model"
        if len(requests) == 1:
            names = {tool["name"] for tool in payload["tools"]}
            assert capture_name in names
            assert "run_code" in names
            output = [
                {
                    "type": "function_call",
                    "id": "fc_capture",
                    "call_id": "capture_1",
                    "name": capture_name,
                    "arguments": "{}",
                    "status": "completed",
                }
            ]
        else:
            output = [text_output()]
        return httpx2.Response(200, json=response(output))

    model = ModelFactory.get_model("vision", config())
    client = install_transport(model, handler)
    agent = Agent(model, capabilities=[CodeMode(tools=_sandbox_tool)])

    def capture() -> ToolReturn:
        return ToolReturn(
            return_value={"success": True, "state_revision": "contract-revision"},
            content=[
                "fresh capture",
                BinaryContent(data=IMAGE, media_type="image/png"),
            ],
        )

    agent.tool_plain(capture, name=capture_name, metadata={"code_mode_native": True})
    try:
        with override_allow_model_requests(True):
            result = await agent.run("Capture once")
        assert result.output == "received"
        assert len(requests) == 2
        items = requests[1][1]["input"]
        tool_results = [
            item for item in items if item.get("type") == "function_call_output"
        ]
        assert len(tool_results) == 1
        assert tool_results[0]["call_id"] == "capture_1"
        assert "contract-revision" in tool_results[0]["output"]
        parts = [
            part
            for item in items
            if isinstance(item.get("content"), list)
            for part in item["content"]
        ]
        images = [part for part in parts if part["type"] == "input_image"]
        assert len(images) == 1
        assert images[0]["image_url"] == (
            "data:image/png;base64," + base64.b64encode(IMAGE).decode()
        )
        assert any(part.get("text") == "fresh capture" for part in parts)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 404, 415, 422, 500])
async def test_responses_failure_never_replays_to_chat(status):
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return httpx2.Response(
            status,
            json={
                "error": {
                    "message": "route contract failure",
                    "type": "invalid_request_error",
                }
            },
        )

    model = ModelFactory.get_model("vision", config())
    client = install_transport(model, handler)
    try:
        with override_allow_model_requests(True), pytest.raises(ModelHTTPError):
            await Agent(model).run(
                ["inspect", BinaryContent(data=IMAGE, media_type="image/png")]
            )
        assert requests == ["/v1/responses"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_persisted_extra_models_selects_responses(tmp_path, monkeypatch):
    from code_puppy import callbacks, config as puppy_config, model_factory

    path = tmp_path / "extra_models.json"
    path.write_text(json.dumps(config()), encoding="utf-8")
    monkeypatch.setattr(model_factory, "EXTRA_MODELS_FILE", str(path))
    monkeypatch.setattr(callbacks, "get_callbacks", lambda name: [])
    monkeypatch.setattr(callbacks, "on_load_models_config", lambda: [])
    for name in (
        "CHATGPT_MODELS_FILE",
        "CLAUDE_MODELS_FILE",
        "COPILOT_MODELS_FILE",
        "GEMINI_MODELS_FILE",
    ):
        monkeypatch.setattr(puppy_config, name, str(tmp_path / name))
    # Two independent loads: the contract is on-disk configuration, not a cache.
    for _ in range(2):
        loaded = ModelFactory.load_config()
        assert loaded["vision"] == config()["vision"]
        assert _uses_responses_api("vision", loaded["vision"])
        model = ModelFactory.get_model("vision", loaded)
        assert type(model).__name__ == "OpenAIResponsesModel"
        await model._provider.client.close()


@pytest.mark.parametrize(
    "alias", ["vision", "gpt-5-looking-alias", "codex-gpt-6.1-sol"]
)
@pytest.mark.parametrize("model_type", ["custom_openai", "custom_openai_responses"])
def test_protocol_is_explicit_not_inferred_from_model_alias(alias, model_type):
    entry = config(alias, model_type)[alias]
    assert _uses_responses_api(alias, entry) is (
        model_type == "custom_openai_responses"
    )
