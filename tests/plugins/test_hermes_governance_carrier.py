"""Regression tests for the hermes_governance carrier message layout.

The carrier MUST NOT produce two consecutive user (``ModelRequest``) messages
in the outgoing wire body, or Claude Code OAuth's endpoint silently stalls
instead of erroring \u2014 the original "hermes + claude-code-oauth hangs" bug.

The fix: ``write_state`` merges the carrier into the last existing
``ModelRequest`` as an additional ``UserPromptPart``, rather than appending
a new ``ModelRequest``. These tests pin that contract.
"""

from __future__ import annotations

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from code_puppy.plugins.hermes_governance import carrier


def _user(text: str) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _assistant(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=text)])


def test_write_state_merges_into_last_user_message() -> None:
    """Carrier rides as an extra part on the trailing ModelRequest, not as a new one."""
    history = [_user("hi")]
    state = carrier.default_state()

    result = carrier.write_state(history, state)

    # Still one message \u2014 not two consecutive user turns.
    assert len(result) == 1
    msg = result[0]
    assert isinstance(msg, ModelRequest)
    # Original user part preserved + carrier part appended.
    contents = [getattr(p, "content", "") for p in msg.parts]
    assert "hi" in contents
    assert any("<<<HERMES_GOVERNANCE_STATE>>>" in c for c in contents)


def test_write_state_merges_after_assistant_response() -> None:
    """Mid-conversation: still merges into the most recent ModelRequest."""
    history = [
        _user("first"),
        _assistant("ack"),
        _user("second"),
    ]
    state = carrier.default_state()

    result = carrier.write_state(history, state)

    # No extra message appended.
    assert len(result) == 3
    # Carrier landed on the *last* user message, not the first.
    last_user_parts = [getattr(p, "content", "") for p in result[-1].parts]
    first_user_parts = [getattr(p, "content", "") for p in result[0].parts]
    assert any("HERMES_GOVERNANCE_STATE" in c for c in last_user_parts)
    assert not any("HERMES_GOVERNANCE_STATE" in c for c in first_user_parts)


def test_write_state_falls_back_to_standalone_when_no_user_message() -> None:
    """Edge case: no ModelRequest in history \u2192 append a standalone carrier.

    This path is rare (a freshly-built agent with zero user input) and the
    consecutive-user-messages issue can't bite us here because there is no
    real user message yet.
    """
    history: list = []
    state = carrier.default_state()

    result = carrier.write_state(history, state)

    assert len(result) == 1
    assert isinstance(result[0], ModelRequest)
    assert any(
        "HERMES_GOVERNANCE_STATE" in getattr(p, "content", "") for p in result[0].parts
    )


def test_write_state_replaces_stale_carrier_without_duplicating() -> None:
    """Re-writing state strips the old carrier first \u2014 no duplication."""
    history = [_user("hi")]
    state_v1 = carrier.default_state()
    state_v2 = dict(state_v1)
    state_v2["used"] = 7

    once = carrier.write_state(history, state_v1)
    twice = carrier.write_state(once, state_v2)

    # Still one message.
    assert len(twice) == 1
    msg = twice[0]
    # Exactly one carrier part \u2014 not two stacked up.
    carrier_parts = [
        p for p in msg.parts if "HERMES_GOVERNANCE_STATE" in getattr(p, "content", "")
    ]
    assert len(carrier_parts) == 1
    # And it carries the *new* state.
    decoded = carrier.find_state(twice)
    assert decoded is not None
    assert decoded["used"] == 7


def test_find_state_reads_carrier_riding_inline_in_user_message() -> None:
    """``find_state`` works when the carrier is an extra part on a real user turn."""
    history = [_user("real prompt")]
    state = carrier.default_state()
    state["unlocked"] = True

    written = carrier.write_state(history, state)
    decoded = carrier.find_state(written)

    assert decoded is not None
    assert decoded["unlocked"] is True


def test_strip_carriers_preserves_real_user_content() -> None:
    """Stripping the carrier leaves the original user text untouched."""
    history = [_user("real prompt")]
    written = carrier.write_state(history, carrier.default_state())

    stripped = carrier._strip_carriers(written)

    assert len(stripped) == 1
    contents = [getattr(p, "content", "") for p in stripped[0].parts]
    assert "real prompt" in contents
    assert not any("HERMES_GOVERNANCE_STATE" in c for c in contents)
