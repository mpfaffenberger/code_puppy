"""Empty visible reasoning may still carry opaque provider replay state."""

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart

from code_puppy.agents._compaction import _strip_empty_thinking_parts


@pytest.mark.parametrize(
    "state",
    [
        {"signature": "opaque"},
        {"id": "rs_test"},
        {"provider_details": {"opaque": "state"}},
        {"content": "visible"},
    ],
)
@pytest.mark.parametrize("mixed", [False, True])
def test_preserves_each_kind_of_replay_state(state, mixed):
    thinking = ThinkingPart(**{"content": "", **state})
    parts = [thinking, TextPart("answer")] if mixed else [thinking]
    message = ModelResponse(parts=parts)
    cleaned, removed = _strip_empty_thinking_parts([message])
    assert cleaned == [message]
    assert cleaned[0].parts[0] is thinking
    assert removed == 0


@pytest.mark.parametrize("mixed", [False, True])
def test_still_removes_truly_empty_thinking(mixed):
    answer = TextPart("answer")
    parts = [ThinkingPart(content=""), answer] if mixed else [ThinkingPart(content="")]
    cleaned, removed = _strip_empty_thinking_parts([ModelResponse(parts=parts)])
    assert [p for m in cleaned for p in m.parts] == ([answer] if mixed else [])
    assert removed == (0 if mixed else 1)
