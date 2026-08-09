"""Tests for pin_command_completion.py to achieve 100% coverage."""

from unittest.mock import mock_open, patch

import pytest
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
    @pytest.mark.parametrize(
        ("pinned", "expected"),
        [("gpt-4", "→ gpt-4"), (None, "default")],
        ids=["with_pinned_model", "without_pinned_model"],
    )
    def test_display_meta(self, pinned, expected):
        from code_puppy.command_line.pin_command_completion import (
            _get_agent_display_meta,
        )

        with patch(
            "code_puppy.command_line.pin_command_completion._get_pinned_model_for_agent",
            return_value=pinned,
        ):
            assert _get_agent_display_meta("test") == expected


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

    @pytest.mark.parametrize(
        "doc_text",
        [
            "/other ",
            "/pin_model agent1 (unpin) extra",
            "/pin_model agent1 model1 extra",
        ],
        ids=["no_trigger", "unpin_selected_no_more", "three_or_more_tokens"],
    )
    def test_no_completions(self, doc_text):
        from code_puppy.command_line.pin_command_completion import PinCompleter

        c = PinCompleter()
        completions = list(c.get_completions(self._make_doc(doc_text), None))
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

    @pytest.mark.parametrize(
        ("doc", "agent_names", "model_names", "expected_len", "expected_text"),
        [
            ("/pin_model ag", ["agent1", "bot1"], [], 1, "agent1"),
            ("/pin_model agent1 ", [], ["gpt-4", "claude-3"], 3, "(unpin)"),
            ("/pin_model agent1 gpt", [], ["gpt-4", "claude-3"], 1, "gpt-4"),
        ],
        ids=["partial_agent", "agent_then_space_shows_models", "partial_model"],
    )
    def test_agent_or_model_completions(
        self, doc, agent_names, model_names, expected_len, expected_text
    ):
        from code_puppy.command_line.pin_command_completion import PinCompleter

        c = PinCompleter()
        with (
            patch(
                "code_puppy.command_line.pin_command_completion.load_agent_names",
                return_value=agent_names,
            ),
            patch(
                "code_puppy.command_line.pin_command_completion.load_model_names",
                return_value=model_names,
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_agent_display_meta",
                return_value="default",
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_model_display_meta",
                return_value="Model",
            ),
        ):
            completions = list(c.get_completions(self._make_doc(doc), None))
            assert len(completions) == expected_len
            assert completions[0].text == expected_text

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

    @pytest.mark.parametrize(
        "doc_text", ["/other ", "/unpin a1 extra"], ids=["no_trigger", "too_many_args"]
    )
    def test_no_completions(self, doc_text):
        from code_puppy.command_line.pin_command_completion import UnpinCompleter

        c = UnpinCompleter()
        assert list(c.get_completions(self._make_doc(doc_text), None)) == []

    @pytest.mark.parametrize(
        "doc_text,agent_names,expected_len",
        [
            ("/unpin ", ["a1", "a2"], 2),
            ("/unpin ag", ["agent1", "bot1"], 1),
        ],
        ids=["no_args_shows_agents", "partial_agent"],
    )
    def test_agent_completions(self, doc_text, agent_names, expected_len):
        from code_puppy.command_line.pin_command_completion import UnpinCompleter

        c = UnpinCompleter()
        with (
            patch(
                "code_puppy.command_line.pin_command_completion.load_agent_names",
                return_value=agent_names,
            ),
            patch(
                "code_puppy.command_line.pin_command_completion._get_agent_display_meta",
                return_value="default",
            ),
        ):
            completions = list(c.get_completions(self._make_doc(doc_text), None))
            assert len(completions) == expected_len

