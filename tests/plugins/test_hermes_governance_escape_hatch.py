"""Regression tests for the hermes_governance escape-hatch wiring.

The budget gate blocks every non-exempt tool once the onboarding budget is
spent; the only way to unlock is a skill action via ``skill_manage``. But
``register_tools`` alone never advertises ``skill_manage`` to an agent's tool
list, so an armed gate would dead-end. ``wrap_agent`` must self-attach the
tool when enforcement is enabled (and must NOT when disarmed).
"""

from __future__ import annotations

from code_puppy.plugins.hermes_governance import carrier_processor, config


class _FakePydanticAgent:
    """Minimal stand-in for a pydantic-ai Agent.

    Records tool functions registered via the ``@agent.tool`` decorator and
    raises on duplicate names, mirroring pydantic-ai's behaviour so we can
    assert idempotency is handled.
    """

    def __init__(self):
        self.history_processors = []
        self.registered_tools = {}

    def tool(self, func):
        name = func.__name__
        if name in self.registered_tools:
            raise ValueError(f"Tool already registered: {name}")
        self.registered_tools[name] = func
        return func


class _FakeAgent:
    """Stand-in for the code_puppy agent (only needs _message_history)."""

    def __init__(self):
        self._message_history = []


def _set_enabled(value: bool):
    config.set_enabled(value)


def test_wrap_agent_attaches_skill_manage_when_enabled():
    _set_enabled(True)
    try:
        pyd = _FakePydanticAgent()
        carrier_processor.wrap_agent(_FakeAgent(), pyd)
        assert "skill_manage" in pyd.registered_tools, (
            "escape-hatch tool must be attached so the budget gate is unlockable"
        )
        # carrier processor must also be attached
        assert pyd.history_processors, "carrier processor should be appended"
    finally:
        _set_enabled(False)


def test_wrap_agent_does_not_attach_when_disabled():
    _set_enabled(False)
    pyd = _FakePydanticAgent()
    carrier_processor.wrap_agent(_FakeAgent(), pyd)
    assert "skill_manage" not in pyd.registered_tools, (
        "a disarmed plugin must not add any tools"
    )


def test_wrap_agent_idempotent_on_rebuild():
    """Re-wrapping the same agent (agent rebuild) must not raise."""
    _set_enabled(True)
    try:
        pyd = _FakePydanticAgent()
        carrier_processor.wrap_agent(_FakeAgent(), pyd)
        # Second wrap simulates an agent reload; duplicate tool reg is swallowed.
        carrier_processor.wrap_agent(_FakeAgent(), pyd)
        assert "skill_manage" in pyd.registered_tools
    finally:
        _set_enabled(False)


# ---------------------------------------------------------------------------
# Deep-critique regression tests
# ---------------------------------------------------------------------------

from code_puppy.plugins.hermes_governance import budget, carrier, enforcer  # noqa: E402


class _FailResult:
    """Mimics SkillManageOutput with an error (a failed call)."""

    def __init__(self, error):
        self.error = error


def test_fake_unlock_rejected_on_failed_skill_call():
    """activate_skill on a bogus name must NOT unlock the budget (#1)."""
    config.set_enabled(True)
    try:
        budget.reset()
        budget.load_from_carrier([])  # hydrate fresh
        assert not budget.unlocked()
        # Simulate a failed activate_skill returning "not found".
        enforcer.post_tool_call(
            "activate_skill",
            {"skill_name": "does_not_exist"},
            result="Skill 'does_not_exist' not found",
        )
        assert not budget.unlocked(), "failed skill call must not unlock"
        # And it must not pollute the curator's skill_usage map (#7).
        assert "does_not_exist" not in budget.snapshot().get("skill_usage", {})
    finally:
        config.set_enabled(False)


def test_real_skill_call_still_unlocks():
    config.set_enabled(True)
    try:
        budget.reset()
        budget.load_from_carrier([])
        enforcer.post_tool_call(
            "skill_manage",
            {"name": "real_skill"},
            result=_FailResult(error=None),  # error=None => success
        )
        assert budget.unlocked()
        assert "real_skill" in budget.snapshot().get("skill_usage", {})
    finally:
        config.set_enabled(False)


def test_exploration_tools_are_exempt():
    """Read-only exploration must never count against the budget (#9)."""
    for t in ("read_file", "list_files", "grep"):
        assert budget.is_exempt(t), f"{t} should be exempt"


def test_carrier_rejects_accidental_sentinel_echo():
    """A prose echo of the sentinels must not be parsed as state (#4a)."""

    class _Part:
        def __init__(self, content):
            self.content = content

    class _Msg:
        def __init__(self, content):
            self.parts = [_Part(content)]

    bogus = (
        "<<<HERMES_GOVERNANCE_STATE>>>not really json<<<END_HERMES_GOVERNANCE_STATE>>>"
    )
    assert carrier.find_state([_Msg(bogus)]) is None


def test_carrier_strip_does_not_mutate_input():
    """_strip_carriers must not mutate the original message parts (#4b)."""

    class _Part:
        def __init__(self, content):
            self.content = content

    class _Msg:
        def __init__(self, parts):
            self.parts = parts

    real = carrier._encode(carrier.default_state())
    msg = _Msg([_Part("real user text"), _Part(real)])
    original_parts = msg.parts
    carrier._strip_carriers([msg])
    # original object's parts list must be unchanged
    assert msg.parts is original_parts
    assert len(msg.parts) == 2


def test_per_turn_regen_preserves_unlock_and_skill_usage():
    """Per-turn regeneration zeroes 'used' but keeps durable progress (#2)."""

    class _Part:
        def __init__(self, content):
            self.content = content

    class _Msg:
        def __init__(self, content):
            self.parts = [_Part(content)]

    config.set_enabled(True)
    try:
        state = carrier.default_state()
        state["unlocked"] = True
        state["used"] = 89
        state["skill_usage"] = {"foo": "2026-01-01"}
        hist = [_Msg(carrier._encode(state))]

        budget.reset()
        budget.load_from_carrier(hist)
        s = budget.snapshot()
        assert s["used"] == 0, "used must regenerate to 0 each turn (no lifetime cap)"
        assert s["unlocked"] is True, "unlocked must survive regeneration"
        assert "foo" in s["skill_usage"], "skill_usage must survive regeneration"
    finally:
        config.set_enabled(False)
