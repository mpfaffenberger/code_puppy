"""Gemini ``thoughtSignature`` round-trip on function calls.

Gemini 3 attaches the signature directly to a ``functionCall`` part when no
thought text precedes it (common at ``thinking_level="low"``), and only to the
first call of a parallel batch. These tests pin that the real signature is
parsed onto the matching ``ToolCallPart`` and replayed on the next request,
instead of being dropped and replaced by the bypass value.
"""

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters

from code_puppy.gemini_code_assist import GeminiCodeAssistModel
from code_puppy.gemini_common import (
    THOUGHT_SIGNATURE_KEY,
    _parse_candidate_parts,
    tool_call_signature,
)
from code_puppy.gemini_model import (
    BYPASS_THOUGHT_SIGNATURE,
    GeminiModel,
    GeminiStreamingResponse,
)

CODE_ASSIST_SKIP = "skip_thought_signature_validator"


def _candidates(*parts):
    return [{"content": {"role": "model", "parts": list(parts)}}]


def _call(name, args=None, signature=None, call_id=None):
    part = {"functionCall": {"name": name, "args": args or {}}}
    if call_id:
        part["functionCall"]["id"] = call_id
    if signature:
        part["thoughtSignature"] = signature
    return part


def _tool_call(name, signature=None, call_id="c1"):
    details = {THOUGHT_SIGNATURE_KEY: signature} if signature else None
    return ToolCallPart(
        tool_name=name, args={}, tool_call_id=call_id, provider_details=details
    )


def _replayed_signatures(content):
    return [
        part.get("thoughtSignature")
        for part in content["parts"]
        if "function_call" in part
    ]


@pytest.fixture
def model():
    return GeminiModel(model_name="gemini-3-flash", api_key="test-key")


@pytest.fixture
def params():
    return ModelRequestParameters(function_tools=[], allow_text_output=True)


class TestParseCandidateParts:
    def test_signature_on_function_call_is_kept(self):
        _, parts = _parse_candidate_parts(
            {}, _candidates(_call("grep", signature="SIG_A"))
        )
        assert tool_call_signature(parts[0]) == "SIG_A"

    def test_parallel_calls_keep_only_their_own_signature(self):
        _, parts = _parse_candidate_parts(
            {},
            _candidates(
                _call("grep", signature="SIG_FIRST", call_id="a"),
                _call("list_files", call_id="b"),
            ),
        )
        assert tool_call_signature(parts[0]) == "SIG_FIRST"
        assert tool_call_signature(parts[1]) is None
        assert parts[1].provider_details is None

    def test_call_without_signature_has_no_provider_details(self):
        _, parts = _parse_candidate_parts({}, _candidates(_call("grep")))
        assert parts[0].provider_details is None


class TestMapModelResponse:
    def test_replays_signature_attached_to_the_call(self, model):
        content = model._map_model_response(
            ModelResponse(parts=[_tool_call("grep", signature="SIG_A")])
        )
        assert _replayed_signatures(content) == ["SIG_A"]

    def test_thinking_signature_still_used_when_call_has_none(self, model):
        response = ModelResponse(
            parts=[ThinkingPart(content="plan", signature="SIG_T"), _tool_call("grep")]
        )
        assert _replayed_signatures(model._map_model_response(response)) == ["SIG_T"]

    def test_call_signature_wins_over_thinking_signature(self, model):
        response = ModelResponse(
            parts=[
                ThinkingPart(content="plan", signature="SIG_T"),
                _tool_call("grep", signature="SIG_CALL"),
            ]
        )
        assert _replayed_signatures(model._map_model_response(response)) == ["SIG_CALL"]

    def test_bypass_only_when_no_signature_exists(self, model):
        content = model._map_model_response(ModelResponse(parts=[_tool_call("grep")]))
        assert _replayed_signatures(content) == [BYPASS_THOUGHT_SIGNATURE]

    def test_parallel_batch_does_not_copy_first_signature(self, model):
        response = ModelResponse(
            parts=[
                _tool_call("grep", signature="SIG_FIRST", call_id="a"),
                _tool_call("list_files", call_id="b"),
            ]
        )
        assert _replayed_signatures(model._map_model_response(response)) == [
            "SIG_FIRST",
            BYPASS_THOUGHT_SIGNATURE,
        ]

    def test_parse_then_map_round_trip(self, model):
        _, parts = _parse_candidate_parts(
            {}, _candidates(_call("grep", signature="SIG_RT"))
        )
        content = model._map_model_response(ModelResponse(parts=parts))
        assert _replayed_signatures(content) == ["SIG_RT"]


async def _stream(chunks):
    async def gen():
        for chunk in chunks:
            yield chunk

    response = GeminiStreamingResponse(
        model_request_parameters=ModelRequestParameters(
            function_tools=[], allow_text_output=True
        ),
        _chunks=gen(),
        _model_name_str="gemini-3-flash",
    )
    async for _ in response:
        pass
    return response.get().parts


class TestStreaming:
    @pytest.mark.asyncio
    async def test_function_call_signature_survives_streaming(self):
        parts = await _stream(
            [{"candidates": _candidates(_call("grep", {"q": "x"}, signature="SIG_S"))}]
        )
        tool_calls = [p for p in parts if isinstance(p, ToolCallPart)]
        assert [tool_call_signature(p) for p in tool_calls] == ["SIG_S"]

    @pytest.mark.asyncio
    async def test_signature_from_first_chunk_survives_later_arg_chunks(self):
        first = _call("grep", signature="SIG_S", call_id="c1")
        first["functionCall"]["partialArgs"] = [
            {"jsonPath": "$.q", "stringValue": "abc"}
        ]
        later = {
            "functionCall": {"partialArgs": [{"jsonPath": "$.d", "stringValue": "."}]}
        }
        parts = await _stream(
            [{"candidates": _candidates(first)}, {"candidates": _candidates(later)}]
        )
        tool_calls = [p for p in parts if isinstance(p, ToolCallPart)]
        assert len(tool_calls) == 1
        assert tool_call_signature(tool_calls[0]) == "SIG_S"

    @pytest.mark.asyncio
    async def test_thinking_signature_survives_streaming(self):
        thought = {"text": "plan", "thought": True, "thoughtSignature": "SIG_T"}
        parts = await _stream([{"candidates": _candidates(thought)}])
        thinking = [p for p in parts if isinstance(p, ThinkingPart)]
        assert thinking[0].signature == "SIG_T"


class TestCodeAssistReplay:
    @pytest.fixture
    def code_assist(self):
        return GeminiCodeAssistModel(
            model_name="gemini-3-flash", access_token="tok", project_id="proj"
        )

    def _function_call_signatures(self, code_assist, params, response):
        messages = [ModelRequest(parts=[UserPromptPart(content="hi")]), response]
        body = code_assist._build_request(messages, None, params)
        model_turn = body["request"]["contents"][-1]
        return [
            part.get("thoughtSignature")
            for part in model_turn["parts"]
            if "functionCall" in part
        ]

    def test_first_call_replays_real_signature(self, code_assist, params):
        response = ModelResponse(
            parts=[
                _tool_call("grep", signature="SIG_A", call_id="a"),
                _tool_call("list_files", call_id="b"),
            ]
        )
        assert self._function_call_signatures(code_assist, params, response) == [
            "SIG_A",
            None,
        ]

    def test_falls_back_to_skip_validator(self, code_assist, params):
        response = ModelResponse(parts=[TextPart(content="ok"), _tool_call("grep")])
        assert self._function_call_signatures(code_assist, params, response) == [
            CODE_ASSIST_SKIP
        ]
