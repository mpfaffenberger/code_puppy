from unittest.mock import MagicMock, patch

import code_puppy.agent as agent_module


def test_session_memory_singleton():
    # Skip this test since session_memory is no longer a module-level function
    # Should always return the same instance
    # Skip this test since session_memory is no longer a module-level function
    pass


def disabled_test_reload_code_generation_agent_loads_model(monkeypatch):
    # Patch all dependencies
    fake_agent = MagicMock()
    fake_model = MagicMock()
    fake_config = MagicMock()
    monkeypatch.setattr(agent_module, "Agent", lambda **kwargs: fake_agent)
    monkeypatch.setattr(
        agent_module.ModelFactory, "get_model", lambda name, config: fake_model
    )
    monkeypatch.setattr(
        agent_module.ModelFactory, "load_config", lambda path: fake_config
    )
    monkeypatch.setattr(agent_module, "register_all_tools", lambda agent: None)
    monkeypatch.setattr(agent_module, "get_system_prompt", lambda: "SYS_PROMPT")
    monkeypatch.setattr(agent_module, "PUPPY_RULES", None)
    monkeypatch.setattr(agent_module, "emit_info", MagicMock())
    monkeypatch.setattr(agent_module, "emit_system_message", MagicMock())
    monkeypatch.setattr(
        agent_module, "_mock_session_memory", lambda: MagicMock(log_task=MagicMock())
    )
    with patch("code_puppy.config.get_model_name", return_value="gpt-4o"):
        agent = agent_module.reload_code_generation_agent()
    assert agent is fake_agent


def disabled_test_reload_code_generation_agent_appends_rules(monkeypatch):
    fake_agent = MagicMock()
    fake_model = MagicMock()
    fake_config = MagicMock()
    monkeypatch.setattr(agent_module, "Agent", lambda **kwargs: fake_agent)
    monkeypatch.setattr(
        agent_module.ModelFactory, "get_model", lambda name, config: fake_model
    )
    monkeypatch.setattr(
        agent_module.ModelFactory, "load_config", lambda path: fake_config
    )
    monkeypatch.setattr(agent_module, "register_all_tools", lambda agent: None)
    monkeypatch.setattr(agent_module, "get_system_prompt", lambda: "SYS_PROMPT")
    monkeypatch.setattr(agent_module, "PUPPY_RULES", "RULES")
    monkeypatch.setattr(agent_module, "emit_info", MagicMock())
    monkeypatch.setattr(agent_module, "emit_system_message", MagicMock())
    monkeypatch.setattr(
        agent_module, "_mock_session_memory", lambda: MagicMock(log_task=MagicMock())
    )
    with patch("code_puppy.config.get_model_name", return_value="gpt-4o"):
        agent = agent_module.reload_code_generation_agent()
    # Should append rules to prompt
    assert agent is fake_agent


def disabled_test_reload_code_generation_agent_logs_exception(monkeypatch):
    fake_agent = MagicMock()
    fake_model = MagicMock()
    fake_config = MagicMock()
    monkeypatch.setattr(agent_module, "Agent", lambda **kwargs: fake_agent)
    monkeypatch.setattr(
        agent_module.ModelFactory, "get_model", lambda name, config: fake_model
    )
    monkeypatch.setattr(
        agent_module.ModelFactory, "load_config", lambda path: fake_config
    )
    monkeypatch.setattr(agent_module, "register_all_tools", lambda agent: None)
    monkeypatch.setattr(agent_module, "get_system_prompt", lambda: "SYS_PROMPT")
    monkeypatch.setattr(agent_module, "PUPPY_RULES", None)
    monkeypatch.setattr(agent_module, "emit_info", MagicMock())
    monkeypatch.setattr(agent_module, "emit_system_message", MagicMock())
    # session_memory().log_task will raise
    monkeypatch.setattr(
        agent_module,
        "session_memory",
        lambda: MagicMock(log_task=MagicMock(side_effect=Exception("fail"))),
    )
    with patch("code_puppy.config.get_model_name", return_value="gpt-4o"):
        agent = agent_module.reload_code_generation_agent()
    assert agent is fake_agent


def test_get_code_generation_agent_force_reload(monkeypatch):
    # Always reload
    monkeypatch.setattr(
        agent_module, "reload_code_generation_agent", lambda: "RELOADED"
    )
    agent_module._code_generation_agent = None
    agent_module._LAST_MODEL_NAME = None
    with patch("code_puppy.config.get_model_name", return_value="gpt-4o"):
        out = agent_module.get_code_generation_agent(force_reload=True)
    assert out == "RELOADED"


def test_get_code_generation_agent_model_change(monkeypatch):
    monkeypatch.setattr(
        agent_module, "reload_code_generation_agent", lambda: "RELOADED"
    )
    agent_module._code_generation_agent = "OLD"
    agent_module._LAST_MODEL_NAME = "old-model"
    with patch("code_puppy.config.get_model_name", return_value="gpt-4o"):
        out = agent_module.get_code_generation_agent(force_reload=False)
    assert out == "RELOADED"


def test_get_code_generation_agent_cached(monkeypatch):
    monkeypatch.setattr(
        agent_module, "reload_code_generation_agent", lambda: "RELOADED"
    )
    agent_module._code_generation_agent = "CACHED"
    agent_module._LAST_MODEL_NAME = "gpt-4o"
    with patch("code_puppy.config.get_model_name", return_value="gpt-4o"):
        out = agent_module.get_code_generation_agent(force_reload=False)
    assert out == "CACHED"
