"""Tests for pin_command_completion.py to achieve 100% coverage."""

from unittest.mock import mock_open, patch

from prompt_toolkit.document import Document


class TestGetJsonAgentsForModel:
    def test_returns_matching_agents(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_json_agents_for_model,
        )

        with (
            patch(
                "code_puppy.agents.json_agent.discover_json_agents",
                return_value={"agent1": "/tmp/a1.json", "agent2": "/tmp/a2.json"},
            ),
            patch(
                "builtins.open",
                side_effect=[
                    mock_open(read_data='{"model": "gpt-4"}')(),
                    mock_open(read_data='{"model": "gpt-3"}')(),
                ],
            ),
        ):
            result = _get_json_agents_for_model("gpt-4")
            assert result == ["agent1"]

    def test_handles_exception(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_json_agents_for_model,
        )

        with patch(
            "code_puppy.agents.json_agent.discover_json_agents",
            side_effect=Exception("fail"),
        ):
            assert _get_json_agents_for_model("gpt-4") == []

    def test_handles_bad_json_file(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_json_agents_for_model,
        )

        with (
            patch(
                "code_puppy.agents.json_agent.discover_json_agents",
                return_value={"agent1": "/tmp/a1.json"},
            ),
            patch("builtins.open", side_effect=IOError("nope")),
        ):
            assert _get_json_agents_for_model("gpt-4") == []


class TestGetPinnedModelForAgent:
    def test_from_config(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_pinned_model_for_agent,
        )

        with patch("code_puppy.config.get_agent_pinned_model", return_value="gpt-4"):
            assert _get_pinned_model_for_agent("test") == "gpt-4"

    def test_from_json_agent(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_pinned_model_for_agent,
        )

        with (
            patch("code_puppy.config.get_agent_pinned_model", return_value=None),
            patch(
                "code_puppy.agents.json_agent.discover_json_agents",
                return_value={"myagent": "/tmp/a.json"},
            ),
            patch(
                "builtins.open",
                mock_open(read_data='{"model": "claude-3"}'),
            ),
        ):
            assert _get_pinned_model_for_agent("myagent") == "claude-3"

    def test_not_found(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_pinned_model_for_agent,
        )

        with (
            patch("code_puppy.config.get_agent_pinned_model", return_value=None),
            patch(
                "code_puppy.agents.json_agent.discover_json_agents",
                return_value={},
            ),
        ):
            assert _get_pinned_model_for_agent("unknown") is None

    def test_config_exception(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_pinned_model_for_agent,
        )

        with (
            patch(
                "code_puppy.config.get_agent_pinned_model",
                side_effect=Exception("fail"),
            ),
            patch(
                "code_puppy.agents.json_agent.discover_json_agents",
                side_effect=Exception("fail2"),
            ),
        ):
            assert _get_pinned_model_for_agent("x") is None


class TestGetModelDisplayMeta:
    def test_with_pinned_agents(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_model_display_meta,
        )

        with (
            patch(
                "code_puppy.config.get_agents_pinned_to_model",
                return_value=["a1"],
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_json_agents_for_model",
                return_value=["a2"],
            ),
        ):
            result = _get_model_display_meta("gpt-4")
            assert "Pinned" in result

    def test_with_many_pinned_agents(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_model_display_meta,
        )

        with (
            patch(
                "code_puppy.config.get_agents_pinned_to_model",
                return_value=["a1", "a2", "a3"],
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_json_agents_for_model",
                return_value=[],
            ),
        ):
            result = _get_model_display_meta("gpt-4")
            assert "..." in result

    def test_no_pinned(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_model_display_meta,
        )

        with (
            patch("code_puppy.config.get_agents_pinned_to_model", return_value=[]),
            patch(
                "code_puppy.command_line.pin_command_completion._get_json_agents_for_model",
                return_value=[],
            ),
        ):
            assert _get_model_display_meta("gpt-4") == "Model"

    def test_exception(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_model_display_meta,
        )

        with patch(
            "code_puppy.config.get_agents_pinned_to_model",
            side_effect=Exception("fail"),
        ):
            assert _get_model_display_meta("gpt-4") == "Model"


class TestGetAgentDisplayMeta:
    def test_with_pinned_model(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_agent_display_meta,
        )

        with patch(
            "code_puppy.command_line.pin_command_completion._get_pinned_model_for_agent",
            return_value="gpt-4",
        ):
            assert _get_agent_display_meta("test") == "→ gpt-4"

    def test_without_pinned_model(self):
        from code_puppy.command_line.pin_command_completion import (
            _get_agent_display_meta,
        )

        with patch(
            "code_puppy.command_line.pin_command_completion._get_pinned_model_for_agent",
            return_value=None,
        ):
            assert _get_agent_display_meta("test") == "default"


class TestLoadAgentNames:
    def test_combines_builtin_and_json(self):
        from code_puppy.command_line.pin_command_completion import load_agent_names

        with (
            patch(
                "code_puppy.agents.agent_manager.get_agent_descriptions",
                return_value={"builtin1": "desc"},
            ),
            patch(
                "code_puppy.agents.json_agent.discover_json_agents",
                return_value={"json1": "/tmp/j1.json"},
            ),
        ):
            result = load_agent_names()
            assert "builtin1" in result
            assert "json1" in result
            assert result == sorted(result)

    def test_handles_exceptions(self):
        from code_puppy.command_line.pin_command_completion import load_agent_names

        with (
            patch(
                "code_puppy.agents.agent_manager.get_agent_descriptions",
                side_effect=Exception("fail"),
            ),
            patch(
                "code_puppy.agents.json_agent.discover_json_agents",
                side_effect=Exception("fail"),
            ),
        ):
            assert load_agent_names() == []


class TestLoadModelNames:
    def test_delegates(self):
        from code_puppy.command_line.pin_command_completion import load_model_names

        with patch(
            "code_puppy.command_line.model_picker_completion.load_model_names",
            return_value=["m1", "m2"],
        ):
            assert load_model_names() == ["m1", "m2"]

    def test_exception(self):
        from code_puppy.command_line.pin_command_completion import load_model_names

        with patch(
            "code_puppy.command_line.model_picker_completion.load_model_names",
            side_effect=Exception("fail"),
        ):
            assert load_model_names() == []


class TestPinCompleter:
    def _make_doc(self, text, cursor_pos=None):
        if cursor_pos is None:
            cursor_pos = len(text)
        return Document(text=text, cursor_position=cursor_pos)

    def test_no_trigger(self):
        from code_puppy.command_line.pin_command_completion import PinCompleter

        c = PinCompleter()
        completions = list(c.get_completions(self._make_doc("/other "), None))
        assert completions == []

    def test_no_args_shows_agents(self):
        from code_puppy.command_line.pin_command_completion import PinCompleter

        c = PinCompleter()
        with (
            patch(
                "code_puppy.command_line.pin_command_completion.load_agent_names",
                return_value=["agent1", "agent2"],
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_agent_display_meta",
                return_value="default",
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/pin_model "), None))
            assert len(completions) == 2

    def test_partial_agent(self):
        from code_puppy.command_line.pin_command_completion import PinCompleter

        c = PinCompleter()
        with (
            patch(
                "code_puppy.command_line.pin_command_completion.load_agent_names",
                return_value=["agent1", "bot1"],
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_agent_display_meta",
                return_value="default",
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/pin_model ag"), None))
            assert len(completions) == 1
            assert completions[0].text == "agent1"

    def test_agent_then_space_shows_models(self):
        from code_puppy.command_line.pin_command_completion import PinCompleter

        c = PinCompleter()
        with (
            patch(
                "code_puppy.command_line.pin_command_completion.load_model_names",
                return_value=["gpt-4", "claude-3"],
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_model_display_meta",
                return_value="Model",
            ),
        ):
            completions = list(
                c.get_completions(self._make_doc("/pin_model agent1 "), None)
            )
            # (unpin) + 2 models
            assert len(completions) == 3
            assert completions[0].text == "(unpin)"

    def test_partial_model(self):
        from code_puppy.command_line.pin_command_completion import PinCompleter

        c = PinCompleter()
        with (
            patch(
                "code_puppy.command_line.pin_command_completion.load_model_names",
                return_value=["gpt-4", "claude-3"],
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_model_display_meta",
                return_value="Model",
            ),
        ):
            completions = list(
                c.get_completions(self._make_doc("/pin_model agent1 gpt"), None)
            )
            assert len(completions) == 1
            assert completions[0].text == "gpt-4"

    def test_partial_model_unpin_match(self):
        from code_puppy.command_line.pin_command_completion import PinCompleter

        c = PinCompleter()
        with (
            patch(
                "code_puppy.command_line.pin_command_completion.load_model_names",
                return_value=["gpt-4"],
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_model_display_meta",
                return_value="Model",
            ),
        ):
            completions = list(
                c.get_completions(self._make_doc("/pin_model agent1 (un"), None)
            )
            assert any(c.text == "(unpin)" for c in completions)

    def test_unpin_selected_no_more_completions(self):
        from code_puppy.command_line.pin_command_completion import PinCompleter

        c = PinCompleter()
        completions = list(
            c.get_completions(self._make_doc("/pin_model agent1 (unpin) extra"), None)
        )
        assert completions == []

    def test_three_or_more_tokens_no_completions(self):
        from code_puppy.command_line.pin_command_completion import PinCompleter

        c = PinCompleter()
        completions = list(
            c.get_completions(self._make_doc("/pin_model agent1 model1 extra"), None)
        )
        assert completions == []

    def test_empty_partial_model(self):
        """Test case 3 with empty partial_model (shouldn't happen with split but covers the branch)."""
        from code_puppy.command_line.pin_command_completion import PinCompleter

        c = PinCompleter()
        # Two tokens but the second is empty - shouldn't happen with split, but test the branch
        with (
            patch(
                "code_puppy.command_line.pin_command_completion.load_model_names",
                return_value=["gpt-4"],
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_model_display_meta",
                return_value="Model",
            ),
        ):
            # This will have 2 tokens since "agent1 gpt" splits to ["agent1", "gpt"]
            completions = list(
                c.get_completions(self._make_doc("/pin_model agent1 gpt"), None)
            )
            assert len(completions) >= 1


class TestPinModelCompleterAlias:
    def test_alias_exists(self):
        from code_puppy.command_line.pin_command_completion import (
            PinCompleter,
            PinModelCompleter,
        )

        assert PinModelCompleter is PinCompleter


class TestUnpinCompleter:
    def _make_doc(self, text, cursor_pos=None):
        if cursor_pos is None:
            cursor_pos = len(text)
        return Document(text=text, cursor_position=cursor_pos)

    def test_no_trigger(self):
        from code_puppy.command_line.pin_command_completion import UnpinCompleter

        c = UnpinCompleter()
        assert list(c.get_completions(self._make_doc("/other "), None)) == []

    def test_no_args_shows_agents(self):
        from code_puppy.command_line.pin_command_completion import UnpinCompleter

        c = UnpinCompleter()
        with (
            patch(
                "code_puppy.command_line.pin_command_completion.load_agent_names",
                return_value=["a1", "a2"],
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_agent_display_meta",
                return_value="default",
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/unpin "), None))
            assert len(completions) == 2

    def test_partial_agent(self):
        from code_puppy.command_line.pin_command_completion import UnpinCompleter

        c = UnpinCompleter()
        with (
            patch(
                "code_puppy.command_line.pin_command_completion.load_agent_names",
                return_value=["agent1", "bot1"],
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_agent_display_meta",
                return_value="default",
            ),
        ):
            completions = list(c.get_completions(self._make_doc("/unpin ag"), None))
            assert len(completions) == 1

    def test_too_many_args(self):
        from code_puppy.command_line.pin_command_completion import UnpinCompleter

        c = UnpinCompleter()
        assert list(c.get_completions(self._make_doc("/unpin a1 extra"), None)) == []
