"""Ordering guarantees for the summarization compaction path.

Some providers (Anthropic among them) require the message list of a request to
open with a user-role message and to alternate roles thereafter. A summarization
slice taken from the middle of a conversation naturally begins on an assistant
turn, and orphan-pruning can further leave it ending on a user turn or carrying
an internal same-role adjacency. On top of that, ``run_summarization_sync``
appends the summarization instruction as a trailing user-role message. The full
request the summarization model receives must therefore still open on a user
turn and alternate roles end to end — otherwise the provider rejects it and
compaction silently falls back to hard truncation instead of producing a real
summary.

These tests drive the real ``compact`` -> ``summarize`` ->
``run_summarization_sync`` path with a ``FunctionModel`` standing in for the
summarization model. The stand-in mirrors the provider contract: it inspects the
full incoming request and refuses one whose first message is an assistant turn
or that places two same-role messages next to each other, exactly as the
provider would. The production CLI disables pydantic-ai's history cleaner,
so the tests apply the same identity patch: shaping must hold without a
framework merge.
"""

from __future__ import annotations

from typing import Dict, List

from unittest.mock import patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

import code_puppy.summarization_agent as summarization_agent
from code_puppy.agents import _compaction

_SUMMARY_MARKER = "COMPACTED_SUMMARY_APPLIED"


def _roles(messages: List[ModelMessage]) -> List[str]:
    return ["assistant" if isinstance(m, ModelResponse) else "user" for m in messages]


def _realistic_history(
    n_turns: int = 20, payload_chars: int = 400
) -> List[ModelMessage]:
    """Build a history shaped like a live pydantic-ai run.

    The first message is a single ``ModelRequest`` carrying both the system
    prompt and the opening user prompt (how pydantic-ai composes the first
    request). Every following turn is an assistant ``ModelResponse`` paired with
    a user ``ModelRequest``, so the slice that gets summarized begins on an
    assistant turn.
    """
    payload = "x" * payload_chars
    history: List[ModelMessage] = [
        ModelRequest(
            parts=[
                SystemPromptPart(content="You are a helpful test agent."),
                UserPromptPart(content=f"opening question: {payload}"),
            ]
        )
    ]
    for i in range(n_turns):
        call_id = f"call_{i}"
        history.append(
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="read_file",
                        args={"path": f"/tmp/file_{i}.txt"},
                        tool_call_id=call_id,
                    )
                ]
            )
        )
        history.append(
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="read_file",
                        content=f"contents {i}: {payload}",
                        tool_call_id=call_id,
                    )
                ]
            )
        )
        history.append(ModelResponse(parts=[TextPart(content=f"answer {i}")]))
        history.append(
            ModelRequest(parts=[UserPromptPart(content=f"question {i}: {payload}")])
        )
    return history


def _user_ending_history(payload_chars: int = 400) -> List[ModelMessage]:
    """A tool-free history whose summarizable slice ends on a user turn.

    With the protected budget squeezed to a single token (see
    ``_run_compaction``), only the system message stays protected and the whole
    remainder becomes summarization fodder. That remainder both opens on an
    assistant turn and ends on a user turn, so it exercises the leading-role and
    trailing-adjacency repairs at once. No tool calls appear, so nothing is
    pruned and compaction is never deferred for a pending call.
    """
    payload = "x" * payload_chars
    return [
        ModelRequest(
            parts=[
                SystemPromptPart(content="You are a helpful test agent."),
                UserPromptPart(content=f"opening question: {payload}"),
            ]
        ),
        ModelResponse(parts=[TextPart(content=f"answer a: {payload}")]),
        ModelRequest(parts=[UserPromptPart(content=f"question b: {payload}")]),
        ModelResponse(parts=[TextPart(content=f"answer b: {payload}")]),
        ModelRequest(parts=[UserPromptPart(content=f"question c: {payload}")]),
    ]


def _make_capturing_summarization_agent(
    capture: Dict[str, List[ModelMessage]],
) -> Agent:
    """A summarization agent whose model records the request and enforces the
    provider's ordering contract.

    The model captures the exact message list it is handed, then refuses (the
    way the provider would) any request whose first message is an assistant turn
    or that places two same-role messages adjacently. A well-formed request
    returns a recognizable summary string.
    """

    def _model_fn(messages: List[ModelMessage], info: AgentInfo) -> ModelResponse:
        capture["messages"] = list(messages)
        roles = _roles(messages)
        if roles and roles[0] != "user":
            raise RuntimeError("messages: first message must use the 'user' role")
        if any(roles[i] == roles[i + 1] for i in range(len(roles) - 1)):
            raise RuntimeError(
                "messages: roles must alternate; two same-role messages were adjacent"
            )
        return ModelResponse(parts=[TextPart(content=_SUMMARY_MARKER)])

    return Agent(model=FunctionModel(_model_fn), output_type=str)


def _run_compaction(
    capture: Dict[str, List[ModelMessage]],
    history: List[ModelMessage] | None = None,
    protected_tokens: int = 500,
):
    if history is None:
        history = _realistic_history()
    # Production replaces pydantic-ai's history cleaner with identity
    # (``patch_message_history_cleaning``). Shape the request the same way
    # the CLI does, then restore whatever the rest of the suite had.
    from pydantic_ai import _agent_graph

    previous_cleaner = _agent_graph._clean_message_history
    _agent_graph._clean_message_history = lambda messages, **_kwargs: messages
    try:
        with (
            patch.object(
                summarization_agent,
                "get_summarization_agent",
                lambda *a, **kw: _make_capturing_summarization_agent(capture),
            ),
            patch.object(
                summarization_agent,
                "get_summarization_model_name",
                lambda: "function-model",
            ),
            patch.multiple(
                _compaction,
                get_compaction_threshold=lambda: 0.01,
                get_compaction_strategy=lambda: "summarization",
                get_protected_token_count=lambda: protected_tokens,
            ),
        ):
            new_messages, dropped = _compaction.compact(
                agent=None, messages=history, model_max=10_000, context_overhead=0
            )
    finally:
        _agent_graph._clean_message_history = previous_cleaner
    return history, new_messages, dropped


@pytest.fixture
def capture() -> Dict[str, List[ModelMessage]]:
    return {}


def _assert_valid_provider_ordering(messages: List[ModelMessage]) -> None:
    """The full request must open on a user turn and never repeat a role."""
    assert messages, "summarization model was never invoked"

    first = messages[0]
    assert isinstance(first, ModelRequest) and not isinstance(first, ModelResponse), (
        "summarization request must begin with a user-role message, not an "
        f"assistant turn (got {type(first).__name__})"
    )

    roles = _roles(messages)
    assert roles[0] == "user"
    adjacent_same = [i for i in range(len(roles) - 1) if roles[i] == roles[i + 1]]
    assert not adjacent_same, (
        f"summarization request placed same-role messages adjacently at {adjacent_same}"
    )


def test_summarization_request_starts_with_user_message(capture):
    """The full request the summarization model receives — including the
    instruction ``run_summarization_sync`` appends — must open on a user-role
    message and never place two same-role messages next to each other,
    regardless of where the slice boundary lands."""
    _run_compaction(capture)
    _assert_valid_provider_ordering(capture.get("messages"))


def test_summarization_request_valid_for_user_ending_slice(capture):
    """End-to-end guard for a slice that both opens on an assistant turn and
    ends on a user turn. The full request handed to the model must still be well
    ordered, and the summary must be applied rather than dropped to a truncation
    fallback, regardless of where the boundary lands."""
    history, new_messages, dropped = _run_compaction(
        capture, history=_user_ending_history(), protected_tokens=1
    )

    _assert_valid_provider_ordering(capture.get("messages"))
    # Confirm the appended instruction actually rode along on this request.
    assert _roles(capture["messages"])[-1] == "user", "trailing instruction missing"
    assert any(
        getattr(part, "content", None) == _SUMMARY_MARKER
        for message in new_messages
        for part in message.parts
    ), "summary was not applied — compaction fell back to truncation"
    assert dropped, "no messages recorded as dropped"


def test_compaction_applies_summary_not_truncation(capture):
    """A well-formed summarization request must actually shrink history via the
    produced summary rather than silently falling back to truncation."""
    history, new_messages, dropped = _run_compaction(capture)

    assert len(new_messages) < len(history), "history was not compacted"
    assert dropped, "no messages recorded as dropped"
    assert new_messages[0] is history[0], "system message must be preserved"
    assert any(
        getattr(part, "content", None) == _SUMMARY_MARKER
        for message in new_messages
        for part in message.parts
    ), "summary was not applied — compaction fell back to truncation"


def _assistant(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=text)])


def _user(text: str) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


# Adversarial slices covering every boundary the normalizer must repair. Each
# starts and/or ends and/or bends in a way a raw provider request would reject.
# Two adjacent assistant turns are the case pydantic-ai's own consecutive-message
# merge leaves alone for real (API-sourced) responses, so it must be repaired
# here rather than relied upon downstream.
_ADVERSARIAL_SLICES = {
    "leading_assistant": [_assistant("a0"), _user("u0")],
    "trailing_user": [_user("u0"), _assistant("a0"), _user("u1")],
    "adjacent_assistants": [_user("u0"), _assistant("a0"), _assistant("a1")],
    "adjacent_users": [_assistant("a0"), _user("u0"), _user("u1")],
    "already_valid": [_user("u0"), _assistant("a0")],
    "single_assistant": [_assistant("a0")],
    "single_user": [_user("u0")],
}


@pytest.mark.parametrize("slice_key", sorted(_ADVERSARIAL_SLICES))
def test_ensure_leading_request_repairs_only_the_opening(slice_key):
    """``_ensure_leading_request`` prepends a user turn only when the slice
    opens on an assistant one, and never fabricates other turns.

    Interior same-role adjacencies and a user-final slice are left to
    pydantic-ai's lossless consecutive-message merge — fabricated filler
    turns would be read (and described) by the summarizer as if they were
    real exchanges, so none may be inserted."""
    original = _ADVERSARIAL_SLICES[slice_key]
    normalized = _compaction._ensure_leading_request(list(original))

    opens_on_assistant = isinstance(original[0], ModelResponse)
    if opens_on_assistant:
        assert isinstance(normalized[0], ModelRequest), "must open on a user turn"
        assert normalized[1:] == original, (
            "real content must follow the framing verbatim"
        )
    else:
        assert normalized == original, "a user-opened slice must pass through unchanged"

    # No filler: every message beyond an optional leading framing request is
    # an original one, and nothing was appended.
    extras = [m for m in normalized if not any(m is o for o in original)]
    if opens_on_assistant:
        assert len(extras) == 1 and extras[0] is normalized[0]
    else:
        assert extras == []


def test_merge_consecutive_same_role_is_lossless():
    left = _user("one")
    right = _user("two")
    assistant = _assistant("ok")
    merged = _compaction._merge_consecutive_same_role([left, right, assistant])
    assert [type(m) for m in merged] == [ModelRequest, ModelResponse]
    assert [getattr(p, "content", None) for p in merged[0].parts] == ["one", "two"]


def test_detach_trailing_request_peels_final_user():
    history = [_assistant("ok"), _user("last")]
    rest, trailing = _compaction._detach_trailing_request(history)
    assert rest == history[:1]
    assert trailing is history[1]


def test_no_fabricated_content_reaches_the_summarizer(capture):
    """The summarizer must never be shown invented filler exchanges."""
    _run_compaction(capture)

    contents = [
        getattr(part, "content", None)
        for message in capture.get("messages") or []
        for part in message.parts
    ]
    assert not any(content == "Acknowledged; continuing." for content in contents), (
        "fabricated assistant filler reached the summarizer"
    )
    assert (
        sum(
            1 for content in contents if content == "Conversation history to summarize:"
        )
        <= 1
    ), "more than one framing message was injected"
