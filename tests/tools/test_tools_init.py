"""Tests for code_puppy/tools/__init__.py - 100% coverage."""

from unittest.mock import MagicMock, patch


class TestLoadPluginTools:
    def test_loads_tools(self):
        from code_puppy.tools import TOOL_REGISTRY, _load_plugin_tools

        with patch("code_puppy.tools.on_register_tools") as mock_cb:
            mock_cb.return_value = [
                [{"name": "test_tool", "register_func": lambda a: None}]
            ]
            _load_plugin_tools()
            assert "test_tool" in TOOL_REGISTRY
            del TOOL_REGISTRY["test_tool"]

    def test_none_results(self):
        from code_puppy.tools import _load_plugin_tools

        with patch("code_puppy.tools.on_register_tools") as mock_cb:
            mock_cb.return_value = [None]
            _load_plugin_tools()  # should not raise

    def test_single_dict_result(self):
        from code_puppy.tools import TOOL_REGISTRY, _load_plugin_tools

        with patch("code_puppy.tools.on_register_tools") as mock_cb:
            mock_cb.return_value = [
                {"name": "single_tool", "register_func": lambda a: None}
            ]
            _load_plugin_tools()
            assert "single_tool" in TOOL_REGISTRY
            del TOOL_REGISTRY["single_tool"]

    def test_invalid_tool_def(self):
        from code_puppy.tools import _load_plugin_tools

        with patch("code_puppy.tools.on_register_tools") as mock_cb:
            mock_cb.return_value = [[{"name": "no_func"}]]  # missing register_func
            _load_plugin_tools()  # should not raise

    def test_non_callable(self):
        from code_puppy.tools import _load_plugin_tools

        with patch("code_puppy.tools.on_register_tools") as mock_cb:
            mock_cb.return_value = [[{"name": "x", "register_func": "not_callable"}]]
            _load_plugin_tools()  # should not add

    def test_exception_swallowed(self):
        from code_puppy.tools import _load_plugin_tools

        with patch("code_puppy.tools.on_register_tools", side_effect=Exception("boom")):
            _load_plugin_tools()  # should not raise


class TestHasExtendedThinkingActive:
    @patch("code_puppy.config.get_global_model_name", return_value=None)
    def test_no_model(self, mock_model):
        from code_puppy.tools import has_extended_thinking_active

        assert not has_extended_thinking_active()

    def test_non_claude(self):
        from code_puppy.tools import has_extended_thinking_active

        assert not has_extended_thinking_active("gpt-4")

    @patch("code_puppy.config.get_effective_model_settings", return_value={})
    @patch("code_puppy.model_utils.get_default_extended_thinking", return_value=False)
    def test_claude_disabled(self, mock_default, mock_settings):
        from code_puppy.tools import has_extended_thinking_active

        assert not has_extended_thinking_active("claude-3")

    @patch(
        "code_puppy.config.get_effective_model_settings",
        return_value={"extended_thinking": True},
    )
    @patch("code_puppy.model_utils.get_default_extended_thinking", return_value=False)
    def test_claude_legacy_true(self, mock_default, mock_settings):
        from code_puppy.tools import has_extended_thinking_active

        assert has_extended_thinking_active("claude-3")

    @patch(
        "code_puppy.config.get_effective_model_settings",
        return_value={"extended_thinking": "enabled"},
    )
    @patch("code_puppy.model_utils.get_default_extended_thinking", return_value=False)
    def test_claude_enabled(self, mock_default, mock_settings):
        from code_puppy.tools import has_extended_thinking_active

        assert has_extended_thinking_active("claude-3")

    @patch(
        "code_puppy.config.get_effective_model_settings",
        return_value={"extended_thinking": "adaptive"},
    )
    @patch("code_puppy.model_utils.get_default_extended_thinking", return_value=False)
    def test_claude_adaptive(self, mock_default, mock_settings):
        from code_puppy.tools import has_extended_thinking_active

        assert has_extended_thinking_active("anthropic-model")


class TestRegisterToolsForAgent:
    @patch("code_puppy.tools._load_plugin_tools")
    @patch("code_puppy.tools.has_extended_thinking_active", return_value=False)
    def test_register_known_tool(self, mock_ext, mock_load):
        from code_puppy.tools import TOOL_REGISTRY, register_tools_for_agent

        agent = MagicMock()
        mock_fn = MagicMock()
        TOOL_REGISTRY["__test_tool"] = mock_fn
        try:
            register_tools_for_agent(agent, ["__test_tool"])
            mock_fn.assert_called_once_with(agent)
        finally:
            del TOOL_REGISTRY["__test_tool"]

    @patch("code_puppy.tools._load_plugin_tools")
    @patch("code_puppy.tools.has_extended_thinking_active", return_value=False)
    @patch("code_puppy.tools.emit_warning")
    def test_unknown_tool(self, mock_warn, mock_ext, mock_load):
        from code_puppy.tools import register_tools_for_agent

        agent = MagicMock()
        register_tools_for_agent(agent, ["__nonexistent_tool"])
        mock_warn.assert_called()

    @patch("code_puppy.tools._load_plugin_tools")
    @patch("code_puppy.tools.has_extended_thinking_active", return_value=True)
    def test_skip_reasoning_tool(self, mock_ext, mock_load):
        from code_puppy.tools import TOOL_REGISTRY, register_tools_for_agent

        mock_fn = MagicMock()
        original = TOOL_REGISTRY.get("agent_share_your_reasoning")
        TOOL_REGISTRY["agent_share_your_reasoning"] = mock_fn
        try:
            agent = MagicMock()
            register_tools_for_agent(agent, ["agent_share_your_reasoning"])
            mock_fn.assert_not_called()
        finally:
            if original:
                TOOL_REGISTRY["agent_share_your_reasoning"] = original

    @patch("code_puppy.tools._load_plugin_tools")
    @patch("code_puppy.tools.has_extended_thinking_active", return_value=False)
    @patch("code_puppy.config.get_universal_constructor_enabled", return_value=False)
    def test_skip_uc_disabled(self, mock_uc, mock_ext, mock_load):
        from code_puppy.tools import TOOL_REGISTRY, register_tools_for_agent

        mock_fn = MagicMock()
        original = TOOL_REGISTRY.get("universal_constructor")
        TOOL_REGISTRY["universal_constructor"] = mock_fn
        try:
            agent = MagicMock()
            register_tools_for_agent(agent, ["universal_constructor"])
            mock_fn.assert_not_called()
        finally:
            if original:
                TOOL_REGISTRY["universal_constructor"] = original

    @patch("code_puppy.tools._load_plugin_tools")
    @patch("code_puppy.tools.has_extended_thinking_active", return_value=False)
    @patch("code_puppy.config.get_universal_constructor_enabled", return_value=False)
    def test_skip_uc_prefixed_disabled(self, mock_uc, mock_ext, mock_load):
        from code_puppy.tools import register_tools_for_agent

        agent = MagicMock()
        register_tools_for_agent(agent, ["uc:api.weather"])
        # Should skip silently

    @patch("code_puppy.tools._load_plugin_tools")
    @patch("code_puppy.tools.has_extended_thinking_active", return_value=False)
    @patch("code_puppy.config.get_universal_constructor_enabled", return_value=True)
    @patch("code_puppy.tools._register_uc_tool_wrapper")
    def test_uc_prefixed_enabled(self, mock_uc_reg, mock_uc, mock_ext, mock_load):
        from code_puppy.tools import register_tools_for_agent

        agent = MagicMock()
        register_tools_for_agent(agent, ["uc:api.weather"])
        mock_uc_reg.assert_called_once_with(agent, "api.weather")


class TestRegisterUcToolWrapper:
    @patch("code_puppy.plugins.universal_constructor.registry.get_registry")
    @patch("code_puppy.tools.emit_warning")
    def test_tool_not_found(self, mock_warn, mock_reg):
        from code_puppy.tools import _register_uc_tool_wrapper

        mock_reg.return_value.get_tool.return_value = None
        _register_uc_tool_wrapper(MagicMock(), "bad")
        mock_warn.assert_called()

    @patch("code_puppy.plugins.universal_constructor.registry.get_registry")
    @patch("code_puppy.tools.emit_warning")
    def test_func_not_found(self, mock_warn, mock_reg):
        from code_puppy.tools import _register_uc_tool_wrapper

        tool = MagicMock()
        tool.meta.description = "d"
        tool.docstring = "doc"
        mock_reg.return_value.get_tool.return_value = tool
        mock_reg.return_value.get_tool_function.return_value = None
        _register_uc_tool_wrapper(MagicMock(), "t")
        mock_warn.assert_called()

    @patch("code_puppy.plugins.universal_constructor.registry.get_registry")
    def test_success(self, mock_reg):
        from code_puppy.tools import _register_uc_tool_wrapper

        tool = MagicMock()
        tool.meta.description = "d"
        tool.docstring = "doc"
        mock_reg.return_value.get_tool.return_value = tool

        def my_func(x: int = 1) -> int:
            return x

        mock_reg.return_value.get_tool_function.return_value = my_func
        agent = MagicMock()
        _register_uc_tool_wrapper(agent, "my.tool")
        agent.tool.assert_called_once()

    @patch(
        "code_puppy.plugins.universal_constructor.registry.get_registry",
        side_effect=Exception("boom"),
    )
    @patch("code_puppy.tools.emit_warning")
    def test_exception(self, mock_warn, mock_reg):
        from code_puppy.tools import _register_uc_tool_wrapper

        _register_uc_tool_wrapper(MagicMock(), "t")
        mock_warn.assert_called()

    @patch("code_puppy.plugins.universal_constructor.registry.get_registry")
    @patch("code_puppy.tools.emit_warning")
    def test_register_fails(self, mock_warn, mock_reg):
        from code_puppy.tools import _register_uc_tool_wrapper

        tool = MagicMock()
        tool.meta.description = "d"
        tool.docstring = None
        mock_reg.return_value.get_tool.return_value = tool
        mock_reg.return_value.get_tool_function.return_value = lambda: None
        agent = MagicMock()
        agent.tool.side_effect = Exception("fail")
        _register_uc_tool_wrapper(agent, "t")
        mock_warn.assert_called()


class TestRegisterAllToolsAndGetNames:
    @patch("code_puppy.tools.register_tools_for_agent")
    def test_register_all(self, mock_reg):
        from code_puppy.tools import register_all_tools

        agent = MagicMock()
        register_all_tools(agent, model_name="test")
        mock_reg.assert_called_once()

    @patch("code_puppy.tools._load_plugin_tools")
    def test_get_names(self, mock_load):
        from code_puppy.tools import get_available_tool_names

        names = get_available_tool_names()
        assert isinstance(names, list)
        assert len(names) > 0


class TestExtendedThinkingPromptNote:
    def test_constant_exists(self):
        from code_puppy.tools import EXTENDED_THINKING_PROMPT_NOTE

        assert "extended thinking" in EXTENDED_THINKING_PROMPT_NOTE.lower()
