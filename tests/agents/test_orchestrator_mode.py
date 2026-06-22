from unittest.mock import patch

import code_puppy.agents.agent_code_puppy as m


def test_orchestrator_mode_flag_parsing():
    for off in (None, "", "off", "false", "0", "no"):
        with patch.object(m, "get_value", return_value=off):
            assert m.orchestrator_mode_enabled() is False
    for on in ("on", "true", "1", "yes", "enabled"):
        with patch.object(m, "get_value", return_value=on):
            assert m.orchestrator_mode_enabled() is True


def test_overlay_absent_by_default():
    with patch.object(m, "get_value", return_value=None):
        prompt = m.MistAgent().get_system_prompt()
    assert "ORCHESTRATION MODE" not in prompt


def test_overlay_present_and_delegation_directives_when_enabled():
    with patch.object(m, "get_value", return_value="on"):
        prompt = m.MistAgent().get_system_prompt()
    assert "ORCHESTRATION MODE" in prompt
    overlay = prompt.split("ORCHESTRATION MODE")[1]
    # Core delegation guidance from the research is present.
    assert "invoke_agent" in overlay
    assert "concise summary" in overlay
    assert "non-overlapping" in overlay
