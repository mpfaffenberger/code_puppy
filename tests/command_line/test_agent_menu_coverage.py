"""Coverage tests for agent_menu.py - exercises all uncovered code paths."""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.command_line.agent_menu import (
    PAGE_SIZE,
    _apply_pinned_model,
    _build_model_picker_choices,
    _get_agent_entries,
    _get_pinned_model,
    _normalize_model_choice,
    _reload_agent_if_current,
    _render_menu_panel,
    _render_preview_panel,
    _sanitize_display_text,
    _select_pinned_model,
    interactive_agent_picker,
)

# --------------- _sanitize_display_text ---------------


class TestSanitizeDisplayText:
    def test_plain_text(self):
        assert _sanitize_display_text("Hello World") == "Hello World"

    def test_strips_emojis(self):
        result = _sanitize_display_text("Code Puppy \U0001f436")
        assert "Code Puppy" in result

    def test_keeps_punctuation(self):
        result = _sanitize_display_text("hello-world_v2.0")
        assert "hello" in result

    def test_keeps_math_and_currency(self):
        result = _sanitize_display_text("$100 + €50 = fun")
        assert "$" in result
        assert "+" in result
        assert "€" in result

    def test_empty_string(self):
        assert _sanitize_display_text("") == ""

    def test_double_spaces_collapsed(self):
        result = _sanitize_display_text("Hello  \U0001f436  World")
        assert "  " not in result


# --------------- _get_pinned_model ---------------


class TestGetPinnedModel:
    @patch(
        "code_puppy.command_line.agent_menu.get_agent_pinned_model",
        return_value="gpt-4",
    )
    def test_builtin_pinned(self, mock_pin):
        assert _get_pinned_model("agent1") == "gpt-4"

    @patch(
        "code_puppy.command_line.agent_menu.get_agent_pinned_model", return_value=None
    )
    @patch("code_puppy.agents.json_agent.discover_json_agents", return_value={})
    def test_no_pinned(self, mock_json, mock_pin):
        assert _get_pinned_model("agent1") is None

    @patch(
        "code_puppy.command_line.agent_menu.get_agent_pinned_model", return_value=None
    )
    def test_json_agent_pinned(self, mock_pin):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"model": "claude-3"}, f)
            f.flush()
            with patch(
                "code_puppy.agents.json_agent.discover_json_agents",
                return_value={"agent1": f.name},
            ):
                assert _get_pinned_model("agent1") == "claude-3"
        os.unlink(f.name)

    @patch(
        "code_puppy.command_line.agent_menu.get_agent_pinned_model", return_value=None
    )
    def test_json_agent_no_model(self, mock_pin):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()
            with patch(
                "code_puppy.agents.json_agent.discover_json_agents",
                return_value={"agent1": f.name},
            ):
                assert _get_pinned_model("agent1") is None
        os.unlink(f.name)

    @patch(
        "code_puppy.command_line.agent_menu.get_agent_pinned_model",
        side_effect=Exception,
    )
    def test_exception_in_builtin(self, mock_pin):
        with patch(
            "code_puppy.agents.json_agent.discover_json_agents", side_effect=Exception
        ):
            assert _get_pinned_model("agent1") is None


# --------------- _build_model_picker_choices ---------------


class TestBuildModelPickerChoices:
    def test_no_pinned_model(self):
        choices = _build_model_picker_choices(None, ["m1", "m2"])
        assert choices[0] == "✓ (unpin)"
        assert any("m1" in c for c in choices)

    def test_with_pinned_model(self):
        choices = _build_model_picker_choices("m1", ["m1", "m2"])
        assert choices[0] == "  (unpin)"
        assert any("m1" in c and "pinned" in c for c in choices)


# --------------- _normalize_model_choice ---------------


class TestNormalizeModelChoice:
    def test_plain(self):
        assert _normalize_model_choice("  gpt-4") == "gpt-4"

    def test_with_checkmark(self):
        assert _normalize_model_choice("✓ gpt-4 (pinned)") == "gpt-4"

    def test_unpin(self):
        assert _normalize_model_choice("✓ (unpin)") == "(unpin)"


# --------------- _select_pinned_model ---------------


class TestSelectPinnedModel:
    @pytest.mark.asyncio
    @patch("code_puppy.command_line.agent_menu.arrow_select_async")
    @patch(
        "code_puppy.command_line.agent_menu.load_model_names", return_value=["m1", "m2"]
    )
    @patch(
        "code_puppy.command_line.agent_menu.get_agent_pinned_model", return_value=None
    )
    async def test_success(self, mock_pin, mock_load, mock_select):
        mock_select.return_value = "  m1"
        result = await _select_pinned_model("agent1")
        assert result == "m1"

    @pytest.mark.asyncio
    @patch(
        "code_puppy.command_line.agent_menu.arrow_select_async",
        side_effect=KeyboardInterrupt,
    )
    @patch("code_puppy.command_line.agent_menu.load_model_names", return_value=["m1"])
    @patch(
        "code_puppy.command_line.agent_menu.get_agent_pinned_model", return_value=None
    )
    async def test_cancelled(self, mock_pin, mock_load, mock_select):
        result = await _select_pinned_model("agent1")
        assert result is None

    @pytest.mark.asyncio
    @patch(
        "code_puppy.command_line.agent_menu.load_model_names",
        side_effect=Exception("fail"),
    )
    async def test_load_error(self, mock_load):
        result = await _select_pinned_model("agent1")
        assert result is None

    @pytest.mark.asyncio
    @patch("code_puppy.command_line.agent_menu.load_model_names", return_value=[])
    @patch(
        "code_puppy.command_line.agent_menu.get_agent_pinned_model", return_value=None
    )
    async def test_empty_models(self, mock_pin, mock_load):
        with patch(
            "code_puppy.command_line.agent_menu.arrow_select_async",
            return_value="✓ (unpin)",
        ):
            result = await _select_pinned_model("agent1")
        assert result == "(unpin)"


# --------------- _reload_agent_if_current ---------------


class TestReloadAgentIfCurrent:
    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    def test_not_current(self, mock_get):
        agent = MagicMock()
        agent.name = "other"
        mock_get.return_value = agent
        _reload_agent_if_current("agent1", "m1")

    @patch("code_puppy.command_line.agent_menu.emit_info")
    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    def test_current_with_pinned(self, mock_get, mock_emit):
        agent = MagicMock()
        agent.name = "agent1"
        mock_get.return_value = agent
        _reload_agent_if_current("agent1", "m1")
        agent.reload_code_generation_agent.assert_called()

    @patch("code_puppy.command_line.agent_menu.emit_info")
    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    def test_current_no_pinned(self, mock_get, mock_emit):
        agent = MagicMock()
        agent.name = "agent1"
        mock_get.return_value = agent
        _reload_agent_if_current("agent1", None)
        assert any("default" in str(c) for c in mock_emit.call_args_list)

    @patch("code_puppy.command_line.agent_menu.emit_warning")
    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    def test_reload_fails(self, mock_get, mock_warn):
        agent = MagicMock()
        agent.name = "agent1"
        agent.reload_code_generation_agent.side_effect = Exception("boom")
        mock_get.return_value = agent
        _reload_agent_if_current("agent1", "m1")
        mock_warn.assert_called()

    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    def test_no_current_agent(self, mock_get):
        mock_get.return_value = None
        _reload_agent_if_current("agent1", "m1")

    @patch("code_puppy.command_line.agent_menu.emit_info")
    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    def test_refresh_config(self, mock_get, mock_emit):
        agent = MagicMock()
        agent.name = "agent1"
        agent.refresh_config = MagicMock()
        mock_get.return_value = agent
        _reload_agent_if_current("agent1", "m1")
        agent.refresh_config.assert_called_once()


# --------------- _apply_pinned_model ---------------


class TestApplyPinnedModel:
    @patch("code_puppy.command_line.agent_menu._reload_agent_if_current")
    @patch("code_puppy.command_line.agent_menu.emit_success")
    @patch("code_puppy.command_line.agent_menu.set_agent_pinned_model")
    @patch("code_puppy.agents.json_agent.discover_json_agents", return_value={})
    def test_builtin_pin(self, mock_json, mock_set, mock_emit, mock_reload):
        _apply_pinned_model("agent1", "gpt-4")
        mock_set.assert_called_with("agent1", "gpt-4")
        mock_emit.assert_called()
        mock_reload.assert_called_with("agent1", "gpt-4")

    @patch("code_puppy.command_line.agent_menu._reload_agent_if_current")
    @patch("code_puppy.command_line.agent_menu.emit_success")
    @patch("code_puppy.command_line.agent_menu.clear_agent_pinned_model")
    @patch("code_puppy.agents.json_agent.discover_json_agents", return_value={})
    def test_builtin_unpin(self, mock_json, mock_clear, mock_emit, mock_reload):
        _apply_pinned_model("agent1", "(unpin)")
        mock_clear.assert_called_with("agent1")
        mock_emit.assert_called()
        mock_reload.assert_called_with("agent1", None)

    @patch("code_puppy.command_line.agent_menu._reload_agent_if_current")
    @patch("code_puppy.command_line.agent_menu.emit_success")
    def test_json_agent_pin(self, mock_emit, mock_reload):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"name": "test"}, f)
            f.flush()
            with patch(
                "code_puppy.agents.json_agent.discover_json_agents",
                return_value={"agent1": f.name},
            ):
                _apply_pinned_model("agent1", "claude-3")
            with open(f.name) as rf:
                data = json.load(rf)
            assert data["model"] == "claude-3"
        os.unlink(f.name)

    @patch("code_puppy.command_line.agent_menu._reload_agent_if_current")
    @patch("code_puppy.command_line.agent_menu.emit_success")
    def test_json_agent_unpin(self, mock_emit, mock_reload):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"name": "test", "model": "gpt-4"}, f)
            f.flush()
            with patch(
                "code_puppy.agents.json_agent.discover_json_agents",
                return_value={"agent1": f.name},
            ):
                _apply_pinned_model("agent1", "(unpin)")
            with open(f.name) as rf:
                data = json.load(rf)
            assert "model" not in data
        os.unlink(f.name)

    @patch("code_puppy.command_line.agent_menu.emit_warning")
    @patch(
        "code_puppy.agents.json_agent.discover_json_agents",
        side_effect=Exception("fail"),
    )
    @patch(
        "code_puppy.command_line.agent_menu.set_agent_pinned_model",
        side_effect=Exception("fail"),
    )
    def test_exception(self, mock_set, mock_json, mock_warn):
        _apply_pinned_model("agent1", "gpt-4")
        mock_warn.assert_called()


# --------------- _get_agent_entries ---------------


class TestGetAgentEntries:
    @patch(
        "code_puppy.command_line.agent_menu.get_agent_descriptions",
        return_value={"a": "Desc A", "b": "Desc B"},
    )
    @patch(
        "code_puppy.command_line.agent_menu.get_available_agents",
        return_value={"b": "B Agent", "a": "A Agent"},
    )
    def test_sorted(self, mock_avail, mock_desc):
        entries = _get_agent_entries()
        assert entries[0][0] == "a"
        assert entries[1][0] == "b"

    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions", return_value={})
    @patch(
        "code_puppy.command_line.agent_menu.get_available_agents",
        return_value={"a": "A"},
    )
    def test_missing_description(self, mock_avail, mock_desc):
        entries = _get_agent_entries()
        assert entries[0][2] == "No description available"


# --------------- _render_menu_panel ---------------


class TestRenderMenuPanel:
    @patch("code_puppy.command_line.agent_menu._get_pinned_model", return_value=None)
    def test_empty_entries(self, mock_pin):
        lines = _render_menu_panel([], 0, 0, "current")
        text = "".join(t for _, t in lines)
        assert "No agents found" in text

    @patch("code_puppy.command_line.agent_menu._get_pinned_model", return_value=None)
    def test_with_entries_selected_current(self, mock_pin):
        entries = [("agent1", "Agent One", "desc")]
        lines = _render_menu_panel(entries, 0, 0, "agent1")
        text = "".join(t for _, t in lines)
        assert "Agent One" in text
        assert "current" in text
        assert "▶" in text

    @patch("code_puppy.command_line.agent_menu._get_pinned_model", return_value="gpt-4")
    def test_with_pinned_model(self, mock_pin):
        entries = [("agent1", "Agent One", "desc")]
        lines = _render_menu_panel(entries, 0, 0, "other")
        text = "".join(t for _, t in lines)
        assert "gpt-4" in text

    @patch("code_puppy.command_line.agent_menu._get_pinned_model", return_value=None)
    def test_not_selected(self, mock_pin):
        entries = [("a1", "A1", "d"), ("a2", "A2", "d")]
        lines = _render_menu_panel(entries, 0, 1, "other")
        text = "".join(t for _, t in lines)
        assert "A1" in text
        assert "A2" in text

    @patch("code_puppy.command_line.agent_menu._get_pinned_model", return_value=None)
    def test_pagination(self, mock_pin):
        entries = [(f"a{i}", f"Agent {i}", "d") for i in range(PAGE_SIZE + 3)]
        lines = _render_menu_panel(entries, 1, PAGE_SIZE, "")
        text = "".join(t for _, t in lines)
        assert "Page 2/" in text


# --------------- _render_preview_panel ---------------


class TestRenderPreviewPanel:
    def test_no_entry(self):
        lines = _render_preview_panel(None, "current")
        text = "".join(t for _, t in lines)
        assert "No agent selected" in text

    @patch("code_puppy.command_line.agent_menu._get_pinned_model", return_value=None)
    def test_with_entry_current(self, mock_pin):
        lines = _render_preview_panel(("a1", "Agent 1", "A great agent"), "a1")
        text = "".join(t for _, t in lines)
        assert "Agent 1" in text
        assert "a1" in text
        assert "Currently Active" in text
        assert "default" in text

    @patch("code_puppy.command_line.agent_menu._get_pinned_model", return_value="gpt-4")
    def test_with_pinned_not_current(self, mock_pin):
        lines = _render_preview_panel(("a1", "Agent 1", "desc"), "other")
        text = "".join(t for _, t in lines)
        assert "gpt-4" in text
        assert "Not active" in text

    @patch("code_puppy.command_line.agent_menu._get_pinned_model", return_value=None)
    def test_long_description_wraps(self, mock_pin):
        long_desc = "word " * 50
        lines = _render_preview_panel(("a1", "A1", long_desc), "a1")
        text = "".join(t for _, t in lines)
        assert "word" in text

    @patch("code_puppy.command_line.agent_menu._get_pinned_model", return_value=None)
    def test_multiline_description(self, mock_pin):
        desc = "Line one\nLine two"
        lines = _render_preview_panel(("a1", "A1", desc), "a1")
        text = "".join(t for _, t in lines)
        assert "Line one" in text
        assert "Line two" in text


# --------------- interactive_agent_picker ---------------


class TestInteractiveAgentPicker:
    @pytest.mark.asyncio
    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions", return_value={})
    @patch("code_puppy.command_line.agent_menu.get_available_agents", return_value={})
    async def test_no_agents(self, mock_avail, mock_desc, mock_current):
        result = await interactive_agent_picker()
        assert result is None

    @pytest.mark.asyncio
    @patch("code_puppy.command_line.agent_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.agent_menu.emit_info")
    @patch("code_puppy.command_line.agent_menu.Application")
    @patch("sys.stdout")
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("code_puppy.command_line.agent_menu._get_pinned_model", return_value=None)
    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    @patch(
        "code_puppy.command_line.agent_menu.get_agent_descriptions",
        return_value={"a1": "Desc"},
    )
    @patch(
        "code_puppy.command_line.agent_menu.get_available_agents",
        return_value={"a1": "Agent 1"},
    )
    async def test_select_agent_result_none(
        self,
        mock_avail,
        mock_desc,
        mock_current,
        mock_pin,
        mock_sleep,
        mock_stdout,
        mock_app_cls,
        mock_emit,
        mock_await,
    ):
        agent = MagicMock()
        agent.name = "a1"
        mock_current.return_value = agent

        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.run_async = AsyncMock()

        result = await interactive_agent_picker()
        assert result is None

    @pytest.mark.asyncio
    @patch("code_puppy.command_line.agent_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.agent_menu.emit_info")
    @patch("code_puppy.command_line.agent_menu.Application")
    @patch("sys.stdout")
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("code_puppy.command_line.agent_menu._get_pinned_model", return_value=None)
    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    @patch(
        "code_puppy.command_line.agent_menu.get_agent_descriptions",
        return_value={"a1": "Desc"},
    )
    @patch(
        "code_puppy.command_line.agent_menu.get_available_agents",
        return_value={"a1": "Agent 1"},
    )
    async def test_current_agent_none(
        self,
        mock_avail,
        mock_desc,
        mock_current,
        mock_pin,
        mock_sleep,
        mock_stdout,
        mock_app_cls,
        mock_emit,
        mock_await,
    ):
        mock_current.return_value = None
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_app.run_async = AsyncMock()
        result = await interactive_agent_picker()
        assert result is None
