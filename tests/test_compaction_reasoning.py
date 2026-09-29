from pydantic_ai.messages import ModelResponse, ThinkingPart

from code_puppy.agents._compaction import _strip_empty_thinking_parts


def test_preserve_empty_signed_thinking_part():
    message = ModelResponse(
        [ThinkingPart(content="", id="rs_1", signature="encrypted")]
    )

    cleaned, filtered = _strip_empty_thinking_parts([message])

    assert cleaned == [message]
    assert filtered == 0


def test_remove_empty_unsigned_thinking_part():
    message = ModelResponse([ThinkingPart(content="", id="rs_1")])

    cleaned, filtered = _strip_empty_thinking_parts([message])

    assert cleaned == []
    assert filtered == 1
