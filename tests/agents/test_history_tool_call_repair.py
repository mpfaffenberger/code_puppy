"""Part-granularity repair of mismatched tool call/return pairing.

``prune_interrupted_tool_calls`` must never erase completed sibling calls that
share an assistant turn with an interrupted one (issue #782).
"""

from pydantic_ai.messages import (
    INTERRUPTED_TOOL_RETURN_CONTENT,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from code_puppy.agents._history import (
    has_pending_tool_calls,
    prune_interrupted_tool_calls,
)


def _call(call_id: str, name: str = "edit") -> ToolCallPart:
    return ToolCallPart(tool_name=name, args={"x": 1}, tool_call_id=call_id)


def _ret(call_id: str, name: str = "edit") -> ToolReturnPart:
    return ToolReturnPart(tool_name=name, content="done", tool_call_id=call_id)


def test_interrupted_call_keeps_completed_sibling_calls_and_returns():
    """One interrupted call in a parallel batch must not erase its siblings.

    The assistant turn holds a text part plus calls a (answered) and b
    (interrupted). The turn, the text, call a, and a's return all survive;
    b is closed out with a synthesized return instead of deleting messages.
    """
    history = [
        ModelRequest(parts=[UserPromptPart(content="edit both files")]),
        ModelResponse(
            parts=[
                TextPart(content="editing a and b"),
                _call("a"),
                _call("b"),
            ]
        ),
        ModelRequest(parts=[_ret("a")]),
    ]

    pruned = prune_interrupted_tool_calls(history)

    # The assistant turn survives intact — text, call a, and call b.
    response = pruned[1]
    assert isinstance(response, ModelResponse)
    kinds = [p.part_kind for p in response.parts]
    assert kinds == ["text", "tool-call", "tool-call"]

    # The return for a survives in the following request, joined by the
    # synthesized return for b.
    request = pruned[2]
    assert isinstance(request, ModelRequest)
    returns = [p for p in request.parts if p.part_kind == "tool-return"]
    assert [r.tool_call_id for r in returns] == ["a", "b"]
    assert returns[1].content == INTERRUPTED_TOOL_RETURN_CONTENT
    assert returns[1].outcome == "interrupted"


def test_dangling_call_at_history_end_gets_trailing_request():
    """A history ending on an unanswered call is closed by a trailing request."""
    history = [
        ModelRequest(parts=[UserPromptPart(content="go")]),
        ModelResponse(parts=[_call("only")]),
    ]

    pruned = prune_interrupted_tool_calls(history)

    assert isinstance(pruned[-1], ModelRequest)
    (part,) = pruned[-1].parts
    assert part.part_kind == "tool-return"
    assert part.tool_call_id == "only"
    # The call itself survives; it is answered, not erased.
    assert not has_pending_tool_calls(pruned)


def test_orphaned_return_drops_only_that_part():
    """A return whose call is gone loses only its own part, not its message."""
    history = [
        ModelRequest(parts=[UserPromptPart(content="go")]),
        ModelResponse(parts=[_call("a")]),
        ModelRequest(
            parts=[
                _ret("a"),
                _ret("ghost"),
                UserPromptPart(content="next"),
            ]
        ),
    ]

    pruned = prune_interrupted_tool_calls(history)

    request = pruned[2]
    assert isinstance(request, ModelRequest)
    assert [p.part_kind for p in request.parts] == ["tool-return", "user-prompt"]
    assert request.parts[0].tool_call_id == "a"


def test_interior_emptied_request_is_dropped_trailing_kept():
    history = [
        ModelRequest(parts=[UserPromptPart(content="one")]),
        ModelResponse(parts=[_call("a")]),
        ModelRequest(parts=[_ret("a")]),
        ModelRequest(parts=[_ret("ghost1")]),
        ModelRequest(parts=[UserPromptPart(content="two")]),
        ModelResponse(parts=[TextPart(content="done")]),
        ModelRequest(parts=[_ret("ghost2")]),
    ]

    pruned = prune_interrupted_tool_calls(history)

    # ghost1's interior request is emptied and dropped; ghost2's trailing
    # request is emptied but kept so the history ends on a turn boundary.
    assert [type(m) for m in pruned] == [
        ModelRequest,
        ModelResponse,
        ModelRequest,
        ModelRequest,
        ModelResponse,
        ModelRequest,
    ]
    assert pruned[2].parts[0].tool_call_id == "a"
    assert pruned[3].parts[0].content == "two"
    assert pruned[-1].parts == []


def test_paired_history_returns_input_unchanged():
    history = [
        ModelRequest(parts=[UserPromptPart(content="go")]),
        ModelResponse(parts=[_call("a")]),
        ModelRequest(parts=[_ret("a")]),
    ]

    assert prune_interrupted_tool_calls(history) is history


def test_prune_is_idempotent():
    history = [
        ModelRequest(parts=[UserPromptPart(content="go")]),
        ModelResponse(parts=[TextPart(content="working"), _call("a"), _call("b")]),
        ModelRequest(parts=[_ret("a")]),
    ]

    once = prune_interrupted_tool_calls(history)
    twice = prune_interrupted_tool_calls(once)

    assert twice is once


def test_nameless_retry_prompt_is_not_treated_as_a_tool_return():
    """Validation retries have a tool_call_id but no tool_name.

    They are user-facing feedback, not a result that answers a call, and
    must survive prune instead of being dropped as an orphaned return.
    """
    retry = RetryPromptPart(content="Please return text or call a tool.")
    history = [
        ModelRequest(parts=[UserPromptPart(content="go")]),
        ModelResponse(parts=[TextPart(content="hmm")]),
        ModelRequest(parts=[retry]),
        ModelRequest(parts=[UserPromptPart(content="try again")]),
    ]

    pruned = prune_interrupted_tool_calls(history)

    assert pruned == history
    assert any(
        getattr(part, "part_kind", None) == "retry-prompt" for part in pruned[2].parts
    )


def test_retry_prompt_counts_as_return():
    """A retry prompt answers its call, so nothing is repaired."""
    history = [
        ModelRequest(parts=[UserPromptPart(content="go")]),
        ModelResponse(parts=[_call("a")]),
        ModelRequest(
            parts=[
                RetryPromptPart(
                    content="args invalid", tool_call_id="a", tool_name="edit"
                )
            ]
        ),
    ]

    assert prune_interrupted_tool_calls(history) is history


def test_builtin_tool_call_left_alone():
    """Provider-executed (builtin) calls wait for the provider, not for us."""
    from pydantic_ai.messages import NativeToolCallPart

    native = NativeToolCallPart(tool_name="web_search", tool_call_id="n1")
    history = [
        ModelRequest(parts=[UserPromptPart(content="go")]),
        ModelResponse(parts=[native]),
    ]

    pruned = prune_interrupted_tool_calls(history)

    # Untouched: the identity fast path holds (builtin parts never enter the
    # pairing sets), so nothing is synthesized and nothing reads as pending.
    assert pruned is history
    assert not has_pending_tool_calls(pruned)
