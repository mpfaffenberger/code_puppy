"""Tests for the builtin ``no_tools`` plugin and its core kill-switch (#182)."""

import argparse
import importlib
from unittest.mock import MagicMock

import pytest

import code_puppy.tools as tools_pkg
from code_puppy.plugins.no_tools import register_callbacks as no_tools_plugin


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv(tools_pkg.NO_TOOLS_ENV_VAR, raising=False)
    return monkeypatch


def _parse(argv):
    parser = argparse.ArgumentParser()
    no_tools_plugin._register_cli_args(parser)
    return parser.parse_args(argv)


class TestToolsDisabled:
    def test_default_off(self, clean_env):
        assert tools_pkg.tools_disabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " 1 "])
    def test_truthy_values(self, clean_env, value):
        clean_env.setenv(tools_pkg.NO_TOOLS_ENV_VAR, value)
        assert tools_pkg.tools_disabled() is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "banana"])
    def test_falsy_values(self, clean_env, value):
        clean_env.setenv(tools_pkg.NO_TOOLS_ENV_VAR, value)
        assert tools_pkg.tools_disabled() is False


class TestCliFlag:
    def test_flag_registered_and_default_false(self, clean_env):
        args = _parse([])
        assert args.no_tools is False

    def test_flag_sets_env_var(self, clean_env):
        args = _parse(["--no-tools"])
        assert args.no_tools is True
        result = no_tools_plugin._handle_cli_args(args)
        assert result is None  # never short-circuits startup
        assert tools_pkg.tools_disabled() is True

    def test_absent_flag_does_not_touch_env(self, clean_env):
        no_tools_plugin._handle_cli_args(_parse([]))
        assert tools_pkg.tools_disabled() is False

    def test_missing_attr_is_harmless(self, clean_env):
        # Namespace without no_tools (e.g. parser built without the plugin)
        assert no_tools_plugin._handle_cli_args(argparse.Namespace()) is None
        assert tools_pkg.tools_disabled() is False


class TestRegistrationSkipped:
    def test_register_tools_for_agent_noop_when_disabled(self, clean_env):
        clean_env.setenv(tools_pkg.NO_TOOLS_ENV_VAR, "1")
        agent = MagicMock()
        tools_pkg.register_tools_for_agent(
            agent, ["read_file", "grep"], agent_name="code-puppy"
        )
        agent.tool.assert_not_called()
        agent.tool_plain.assert_not_called()

    def test_register_all_tools_noop_when_disabled(self, clean_env):
        clean_env.setenv(tools_pkg.NO_TOOLS_ENV_VAR, "1")
        agent = MagicMock()
        tools_pkg.register_all_tools(agent)
        agent.tool.assert_not_called()

    def test_registration_still_works_when_enabled(self, clean_env):
        agent = MagicMock()
        tools_pkg.register_tools_for_agent(agent, ["agent_share_your_reasoning"])
        assert agent.tool.called or agent.tool_plain.called


class TestMcpSkipped:
    def test_load_mcp_servers_empty_when_disabled(self, clean_env):
        clean_env.setenv(tools_pkg.NO_TOOLS_ENV_VAR, "1")
        builder = importlib.import_module("code_puppy.agents._builder")
        assert builder.load_mcp_servers(agent_name="code-puppy") == []
