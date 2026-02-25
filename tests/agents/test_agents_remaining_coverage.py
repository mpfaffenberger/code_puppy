"""Tests targeting remaining uncovered lines in code_puppy/agents/ (non-base_agent)."""

import json
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Reviewer agents - get_available_tools and get_system_prompt (2 lines each)
# ---------------------------------------------------------------------------


def _test_reviewer_agent(module_path, class_name):
    """Helper to test reviewer agents' tools and prompt methods."""
    import importlib

    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    agent = cls()
    tools = agent.get_available_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0
    prompt = agent.get_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_c_reviewer():
    _test_reviewer_agent("code_puppy.agents.agent_c_reviewer", "CReviewerAgent")


def test_code_reviewer():
    _test_reviewer_agent(
        "code_puppy.agents.agent_code_reviewer", "CodeQualityReviewerAgent"
    )


def test_cpp_reviewer():
    _test_reviewer_agent("code_puppy.agents.agent_cpp_reviewer", "CppReviewerAgent")


def test_golang_reviewer():
    _test_reviewer_agent(
        "code_puppy.agents.agent_golang_reviewer", "GolangReviewerAgent"
    )


def test_javascript_reviewer():
    _test_reviewer_agent(
        "code_puppy.agents.agent_javascript_reviewer", "JavaScriptReviewerAgent"
    )


def test_python_reviewer():
    _test_reviewer_agent(
        "code_puppy.agents.agent_python_reviewer", "PythonReviewerAgent"
    )


def test_typescript_reviewer():
    _test_reviewer_agent(
        "code_puppy.agents.agent_typescript_reviewer", "TypeScriptReviewerAgent"
    )


def test_security_auditor():
    _test_reviewer_agent(
        "code_puppy.agents.agent_security_auditor", "SecurityAuditorAgent"
    )


def test_qa_expert():
    _test_reviewer_agent("code_puppy.agents.agent_qa_expert", "QAExpertAgent")


def test_qa_kitten():
    from code_puppy.agents.agent_qa_kitten import QualityAssuranceKittenAgent

    agent = QualityAssuranceKittenAgent()
    tools = agent.get_available_tools()
    assert isinstance(tools, list)
    prompt = agent.get_system_prompt()
    assert isinstance(prompt, str)


def test_scheduler_agent():
    _test_reviewer_agent("code_puppy.agents.agent_scheduler", "SchedulerAgent")


def test_python_programmer():
    from code_puppy.agents.agent_python_programmer import PythonProgrammerAgent

    agent = PythonProgrammerAgent()
    tools = agent.get_available_tools()
    assert isinstance(tools, list)
    prompt = agent.get_system_prompt()
    assert isinstance(prompt, str)


def test_helios_agent():
    from code_puppy.agents.agent_helios import HeliosAgent

    agent = HeliosAgent()
    tools = agent.get_available_tools()
    assert isinstance(tools, list)
    prompt = agent.get_system_prompt()
    assert isinstance(prompt, str)


def test_code_puppy_agent():
    from code_puppy.agents.agent_code_puppy import CodePuppyAgent

    agent = CodePuppyAgent()
    tools = agent.get_available_tools()
    assert isinstance(tools, list)
    prompt = agent.get_system_prompt()
    assert isinstance(prompt, str)


# ---------------------------------------------------------------------------
# Planning & Prompt Reviewer agents
# ---------------------------------------------------------------------------


def test_planning_agent():
    from code_puppy.agents.agent_planning import PlanningAgent

    agent = PlanningAgent()
    tools = agent.get_available_tools()
    assert isinstance(tools, list)
    prompt = agent.get_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 100


def test_prompt_reviewer_agent():
    from code_puppy.agents.prompt_reviewer import PromptReviewerAgent

    agent = PromptReviewerAgent()
    tools = agent.get_available_tools()
    assert isinstance(tools, list)
    prompt = agent.get_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 100


# ---------------------------------------------------------------------------
# Pack agents - get_system_prompt (1 uncovered line each)
# ---------------------------------------------------------------------------


def test_pack_bloodhound():
    from code_puppy.agents.pack.bloodhound import BloodhoundAgent

    agent = BloodhoundAgent()
    with patch("code_puppy.agents.pack.bloodhound.callbacks") as mock_cb:
        mock_cb.on_load_prompt.return_value = ["extra prompt"]
        prompt = agent.get_system_prompt()
        assert "extra prompt" in prompt


def test_pack_husky():
    from code_puppy.agents.pack.husky import HuskyAgent

    agent = HuskyAgent()
    with patch("code_puppy.agents.pack.husky.callbacks") as mock_cb:
        mock_cb.on_load_prompt.return_value = ["extra"]
        prompt = agent.get_system_prompt()
        assert "extra" in prompt


def test_pack_retriever():
    from code_puppy.agents.pack.retriever import RetrieverAgent

    agent = RetrieverAgent()
    with patch("code_puppy.agents.pack.retriever.callbacks") as mock_cb:
        mock_cb.on_load_prompt.return_value = ["extra"]
        prompt = agent.get_system_prompt()
        assert "extra" in prompt


def test_pack_shepherd():
    from code_puppy.agents.pack.shepherd import ShepherdAgent

    agent = ShepherdAgent()
    with patch("code_puppy.agents.pack.shepherd.callbacks") as mock_cb:
        mock_cb.on_load_prompt.return_value = ["extra"]
        prompt = agent.get_system_prompt()
        assert "extra" in prompt


def test_pack_terrier():
    from code_puppy.agents.pack.terrier import TerrierAgent

    agent = TerrierAgent()
    with patch("code_puppy.agents.pack.terrier.callbacks") as mock_cb:
        mock_cb.on_load_prompt.return_value = ["extra"]
        prompt = agent.get_system_prompt()
        assert "extra" in prompt


def test_pack_watchdog():
    from code_puppy.agents.pack.watchdog import WatchdogAgent

    agent = WatchdogAgent()
    with patch("code_puppy.agents.pack.watchdog.callbacks") as mock_cb:
        mock_cb.on_load_prompt.return_value = ["extra"]
        prompt = agent.get_system_prompt()
        assert "extra" in prompt


def test_pack_leader():
    from code_puppy.agents.agent_pack_leader import PackLeaderAgent

    agent = PackLeaderAgent()
    with patch("code_puppy.agents.agent_pack_leader.callbacks") as mock_cb:
        mock_cb.on_load_prompt.return_value = ["extra"]
        prompt = agent.get_system_prompt()
        assert "extra" in prompt


# ---------------------------------------------------------------------------
# agent_creator_agent.py - lines 45-46, 52, 546-626
# ---------------------------------------------------------------------------


def test_creator_agent_get_system_prompt_with_uc_tools():
    """Cover UC tools loading in get_system_prompt."""
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()

    mock_tool = MagicMock()
    mock_tool.full_name = "my_tool"
    mock_tool.meta.enabled = True
    mock_tool.meta.description = "A tool"

    mock_registry = MagicMock()
    mock_registry.list_tools.return_value = [mock_tool]

    with patch(
        "code_puppy.plugins.universal_constructor.registry.get_registry",
        return_value=mock_registry,
    ):
        prompt = agent.get_system_prompt()
        assert "my_tool" in prompt


def test_creator_agent_get_system_prompt_uc_import_error():
    """Cover ImportError branch for UC tools."""
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()

    with patch(
        "code_puppy.plugins.universal_constructor.registry.get_registry",
        side_effect=Exception("boom"),
    ):
        prompt = agent.get_system_prompt()
        assert isinstance(prompt, str)


def test_creator_validate_agent_json_valid():
    """Cover validate_agent_json with valid config."""
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()

    with patch(
        "code_puppy.agents.agent_creator_agent.get_available_tool_names",
        return_value=["list_files", "read_file"],
    ):
        errors = agent.validate_agent_json(
            {
                "name": "test-agent",
                "description": "A test",
                "system_prompt": "You are a test agent.",
                "tools": ["list_files"],
            }
        )
        assert errors == []


def test_creator_validate_agent_json_missing_fields():
    """Cover missing required fields."""
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()
    errors = agent.validate_agent_json({})
    assert len(errors) == 4


def test_creator_validate_agent_json_bad_name():
    """Cover name validation: spaces, empty."""
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()

    with patch(
        "code_puppy.agents.agent_creator_agent.get_available_tool_names",
        return_value=["list_files"],
    ):
        # Space in name
        errors = agent.validate_agent_json(
            {
                "name": "bad name",
                "description": "d",
                "system_prompt": "p",
                "tools": ["list_files"],
            }
        )
        assert any("spaces" in e for e in errors)

        # Empty name
        errors = agent.validate_agent_json(
            {
                "name": "",
                "description": "d",
                "system_prompt": "p",
                "tools": ["list_files"],
            }
        )
        assert any("non-empty" in e for e in errors)


def test_creator_validate_agent_json_bad_tools():
    """Cover tools validation: not a list, invalid tools."""
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()

    with patch(
        "code_puppy.agents.agent_creator_agent.get_available_tool_names",
        return_value=["list_files"],
    ):
        # tools not a list
        errors = agent.validate_agent_json(
            {
                "name": "test",
                "description": "d",
                "system_prompt": "p",
                "tools": "not-a-list",
            }
        )
        assert any("list" in e for e in errors)

        # invalid tool names
        errors = agent.validate_agent_json(
            {
                "name": "test",
                "description": "d",
                "system_prompt": "p",
                "tools": ["nonexistent_tool"],
            }
        )
        assert any("Invalid" in e for e in errors)


def test_creator_validate_agent_json_bad_prompt():
    """Cover system_prompt validation: not string/list, bad list items."""
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()

    with patch(
        "code_puppy.agents.agent_creator_agent.get_available_tool_names",
        return_value=["list_files"],
    ):
        # prompt is number
        errors = agent.validate_agent_json(
            {
                "name": "test",
                "description": "d",
                "system_prompt": 123,
                "tools": ["list_files"],
            }
        )
        assert any("string or list" in e for e in errors)

        # prompt is list with non-strings
        errors = agent.validate_agent_json(
            {
                "name": "test",
                "description": "d",
                "system_prompt": ["ok", 123],
                "tools": ["list_files"],
            }
        )
        assert any("must be strings" in e for e in errors)


def test_creator_get_agent_file_path():
    """Cover get_agent_file_path."""
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()
    with patch(
        "code_puppy.agents.agent_creator_agent.get_user_agents_directory",
        return_value="/tmp/agents",
    ):
        path = agent.get_agent_file_path("my-agent")
        assert path.endswith("my-agent.json")


def test_creator_create_agent_json_success(tmp_path):
    """Cover create_agent_json success path."""
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()

    with (
        patch(
            "code_puppy.agents.agent_creator_agent.get_available_tool_names",
            return_value=["list_files"],
        ),
        patch(
            "code_puppy.agents.agent_creator_agent.get_user_agents_directory",
            return_value=str(tmp_path),
        ),
    ):
        success, msg = agent.create_agent_json(
            {
                "name": "new-agent",
                "description": "d",
                "system_prompt": "p",
                "tools": ["list_files"],
            }
        )
        assert success is True
        assert "Successfully" in msg
        assert (tmp_path / "new-agent.json").exists()


def test_creator_create_agent_json_already_exists(tmp_path):
    """Cover create_agent_json when file exists."""
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()
    (tmp_path / "existing.json").write_text("{}")

    with (
        patch(
            "code_puppy.agents.agent_creator_agent.get_available_tool_names",
            return_value=["list_files"],
        ),
        patch(
            "code_puppy.agents.agent_creator_agent.get_user_agents_directory",
            return_value=str(tmp_path),
        ),
    ):
        success, msg = agent.create_agent_json(
            {
                "name": "existing",
                "description": "d",
                "system_prompt": "p",
                "tools": ["list_files"],
            }
        )
        assert success is False
        assert "already exists" in msg


def test_creator_create_agent_json_validation_error():
    """Cover create_agent_json with validation errors."""
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()
    success, msg = agent.create_agent_json({})
    assert success is False
    assert "Validation" in msg


def test_creator_create_agent_json_write_failure(tmp_path):
    """Cover create_agent_json write failure."""
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()

    with (
        patch(
            "code_puppy.agents.agent_creator_agent.get_available_tool_names",
            return_value=["list_files"],
        ),
        patch(
            "code_puppy.agents.agent_creator_agent.get_user_agents_directory",
            return_value=str(tmp_path),
        ),
        patch("builtins.open", side_effect=PermissionError("denied")),
    ):
        success, msg = agent.create_agent_json(
            {
                "name": "fail-agent",
                "description": "d",
                "system_prompt": "p",
                "tools": ["list_files"],
            }
        )
        assert success is False
        assert "Failed" in msg


def test_creator_get_user_prompt():
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    agent = AgentCreatorAgent()
    prompt = agent.get_user_prompt()
    assert isinstance(prompt, str)


# ---------------------------------------------------------------------------
# agent_manager.py - lines 86-90, 247, 267-279, 585, 673-674
# ---------------------------------------------------------------------------


def test_agent_manager_is_process_alive_dead_process():
    """Cover ProcessLookupError branch in _is_process_alive."""
    import sys

    from code_puppy.agents.agent_manager import _is_process_alive

    if sys.platform == "win32":
        pytest.skip("Unix-only")
    with patch("os.kill", side_effect=ProcessLookupError):
        result = _is_process_alive(999999999)
        assert result is False


def test_agent_manager_is_process_alive_permission():
    """Cover PermissionError branch (process exists but no permission)."""
    import sys

    from code_puppy.agents.agent_manager import _is_process_alive

    if sys.platform == "win32":
        pytest.skip("Unix-only")
    with patch("os.kill", side_effect=PermissionError):
        result = _is_process_alive(999999999)
        assert result is True


def test_agent_manager_discover_agents_error():
    """Cover error loading agent sub-packages (lines 267-279)."""
    from code_puppy.agents.agent_manager import _discover_agents

    # Should not raise even with import errors
    with patch("importlib.import_module", side_effect=Exception("boom")):
        _discover_agents()  # Should not raise


def test_next_clone_index():
    """Cover _next_clone_index (line 585)."""
    from pathlib import Path

    from code_puppy.agents.agent_manager import _next_clone_index

    # No existing clones
    with patch("pathlib.Path.exists", return_value=False):
        idx = _next_clone_index("test", [], Path("/tmp"))
        assert isinstance(idx, int)
        assert idx >= 1

    # With existing clones
    with patch("pathlib.Path.exists", return_value=False):
        idx = _next_clone_index("test", ["test-clone-1", "test-clone-3"], Path("/tmp"))
        assert idx >= 1


def test_clone_agent_failure():
    """Cover clone_agent failure paths (lines 673-674)."""
    from code_puppy.agents.agent_manager import clone_agent

    with patch("code_puppy.agents.agent_manager.emit_warning"):
        result = clone_agent("totally-nonexistent-agent-xyz")
        # Should return None for nonexistent agent
        assert result is None


# ---------------------------------------------------------------------------
# event_stream_handler.py - lines 45-48, 262-263, 285
# ---------------------------------------------------------------------------


def test_fire_stream_event_import_error():
    """Cover ImportError branch in _fire_stream_event."""
    from code_puppy.agents.event_stream_handler import _fire_stream_event

    with patch("code_puppy.callbacks.on_stream_event", side_effect=ImportError):
        _fire_stream_event("test", {})  # Should not raise


def test_fire_stream_event_exception():
    """Cover Exception branch in _fire_stream_event."""
    from code_puppy.agents.event_stream_handler import _fire_stream_event

    with patch("code_puppy.callbacks.on_stream_event", side_effect=Exception("boom")):
        _fire_stream_event("test", {})  # Should not raise


# ---------------------------------------------------------------------------
# json_agent.py - lines 103-109, 118
# ---------------------------------------------------------------------------


def _make_json_agent(tmp_path, config):
    """Helper to create a JSONAgent from a dict config."""
    from code_puppy.agents.json_agent import JSONAgent

    path = tmp_path / f"{config['name']}.json"
    path.write_text(json.dumps(config))
    return JSONAgent(str(path))


def test_json_agent_uc_tools(tmp_path):
    """Cover UC tool resolution in get_available_tools."""
    agent = _make_json_agent(
        tmp_path,
        {
            "name": "test-json",
            "display_name": "Test JSON",
            "description": "A test agent",
            "system_prompt": "You are test.",
            "tools": ["list_files", "my_uc_tool"],
        },
    )

    mock_tool = MagicMock()
    mock_tool.full_name = "my_uc_tool"
    mock_tool.meta.enabled = True

    mock_registry = MagicMock()
    mock_registry.list_tools.return_value = [mock_tool]

    with patch(
        "code_puppy.plugins.universal_constructor.registry.get_registry",
        return_value=mock_registry,
    ):
        tools = agent.get_available_tools()
        assert "uc:my_uc_tool" in tools


def test_json_agent_uc_import_error(tmp_path):
    """Cover ImportError branch in get_available_tools."""
    agent = _make_json_agent(
        tmp_path,
        {
            "name": "test-json2",
            "display_name": "Test",
            "description": "d",
            "system_prompt": "p",
            "tools": ["list_files"],
        },
    )

    # The import is inside get_available_tools, so we patch at source
    with patch.dict(
        "sys.modules", {"code_puppy.plugins.universal_constructor.registry": None}
    ):
        tools = agent.get_available_tools()
        assert "list_files" in tools


def test_json_agent_get_user_prompt(tmp_path):
    """Cover get_user_prompt."""
    agent = _make_json_agent(
        tmp_path,
        {
            "name": "t",
            "display_name": "T",
            "description": "d",
            "system_prompt": "p",
            "tools": [],
            "user_prompt": "hello there",
        },
    )
    assert agent.get_user_prompt() == "hello there"


# ---------------------------------------------------------------------------
# subagent_stream_handler.py - lines 59, 152-155
# ---------------------------------------------------------------------------


def test_subagent_fire_callback_no_loop():
    """Cover RuntimeError branch (no event loop) in _fire_callback."""
    from code_puppy.agents.subagent_stream_handler import _fire_callback

    # Called outside async context - should not raise
    _fire_callback("test", {}, None)


def test_subagent_fire_callback_import_error():
    """Cover ImportError branch in _fire_callback."""
    from code_puppy.agents.subagent_stream_handler import _fire_callback

    with patch("code_puppy.callbacks.on_stream_event", side_effect=ImportError):
        _fire_callback("test", {}, None)


def test_subagent_stream_handler_module():
    """Verify the module is importable."""
    import importlib

    mod = importlib.import_module("code_puppy.agents.subagent_stream_handler")
    assert hasattr(mod, "_fire_callback")
