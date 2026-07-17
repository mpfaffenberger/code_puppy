from unittest.mock import patch

import code_puppy.plugins.agents_roster.register_callbacks as rc


def _fake_descs():
    return {
        "mist": "default coding agent",
        "qa-kitten": "Advanced web browser automation using Playwright",
        "planning-agent": "Breaks down complex tasks into steps",
    }


def test_roster_lists_specialists_and_excludes_self():
    rc.invalidate_roster_cache()
    fake_current = type("A", (), {"name": "mist"})()
    with (
        patch.object(rc, "get_agent_descriptions", _fake_descs, create=True),
        patch("code_puppy.agents.agent_manager.get_agent_descriptions", _fake_descs),
        patch(
            "code_puppy.agents.agent_manager.get_current_agent", lambda: fake_current
        ),
    ):
        roster = rc._build_roster()
    assert "qa-kitten" in roster
    assert "Playwright" in roster
    assert "planning-agent" in roster
    assert "- mist:" not in roster  # don't list yourself
    assert "invoke_agent" in roster
    assert "haven't verified" in roster  # the anti-overclaim nudge


def test_roster_cache_is_invalidatable():
    rc.invalidate_roster_cache()
    with patch.object(rc, "_build_roster", lambda: "ROSTER-A"):
        assert rc._on_load_prompt() == "ROSTER-A"
    # cached now; a new _build_roster value is ignored until invalidated
    with patch.object(rc, "_build_roster", lambda: "ROSTER-B"):
        assert rc._on_load_prompt() == "ROSTER-A"
        rc.invalidate_roster_cache()
        assert rc._on_load_prompt() == "ROSTER-B"
