"""Unit tests for the switch_agent_resume plugin and TTY tracking functions.

Covers:
  - get_terminal_tty()
  - record_terminal_session()
  - get_last_terminal_session()
  - finalize_autosave_session()
  - _cleanup_orphaned_tty_sessions()
  - _handle_switch_agent() command handler
  - _do_switch_and_resume() helper
  - custom_command_help callback
  - callback registration

PATCHING STRATEGY
-----------------
The plugin uses ``from module import name`` inside function bodies (lazy
imports).  ``patch("a.b.name")`` only works when ``a.b`` is already in
``sys.modules``.  We ensure that by importing every target module at module
scope below, then use ``patch.object`` or string-based patches — both work
once the module is cached.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# MCP compatibility shim
# pydantic_ai.mcp imports several mcp.client.* and mcp.shared.* submodules.
# The conftest mocks mcp/mcp.client/mcp.client.session but misses the rest.
# We extend coverage here BEFORE importing any code that triggers pydantic_ai.mcp.
# ---------------------------------------------------------------------------
_MCP_EXTRAS = [
    "mcp.client.sse",
    "mcp.client.stdio",
    "mcp.client.streamable_http",
    "mcp.shared",
    "mcp.shared.exceptions",
    "mcp.shared.context",
    "mcp.shared.message",
    "mcp.shared.session",
]
for _mod_name in _MCP_EXTRAS:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# Pre-import every lazy-imported module used by the plugin so that
# unittest.mock.patch() can find them via sys.modules.
import code_puppy.agents as _agents_mod  # noqa: E402, F401
import code_puppy.command_line.agent_menu as _agent_menu_mod  # noqa: E402, F401
import code_puppy.command_line.autosave_menu as _autosave_menu_mod  # noqa: E402, F401
import code_puppy.config as _config_mod  # noqa: E402, F401
import code_puppy.messaging as _messaging_mod  # noqa: E402, F401
import code_puppy.session_storage as _session_storage_mod  # noqa: E402, F401

# ---------------------------------------------------------------------------
# TTY tracking: get_terminal_tty
# ---------------------------------------------------------------------------


class TestGetTerminalTty:
    """Tests for code_puppy.config.get_terminal_tty()."""

    def test_returns_tty_name_when_stdin_is_tty(self):
        """Returns the tty device path when os.ttyname succeeds."""
        from code_puppy.config import get_terminal_tty

        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 0

        with (
            patch("sys.stdin", mock_stdin),
            patch.object(_config_mod.os, "ttyname", return_value="/dev/ttys001"),
        ):
            result = get_terminal_tty()

        assert result == "/dev/ttys001"

    def test_returns_none_when_stdin_not_a_tty(self):
        """Returns None when os.ttyname raises OSError (not a terminal)."""
        from code_puppy.config import get_terminal_tty

        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 0

        with (
            patch("sys.stdin", mock_stdin),
            patch.object(_config_mod.os, "ttyname", side_effect=OSError("not a tty")),
        ):
            result = get_terminal_tty()

        assert result is None

    def test_returns_none_on_attribute_error(self):
        """Returns None when stdin raises AttributeError (e.g. no fileno method)."""
        from code_puppy.config import get_terminal_tty

        mock_stdin = MagicMock()
        mock_stdin.fileno.side_effect = AttributeError("no fileno")

        with patch("sys.stdin", mock_stdin):
            result = get_terminal_tty()

        assert result is None


# ---------------------------------------------------------------------------
# TTY tracking: record_terminal_session
# ---------------------------------------------------------------------------


class TestRecordTerminalSession:
    """Tests for code_puppy.config.record_terminal_session()."""

    def test_creates_txt_file_for_tty(self, tmp_path):
        """Creates a per-TTY .txt file with the session name (no JSON mapping)."""
        from code_puppy.config import record_terminal_session

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            record_terminal_session("my-session-001")

        session_file = tmp_path / "tty_sessions" / "dev_ttys001.txt"
        assert session_file.exists()
        assert session_file.read_text().strip() == "my-session-001"

    def test_different_ttys_write_different_files(self, tmp_path):
        """Each TTY gets its own isolated file; concurrent writes cannot clobber each other."""
        from code_puppy.config import record_terminal_session

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys099"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            record_terminal_session("session-for-other")

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            record_terminal_session("new-session-001")

        other_file = tmp_path / "tty_sessions" / "dev_ttys099.txt"
        our_file = tmp_path / "tty_sessions" / "dev_ttys001.txt"
        assert other_file.read_text().strip() == "session-for-other"  # unaffected
        assert our_file.read_text().strip() == "new-session-001"  # ours written

    def test_noop_when_tty_is_none(self, tmp_path):
        """Does nothing (no file created) when get_terminal_tty returns None."""
        from code_puppy.config import record_terminal_session

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value=None),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            record_terminal_session("should-not-be-written")

        tty_sessions_dir = tmp_path / "tty_sessions"
        assert not tty_sessions_dir.exists()

    def test_overwrites_own_entry_on_second_call(self, tmp_path):
        """A second call for the same TTY replaces the previous session name."""
        from code_puppy.config import record_terminal_session

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            record_terminal_session("session-first")
            record_terminal_session("session-second")

        session_file = tmp_path / "tty_sessions" / "dev_ttys001.txt"
        assert session_file.read_text().strip() == "session-second"

    def test_startup_record_can_preserve_existing_marker(self, tmp_path):
        """overwrite=False preserves previous real terminal session across restarts."""
        from code_puppy.config import record_terminal_session

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            record_terminal_session("auto_session_20260101_010101")
            record_terminal_session("auto_session_20260101_020202", overwrite=False)

        session_file = tmp_path / "tty_sessions" / "dev_ttys001.txt"
        assert session_file.read_text().strip() == "auto_session_20260101_010101"


# ---------------------------------------------------------------------------
# TTY tracking: get_last_terminal_session
# ---------------------------------------------------------------------------


class TestGetLastTerminalSession:
    """Tests for code_puppy.config.get_last_terminal_session()."""

    def test_returns_session_for_current_tty(self, tmp_path):
        """Returns the session name previously recorded for this TTY."""
        from code_puppy.config import get_last_terminal_session

        tty_sessions_dir = tmp_path / "tty_sessions"
        tty_sessions_dir.mkdir()
        (tty_sessions_dir / "dev_ttys001.txt").write_text(
            "auto_session_20260101_010101"
        )

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            result = get_last_terminal_session()

        assert result == "auto_session_20260101_010101"

    def test_returns_none_when_tty_not_in_file(self, tmp_path):
        """Returns None when no .txt file exists for our TTY (only another TTY has one)."""
        from code_puppy.config import get_last_terminal_session

        tty_sessions_dir = tmp_path / "tty_sessions"
        tty_sessions_dir.mkdir()
        (tty_sessions_dir / "dev_ttys099.txt").write_text("other-session")

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            result = get_last_terminal_session()

        assert result is None

    def test_returns_none_when_file_does_not_exist(self, tmp_path):
        """Returns None gracefully when no session file exists yet for this TTY."""
        from code_puppy.config import get_last_terminal_session

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            result = get_last_terminal_session()

        assert result is None

    def test_returns_none_when_tty_is_none(self, tmp_path):
        """Returns None when there's no TTY available at all."""
        from code_puppy.config import get_last_terminal_session

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value=None),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            result = get_last_terminal_session()

        assert result is None

    def test_returns_none_for_path_traversal_marker(self, tmp_path):
        """Rejects tampered marker values that could traverse out of AUTOSAVE_DIR."""
        from code_puppy.config import get_last_terminal_session

        tty_sessions_dir = tmp_path / "tty_sessions"
        tty_sessions_dir.mkdir()
        (tty_sessions_dir / "dev_ttys001.txt").write_text("../../payload")

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            result = get_last_terminal_session()

        assert result is None

    def test_returns_none_for_malformed_marker(self, tmp_path):
        """Rejects non-autosave marker names instead of trusting arbitrary pickle names."""
        from code_puppy.config import get_last_terminal_session

        tty_sessions_dir = tmp_path / "tty_sessions"
        tty_sessions_dir.mkdir()
        (tty_sessions_dir / "dev_ttys001.txt").write_text("manual_session")

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            result = get_last_terminal_session()

        assert result is None


# ---------------------------------------------------------------------------
# TTY tracking: finalize_autosave_session
# ---------------------------------------------------------------------------


class TestFinalizeAutosaveSession:
    """Tests for code_puppy.config.finalize_autosave_session()."""

    def test_calls_record_terminal_session_before_rotating(self):
        """record_terminal_session is called with current session name before rotate."""
        from code_puppy.config import finalize_autosave_session

        call_order: list[str] = []

        def fake_record(name: str) -> None:
            call_order.append(f"record:{name}")

        def fake_autosave() -> None:
            call_order.append("autosave")

        def fake_rotate() -> str:
            call_order.append("rotate")
            return "new-session-id"

        with (
            patch.object(
                _config_mod,
                "get_current_autosave_session_name",
                return_value="current-session",
            ),
            patch.object(
                _config_mod, "record_terminal_session", side_effect=fake_record
            ),
            patch.object(
                _config_mod,
                "auto_save_session_if_enabled",
                side_effect=fake_autosave,
            ),
            patch.object(_config_mod, "rotate_autosave_id", side_effect=fake_rotate),
        ):
            new_id = finalize_autosave_session()

        assert new_id == "new-session-id"
        assert call_order[0] == "record:current-session", (
            "record_terminal_session must be called FIRST"
        )
        assert "rotate" in call_order

    def test_returns_new_session_id(self):
        """finalize_autosave_session returns whatever rotate_autosave_id returns."""
        from code_puppy.config import finalize_autosave_session

        with (
            patch.object(
                _config_mod, "get_current_autosave_session_name", return_value="s"
            ),
            patch.object(_config_mod, "record_terminal_session"),
            patch.object(_config_mod, "auto_save_session_if_enabled"),
            patch.object(
                _config_mod, "rotate_autosave_id", return_value="brand-new-id"
            ),
        ):
            result = finalize_autosave_session()

        assert result == "brand-new-id"


# ---------------------------------------------------------------------------
# Helpers shared across plugin handler tests
# ---------------------------------------------------------------------------


def _make_mock_agent(
    name: str = "puppy",
    display_name: str = "Puppy",
    description: str = "A helpful agent",
) -> MagicMock:
    agent = MagicMock()
    agent.name = name
    agent.display_name = display_name
    agent.description = description
    agent.reload_code_generation_agent = MagicMock()
    agent.set_message_history = MagicMock()
    agent.estimate_tokens_for_message = MagicMock(return_value=10)
    return agent


# ---------------------------------------------------------------------------
# Plugin command handler: _handle_switch_agent
# ---------------------------------------------------------------------------


class TestHandleSwitchAgent:
    """Tests for _handle_switch_agent in the switch_agent_resume plugin."""

    def _import(self):
        from code_puppy.plugins.switch_agent_resume.register_callbacks import (
            _handle_switch_agent,
        )

        return _handle_switch_agent

    def test_returns_none_for_unrelated_command(self):
        """Returns None for commands that aren't 'switch-agent' or 'sa'."""
        handler = self._import()
        result = handler("/agent puppy", "agent")
        assert result is None

    def test_returns_none_for_help_command(self):
        """Returns None for the 'help' command name."""
        handler = self._import()
        result = handler("/help", "help")
        assert result is None

    def test_sa_alias_routes_through_same_handler(self):
        """The /sa alias is handled identically to /switch-agent."""
        handler = self._import()

        import code_puppy.plugins.switch_agent_resume.register_callbacks as plugin_mod

        with (
            patch.object(
                _agents_mod,
                "get_available_agents",
                return_value={"wiggum": MagicMock()},
            ),
            patch.object(
                plugin_mod, "_do_switch_and_resume", return_value=True
            ) as mock_switch,
        ):
            result = handler("/sa wiggum", "sa")

        mock_switch.assert_called_once_with("wiggum")
        assert result is True

    def test_switch_agent_routes_to_do_switch(self):
        """Valid /switch-agent <name> calls _do_switch_and_resume."""
        handler = self._import()

        import code_puppy.plugins.switch_agent_resume.register_callbacks as plugin_mod

        with (
            patch.object(
                _agents_mod,
                "get_available_agents",
                return_value={"wiggum": MagicMock()},
            ),
            patch.object(
                plugin_mod, "_do_switch_and_resume", return_value=True
            ) as mock_switch,
        ):
            result = handler("/switch-agent wiggum", "switch-agent")

        mock_switch.assert_called_once_with("wiggum")
        assert result is True

    def test_unknown_agent_name_calls_interactive_picker(self):
        """If the agent name is not in available agents, falls through to picker."""
        handler = self._import()

        import code_puppy.plugins.switch_agent_resume.register_callbacks as plugin_mod

        mock_picker = AsyncMock(return_value="puppy")

        with (
            patch.object(
                _agents_mod,
                "get_available_agents",
                return_value={"puppy": MagicMock()},  # "unknownagent" is not here
            ),
            patch.object(_agent_menu_mod, "interactive_agent_picker", mock_picker),
            patch.object(plugin_mod, "_do_switch_and_resume", return_value=True),
        ):
            handler("/switch-agent unknownagent", "switch-agent")

        mock_picker.assert_called_once()

    def test_no_args_shows_interactive_picker(self):
        """/switch-agent with no arguments shows the interactive picker."""
        handler = self._import()

        import code_puppy.plugins.switch_agent_resume.register_callbacks as plugin_mod

        mock_picker = AsyncMock(return_value="puppy")

        with (
            patch.object(
                _agents_mod,
                "get_available_agents",
                return_value={"puppy": MagicMock()},
            ),
            patch.object(_agent_menu_mod, "interactive_agent_picker", mock_picker),
            patch.object(plugin_mod, "_do_switch_and_resume", return_value=True),
        ):
            handler("/switch-agent", "switch-agent")

        mock_picker.assert_called_once()

    def test_picker_cancelled_returns_true_with_warning(self):
        """When picker returns None/empty, emits warning and returns True."""
        handler = self._import()

        mock_picker = AsyncMock(return_value=None)

        with (
            patch.object(_agents_mod, "get_available_agents", return_value={}),
            patch.object(_agent_menu_mod, "interactive_agent_picker", mock_picker),
            patch.object(_messaging_mod, "emit_warning") as mock_warn,
        ):
            result = handler("/switch-agent", "switch-agent")

        assert result is True
        mock_warn.assert_called_once()


# ---------------------------------------------------------------------------
# Plugin command handler: _do_switch_and_resume
# ---------------------------------------------------------------------------


class TestDoSwitchAndResume:
    """Tests for _do_switch_and_resume in the switch_agent_resume plugin."""

    def _import(self):
        from code_puppy.plugins.switch_agent_resume.register_callbacks import (
            _do_switch_and_resume,
        )

        return _do_switch_and_resume

    def test_already_on_target_agent_returns_true_without_switching(self):
        """If already on the target agent, returns True and skips finalize."""
        do_switch = self._import()

        current = _make_mock_agent("puppy")

        with (
            patch.object(_agents_mod, "get_current_agent", return_value=current),
            patch.object(_config_mod, "finalize_autosave_session") as mock_finalize,
            patch.object(_messaging_mod, "emit_info"),
        ):
            result = do_switch("puppy")

        assert result is True
        mock_finalize.assert_not_called()

    def test_valid_switch_calls_finalize_set_agent_reload(self):
        """With a valid agent name: calls finalize, set_current_agent, reload."""
        do_switch = self._import()

        current = _make_mock_agent("puppy")
        new_ag = _make_mock_agent("wiggum", "Wiggum", "Detective")

        with (
            patch.object(
                _agents_mod, "get_current_agent", side_effect=[current, new_ag]
            ),
            patch.object(
                _agents_mod, "set_current_agent", return_value=True
            ) as mock_set,
            patch.object(
                _config_mod,
                "finalize_autosave_session",
                return_value="rotated-id",
            ) as mock_finalize,
            patch.object(_config_mod, "get_last_terminal_session", return_value=None),
            patch.object(_messaging_mod, "emit_info"),
            patch.object(_messaging_mod, "emit_success"),
        ):
            result = do_switch("wiggum")

        assert result is True
        mock_finalize.assert_called_once()
        mock_set.assert_called_once_with("wiggum")
        new_ag.reload_code_generation_agent.assert_called_once()

    def test_with_last_session_loads_history_and_calls_set_autosave(self):
        """When a last terminal session exists, loads history and updates autosave name."""
        do_switch = self._import()

        current = _make_mock_agent("puppy")
        new_ag = _make_mock_agent("wiggum", "Wiggum", "Detective")
        fake_history = [MagicMock(), MagicMock()]

        with (
            patch.object(
                _agents_mod, "get_current_agent", side_effect=[current, new_ag]
            ),
            patch.object(_agents_mod, "set_current_agent", return_value=True),
            patch.object(
                _config_mod, "finalize_autosave_session", return_value="new-session"
            ),
            patch.object(
                _config_mod,
                "get_last_terminal_session",
                return_value="last-session-from-terminal",
            ),
            patch.object(
                _session_storage_mod, "load_session", return_value=fake_history
            ) as mock_load,
            patch.object(
                _config_mod, "set_current_autosave_from_session_name"
            ) as mock_set_name,
            patch.object(_config_mod, "AUTOSAVE_DIR", "/tmp/autosaves"),
            patch.object(_messaging_mod, "emit_info"),
            patch.object(_messaging_mod, "emit_success"),
            # display_resumed_history is imported inside a try/except — patch at source
            patch.object(_autosave_menu_mod, "display_resumed_history", MagicMock()),
        ):
            result = do_switch("wiggum")

        assert result is True
        mock_load.assert_called_once()
        mock_set_name.assert_called_once_with("last-session-from-terminal")
        new_ag.set_message_history.assert_called_once_with(fake_history)

    def test_no_last_terminal_session_switches_cleanly(self):
        """When get_last_terminal_session returns None, switches without crashing."""
        do_switch = self._import()

        current = _make_mock_agent("puppy")
        new_ag = _make_mock_agent("wiggum", "Wiggum", "Detective")

        with (
            patch.object(
                _agents_mod, "get_current_agent", side_effect=[current, new_ag]
            ),
            patch.object(_agents_mod, "set_current_agent", return_value=True),
            patch.object(
                _config_mod, "finalize_autosave_session", return_value="new-session"
            ),
            patch.object(_config_mod, "get_last_terminal_session", return_value=None),
            patch.object(_messaging_mod, "emit_info"),
            patch.object(_messaging_mod, "emit_success"),
        ):
            result = do_switch("wiggum")

        assert result is True
        new_ag.set_message_history.assert_not_called()

    def test_missing_session_file_falls_back_cleanly(self):
        """FileNotFoundError from load_session falls back to clean switch."""
        do_switch = self._import()

        current = _make_mock_agent("puppy")
        new_ag = _make_mock_agent("wiggum", "Wiggum", "Detective")

        with (
            patch.object(
                _agents_mod, "get_current_agent", side_effect=[current, new_ag]
            ),
            patch.object(_agents_mod, "set_current_agent", return_value=True),
            patch.object(
                _config_mod, "finalize_autosave_session", return_value="new-session"
            ),
            patch.object(
                _config_mod,
                "get_last_terminal_session",
                return_value="ghost-session",
            ),
            patch.object(
                _session_storage_mod,
                "load_session",
                side_effect=FileNotFoundError("session file gone"),
            ),
            patch.object(_config_mod, "AUTOSAVE_DIR", "/tmp/autosaves"),
            patch.object(_messaging_mod, "emit_info"),
            patch.object(_messaging_mod, "emit_success") as mock_success,
        ):
            result = do_switch("wiggum")

        assert result is True
        # Should still emit a success message for the clean fallback switch
        mock_success.assert_called()

    def test_tampered_last_session_marker_does_not_load_pickle(self):
        """A tampered traversal marker is ignored before load_session can unpickle."""
        do_switch = self._import()

        current = _make_mock_agent("puppy")
        new_ag = _make_mock_agent("wiggum", "Wiggum", "Detective")

        with (
            patch.object(
                _agents_mod, "get_current_agent", side_effect=[current, new_ag]
            ),
            patch.object(_agents_mod, "set_current_agent", return_value=True),
            patch.object(
                _config_mod, "finalize_autosave_session", return_value="new-session"
            ),
            patch.object(
                _config_mod,
                "get_last_terminal_session",
                return_value="../../payload",
            ),
            patch.object(_session_storage_mod, "load_session") as mock_load,
            patch.object(_config_mod, "AUTOSAVE_DIR", "/tmp/autosaves"),
            patch.object(_messaging_mod, "emit_info"),
            patch.object(_messaging_mod, "emit_success"),
        ):
            result = do_switch("wiggum")

        assert result is True
        mock_load.assert_not_called()

    def test_empty_fresh_session_resumes_marker_captured_before_finalize(self):
        """Existing terminal marker survives finalize when current history is empty."""
        do_switch = self._import()

        current = _make_mock_agent("puppy")
        current.get_message_history.return_value = []
        new_ag = _make_mock_agent("wiggum", "Wiggum", "Detective")
        fake_history = [MagicMock()]

        with (
            patch.object(
                _agents_mod, "get_current_agent", side_effect=[current, new_ag]
            ),
            patch.object(_agents_mod, "set_current_agent", return_value=True),
            patch.object(
                _config_mod,
                "get_last_terminal_session",
                return_value="auto_session_20260101_010101",
            ) as mock_get_last,
            patch.object(
                _config_mod,
                "finalize_autosave_session",
                return_value="auto_session_20260101_020202",
            ),
            patch.object(
                _session_storage_mod, "load_session", return_value=fake_history
            ) as mock_load,
            patch.object(
                _config_mod, "set_current_autosave_from_session_name"
            ) as mock_set_name,
            patch.object(_config_mod, "record_terminal_session") as mock_record,
            patch.object(_config_mod, "AUTOSAVE_DIR", "/tmp/autosaves"),
            patch.object(_messaging_mod, "emit_info"),
            patch.object(_messaging_mod, "emit_success"),
        ):
            result = do_switch("wiggum")

        assert result is True
        mock_get_last.assert_called_once()
        mock_load.assert_called_once_with(
            "auto_session_20260101_010101", Path("/tmp/autosaves").resolve()
        )
        mock_set_name.assert_called_once_with("auto_session_20260101_010101")
        mock_record.assert_called_once_with("auto_session_20260101_010101")
        new_ag.set_message_history.assert_called_once_with(fake_history)

    def test_set_current_agent_failure_emits_warning(self):
        """When set_current_agent returns False, emits a warning and returns True."""
        do_switch = self._import()

        current = _make_mock_agent("puppy")
        current.get_message_history.return_value = []  # No history to save

        with (
            patch.object(_agents_mod, "get_current_agent", return_value=current),
            patch.object(_agents_mod, "set_current_agent", return_value=False),
            patch.object(
                _config_mod, "finalize_autosave_session", return_value="new-session"
            ),
            patch.object(_messaging_mod, "emit_warning") as mock_warn,
            patch.object(_messaging_mod, "emit_info"),
        ):
            result = do_switch("wiggum")

        assert result is True
        mock_warn.assert_called_once()


# ---------------------------------------------------------------------------
# custom_command_help callback
# ---------------------------------------------------------------------------


class TestCustomCommandHelp:
    """Tests for the custom_command_help callback (_handle_help)."""

    def test_returns_list_with_switch_agent_entry(self):
        """Help callback returns a list with 'switch-agent' as the first element."""
        from code_puppy.plugins.switch_agent_resume.register_callbacks import (
            _handle_help,
        )

        result = _handle_help()
        assert isinstance(result, list)
        assert len(result) >= 1
        names = [item[0] for item in result]
        assert "switch-agent" in names

    def test_help_entry_is_tuple_of_two_strings(self):
        """Each help entry is a (str, str) tuple."""
        from code_puppy.plugins.switch_agent_resume.register_callbacks import (
            _handle_help,
        )

        result = _handle_help()
        for entry in result:
            assert isinstance(entry, tuple)
            assert len(entry) == 2
            assert isinstance(entry[0], str)
            assert isinstance(entry[1], str)

    def test_help_description_mentions_switch_and_resume(self):
        """The description for switch-agent mentions switching, resuming, or agent."""
        from code_puppy.plugins.switch_agent_resume.register_callbacks import (
            _handle_help,
        )

        result = _handle_help()
        switch_agent_entry = next(e for e in result if e[0] == "switch-agent")
        desc_lower = switch_agent_entry[1].lower()
        assert "switch" in desc_lower or "resume" in desc_lower or "agent" in desc_lower


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------


class TestCallbackRegistration:
    """Verify that callbacks are registered at module import time."""

    @pytest.fixture(autouse=True)
    def _ensure_switch_agent_callbacks(self):
        """Re-register callbacks that may have been cleared by clear_callbacks()."""
        from code_puppy.callbacks import get_callbacks, register_callback
        from code_puppy.plugins.switch_agent_resume.register_callbacks import (
            _cleanup_orphaned_tty_sessions_async,
            _handle_help,
            _handle_switch_agent_callback,
        )

        if not any(
            cb is _handle_switch_agent_callback
            or getattr(cb, "__wrapped__", None) is _handle_switch_agent_callback
            for cb in get_callbacks("custom_command")
        ):
            register_callback("custom_command", _handle_switch_agent_callback)
        if not any(
            cb is _handle_help or getattr(cb, "__wrapped__", None) is _handle_help
            for cb in get_callbacks("custom_command_help")
        ):
            register_callback("custom_command_help", _handle_help)
        if not any(
            cb is _cleanup_orphaned_tty_sessions_async
            or getattr(cb, "__wrapped__", None) is _cleanup_orphaned_tty_sessions_async
            for cb in get_callbacks("startup")
        ):
            register_callback("startup", _cleanup_orphaned_tty_sessions_async)

    def test_custom_command_callback_registered(self):
        """_handle_switch_agent is registered for the 'custom_command' hook."""
        from code_puppy.callbacks import get_callbacks
        from code_puppy.plugins.switch_agent_resume.register_callbacks import (
            _handle_switch_agent_callback,
        )

        callbacks = get_callbacks("custom_command")
        assert any(
            cb is _handle_switch_agent_callback
            or getattr(cb, "__wrapped__", None) is _handle_switch_agent_callback
            for cb in callbacks
        )

    def test_custom_command_help_callback_registered(self):
        """_handle_help is registered for the 'custom_command_help' hook."""
        from code_puppy.callbacks import get_callbacks
        from code_puppy.plugins.switch_agent_resume.register_callbacks import (
            _handle_help,
        )

        callbacks = get_callbacks("custom_command_help")
        assert any(
            cb is _handle_help or getattr(cb, "__wrapped__", None) is _handle_help
            for cb in callbacks
        )


# ---------------------------------------------------------------------------
# Cleanup orphaned TTY sessions
# ---------------------------------------------------------------------------


class TestCleanupOrphanedTtySessions:
    """Tests for _cleanup_orphaned_tty_sessions in the switch_agent_resume plugin."""

    @pytest.fixture(autouse=True)
    def _ensure_cleanup_callback(self):
        """Re-register the startup cleanup callback if cleared by another test."""
        from code_puppy.callbacks import get_callbacks, register_callback
        from code_puppy.plugins.switch_agent_resume.register_callbacks import (
            _cleanup_orphaned_tty_sessions_async,
        )

        if not any(
            cb is _cleanup_orphaned_tty_sessions_async
            or getattr(cb, "__wrapped__", None) is _cleanup_orphaned_tty_sessions_async
            for cb in get_callbacks("startup")
        ):
            register_callback("startup", _cleanup_orphaned_tty_sessions_async)

    def _import(self):
        from code_puppy.plugins.switch_agent_resume.register_callbacks import (
            _cleanup_orphaned_tty_sessions,
        )

        return _cleanup_orphaned_tty_sessions

    def test_startup_callback_registered(self):
        """Verify the async cleanup wrapper is registered for the 'startup' hook."""
        from code_puppy.callbacks import get_callbacks
        from code_puppy.plugins.switch_agent_resume.register_callbacks import (
            _cleanup_orphaned_tty_sessions_async,
        )

        callbacks = get_callbacks("startup")
        assert any(
            cb is _cleanup_orphaned_tty_sessions_async
            or getattr(cb, "__wrapped__", None) is _cleanup_orphaned_tty_sessions_async
            for cb in callbacks
        )

    async def test_async_wrapper_is_nonblocking(self):
        """Verify the async wrapper returns immediately and runs cleanup in background."""
        from unittest.mock import patch

        from code_puppy.plugins.switch_agent_resume.register_callbacks import (
            _cleanup_orphaned_tty_sessions_async,
        )

        # Mock asyncio.create_task to verify background execution
        # The mock should return a fake task to prevent "coroutine never awaited" warning
        mock_task = AsyncMock()

        with patch("asyncio.create_task", return_value=mock_task) as mock_create_task:
            # Call the async wrapper
            result = await _cleanup_orphaned_tty_sessions_async()

            # Verify it returned immediately (didn't block)
            assert result is None

            # Verify create_task was called to run cleanup in background
            assert mock_create_task.call_count == 1

            # Verify the task is created with asyncio.to_thread wrapping the sync function
            call_args = mock_create_task.call_args
            assert call_args is not None
            # The first argument should be a coroutine from asyncio.to_thread
            # We can't easily verify the exact function, but we can verify create_task was called

    def test_skips_current_terminal_file(self, tmp_path):
        """Cleanup preserves the current terminal's session file."""
        cleanup = self._import()

        tty_sessions_dir = tmp_path / "tty_sessions"
        tty_sessions_dir.mkdir()

        # Create current terminal's file
        current_file = tty_sessions_dir / "dev_ttys001.txt"
        current_file.write_text("current-session")

        # Create another terminal's file whose TTY path is guaranteed not to
        # exist on any real system (decodes to /xfake/orphaned/test/device).
        other_file = tty_sessions_dir / "xfake_orphaned_test_device.txt"
        other_file.write_text("other-session")

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            cleanup()

        # Current terminal's file should still exist
        assert current_file.exists()
        assert current_file.read_text() == "current-session"

        # Other terminal's file should be deleted (its fake path doesn't exist)
        assert not other_file.exists()

    def test_deletes_file_for_nonexistent_tty(self, tmp_path):
        """Deletes files where the TTY device no longer exists."""
        cleanup = self._import()

        tty_sessions_dir = tmp_path / "tty_sessions"
        tty_sessions_dir.mkdir()

        # Use a filename that decodes to a path guaranteed not to exist on
        # any real system (/xfake/orphaned/session), so no mocking is needed.
        orphaned_file = tty_sessions_dir / "xfake_orphaned_session.txt"
        orphaned_file.write_text("orphaned-session")

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            cleanup()

        assert not orphaned_file.exists()

    def test_deletes_file_older_than_7_days(self, tmp_path):
        """Deletes files with mtime > 7 days old."""
        import os
        import time

        cleanup = self._import()

        tty_sessions_dir = tmp_path / "tty_sessions"
        tty_sessions_dir.mkdir()

        # Create old session file
        old_file = tty_sessions_dir / "dev_ttys099.txt"
        old_file.write_text("old-session")

        # Set mtime to 8 days ago
        eight_days_ago = time.time() - (8 * 24 * 60 * 60)
        os.utime(old_file, (eight_days_ago, eight_days_ago))

        def mock_exists(path):
            # TTY device exists (so age is the only criterion)
            return True

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
            patch.object(os.path, "exists", side_effect=mock_exists),
        ):
            cleanup()

        assert not old_file.exists()

    def test_keeps_file_newer_than_7_days(self, tmp_path):
        """Preserves files newer than 7 days with existing TTY."""
        import os

        cleanup = self._import()

        tty_sessions_dir = tmp_path / "tty_sessions"
        tty_sessions_dir.mkdir()

        # Create recent session file (just created, mtime is current)
        recent_file = tty_sessions_dir / "dev_ttys099.txt"
        recent_file.write_text("recent-session")

        def mock_exists(path):
            # TTY device exists and file is recent
            return True

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
            patch.object(os.path, "exists", side_effect=mock_exists),
        ):
            cleanup()

        # File should still exist (TTY exists and file is < 7 days old)
        assert recent_file.exists()

    def test_noop_when_no_tty_available(self, tmp_path):
        """Does nothing when get_terminal_tty returns None."""
        cleanup = self._import()

        tty_sessions_dir = tmp_path / "tty_sessions"
        tty_sessions_dir.mkdir()

        # Create some session files
        (tty_sessions_dir / "dev_ttys001.txt").write_text("session-1")
        (tty_sessions_dir / "dev_ttys002.txt").write_text("session-2")

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value=None),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            cleanup()

        # All files should still exist
        assert (tty_sessions_dir / "dev_ttys001.txt").exists()
        assert (tty_sessions_dir / "dev_ttys002.txt").exists()

    def test_noop_when_tty_sessions_dir_missing(self, tmp_path):
        """Does nothing when the tty_sessions directory doesn't exist."""
        cleanup = self._import()

        # Don't create the tty_sessions directory

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            cleanup()  # Should not crash

        # Just verify it didn't crash
        assert True

    def test_handles_errors_gracefully(self, tmp_path):
        """Never crashes even if file deletion raises an exception."""
        import os
        import pathlib

        cleanup = self._import()

        tty_sessions_dir = tmp_path / "tty_sessions"
        tty_sessions_dir.mkdir()

        # Create session files
        file1 = tty_sessions_dir / "dev_ttys099.txt"
        file1.write_text("session-1")
        file2 = tty_sessions_dir / "dev_ttys098.txt"
        file2.write_text("session-2")

        unlink_call_count = [0]

        def mock_unlink(self):
            unlink_call_count[0] += 1
            if unlink_call_count[0] == 1:
                # First call raises exception
                raise PermissionError("Simulated error")
            # Second call succeeds (use original implementation)

        def mock_exists(path):
            # TTY devices don't exist
            return False

        original_unlink = pathlib.Path.unlink

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
            patch.object(os.path, "exists", side_effect=mock_exists),
            patch.object(pathlib.Path, "unlink", mock_unlink),
        ):
            cleanup()  # Should not crash

        # Restore original
        pathlib.Path.unlink = original_unlink

        # Just verify it didn't crash
        assert True

    def test_processes_multiple_files(self, tmp_path):
        """Correctly processes multiple session files."""
        import os
        import time

        cleanup = self._import()

        tty_sessions_dir = tmp_path / "tty_sessions"
        tty_sessions_dir.mkdir()

        # Current terminal's file (should be preserved — skipped by name match)
        current_file = tty_sessions_dir / "dev_ttys001.txt"
        current_file.write_text("current-session")

        # File whose decoded path (/xfake/orphaned) is guaranteed not to exist
        # on any real system — deleted by the TTY-existence check, no mock needed.
        orphaned_file = tty_sessions_dir / "xfake_orphaned.txt"
        orphaned_file.write_text("orphaned-session")

        # File whose decoded path (/dev/null) exists, but mtime is 8 days old
        # — deleted by the age check.
        old_file = tty_sessions_dir / "dev_null.txt"
        old_file.write_text("old-session")
        eight_days_ago = time.time() - (8 * 24 * 60 * 60)
        os.utime(old_file, (eight_days_ago, eight_days_ago))

        # File whose decoded path (/tmp) exists and mtime is recent — preserved.
        recent_file = tty_sessions_dir / "tmp.txt"
        recent_file.write_text("recent-session")

        with (
            patch.object(_config_mod, "get_terminal_tty", return_value="/dev/ttys001"),
            patch.object(_config_mod, "CACHE_DIR", str(tmp_path)),
        ):
            cleanup()

        # Current terminal's file preserved
        assert current_file.exists()

        # Orphaned file deleted (decoded TTY path doesn't exist)
        assert not orphaned_file.exists()

        # Old file deleted (> 7 days)
        assert not old_file.exists()

        # Recent file with existing TTY (/tmp) preserved
        assert recent_file.exists()
