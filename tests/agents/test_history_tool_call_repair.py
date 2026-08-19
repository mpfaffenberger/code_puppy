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
    _OVERSIZED_TOOL_RETURN_CONTENT,
    filter_huge_messages,
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


def test_interior_and_trailing_emptied_requests_are_dropped():
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

    # Both ghost requests empty to zero parts and are dropped wherever they
    # sit — ghost2 included: a kept trailing empty request would end the wire
    # history on the assistant turn (prefill), which providers reject.
    assert [type(m) for m in pruned] == [
        ModelRequest,
        ModelResponse,
        ModelRequest,
        ModelRequest,
        ModelResponse,
    ]
    assert pruned[2].parts[0].tool_call_id == "a"
    assert pruned[3].parts[0].content == "two"
    assert isinstance(pruned[-1], ModelResponse)
    assert pruned[-1].parts[0].content == "done"


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


def test_oversized_tool_return_is_shrunk_not_interrupted():
    """An oversized COMPLETED tool result is shrunk in place, not dropped.

    Dropping the message would leave its call dangling, and prune would then
    close it with an ``interrupted`` return — telling the model the tool never
    ran, so it re-issues the identical oversized call. Instead the body is
    swapped for the oversized placeholder and the pair stays intact.
    """
    huge = "x" * 200_000  # estimates well over the 50k-token per-message budget
    history = [
        ModelRequest(parts=[UserPromptPart(content="read the big file")]),
        ModelResponse(parts=[_call("c1")]),
        ModelRequest(
            parts=[ToolReturnPart(tool_name="edit", content=huge, tool_call_id="c1")]
        ),
    ]

    result = filter_huge_messages(history)

    calls = [
        p
        for m in result
        for p in getattr(m, "parts", [])
        if getattr(p, "part_kind", None) == "tool-call"
    ]
    returns = [
        p
        for m in result
        for p in getattr(m, "parts", [])
        if getattr(p, "part_kind", None) == "tool-return"
    ]

    assert any(c.tool_call_id == "c1" for c in calls), "the call was erased"

    c1_returns = [r for r in returns if r.tool_call_id == "c1"]
    assert len(c1_returns) == 1
    (ret,) = c1_returns
    assert ret.content == _OVERSIZED_TOOL_RETURN_CONTENT
    assert ret.content != INTERRUPTED_TOOL_RETURN_CONTENT
    assert getattr(ret, "outcome", None) != "interrupted"

    assert not has_pending_tool_calls(result)


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
