from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

from code_puppy.agents._history import (
    _CLEARED_PREFIX,
    clear_stale_tool_results,
)

BIG = "x" * 6000  # well over the default min_tokens threshold
SMALL = "ok"


def _pair(call_id: str, content: str):
    """A tool call (ModelResponse) + its return (ModelRequest)."""
    call = ModelResponse(
        parts=[ToolCallPart(tool_name="read_file", args={}, tool_call_id=call_id)]
    )
    ret = ModelRequest(
        parts=[
            ToolReturnPart(tool_name="read_file", content=content, tool_call_id=call_id)
        ]
    )
    return [call, ret]


def _returns(messages):
    out = []
    for m in messages:
        for p in m.parts:
            if getattr(p, "part_kind", None) == "tool-return":
                out.append(p.content)
    return out


def test_clears_old_keeps_recent():
    messages = []
    for i in range(6):
        messages += _pair(f"c{i}", BIG)

    new, n = clear_stale_tool_results(messages, keep_recent=2, min_tokens=1500)
    assert n == 4
    contents = _returns(new)
    # First 4 stubbed, last 2 preserved verbatim.
    assert all(c.startswith(_CLEARED_PREFIX) for c in contents[:4])
    assert contents[-2:] == [BIG, BIG]


def test_idempotent():
    messages = []
    for i in range(5):
        messages += _pair(f"c{i}", BIG)
    new, n1 = clear_stale_tool_results(messages, keep_recent=1, min_tokens=1500)
    assert n1 == 4
    _, n2 = clear_stale_tool_results(new, keep_recent=1, min_tokens=1500)
    assert n2 == 0


def test_small_results_not_cleared():
    messages = []
    for i in range(6):
        messages += _pair(f"c{i}", SMALL)
    _, n = clear_stale_tool_results(messages, keep_recent=2, min_tokens=1500)
    assert n == 0


def test_pairing_preserved():
    messages = []
    for i in range(4):
        messages += _pair(f"c{i}", BIG)
    new, _ = clear_stale_tool_results(messages, keep_recent=1, min_tokens=1500)
    call_ids = {
        p.tool_call_id for m in new for p in m.parts if p.part_kind == "tool-call"
    }
    ret_ids = {
        p.tool_call_id for m in new for p in m.parts if p.part_kind == "tool-return"
    }
    assert call_ids == ret_ids  # no orphaned calls/returns


def test_nothing_to_clear_when_below_keep():
    messages = _pair("c0", BIG)
    out, n = clear_stale_tool_results(messages, keep_recent=4, min_tokens=1500)
    assert n == 0
    assert out is messages


def test_preserves_non_tool_messages():
    messages = [ModelResponse(parts=[TextPart(content="thinking out loud")])]
    for i in range(5):
        messages += _pair(f"c{i}", BIG)
    new, n = clear_stale_tool_results(messages, keep_recent=1, min_tokens=1500)
    assert n == 4
    assert new[0].parts[0].content == "thinking out loud"
