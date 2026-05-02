"""Tests for session_commands.py to achieve 100% coverage."""

from unittest.mock import MagicMock, patch


class TestGetCommandsHelp:
    def test_lazy_import(self):
        from code_puppy.command_line.session_commands import get_commands_help

        with patch(
            "code_puppy.command_line.command_handler.get_commands_help",
            return_value="help text",
        ):
            result = get_commands_help()
            assert result == "help text"


class TestHandleSessionCommand:
    def _run(self, command):
        from code_puppy.command_line.session_commands import handle_session_command

        return handle_session_command(command)

    def test_session_show_id(self):
        with (
            patch("code_puppy.config.get_current_autosave_id", return_value="abc123"),
            patch(
                "code_puppy.config.get_current_autosave_session_name",
                return_value="session_abc123",
            ),
            patch("code_puppy.messaging.emit_info") as mock_info,
        ):
            result = self._run("/session")
            assert result is True
            mock_info.assert_called_once()

    def test_session_id_subcommand(self):
        with (
            patch("code_puppy.config.get_current_autosave_id", return_value="xyz"),
            patch(
                "code_puppy.config.get_current_autosave_session_name",
                return_value="s",
            ),
            patch("code_puppy.messaging.emit_info"),
        ):
            assert self._run("/session id") is True

    def test_session_new(self):
        with (
            patch("code_puppy.config.rotate_autosave_id", return_value="new123"),
            patch("code_puppy.messaging.emit_success") as mock_s,
        ):
            assert self._run("/session new") is True
            assert "new123" in mock_s.call_args[0][0]

    def test_session_invalid(self):
        with patch("code_puppy.messaging.emit_warning") as mock_w:
            assert self._run("/session bad") is True
            mock_w.assert_called_once()


class TestHandleCompactCommand:
    def _run(self, cmd="/compact"):
        from code_puppy.command_line.session_commands import handle_compact_command

        return handle_compact_command(cmd)

    def test_no_history(self):
        agent = MagicMock()
        agent.get_message_history.return_value = []
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch("code_puppy.messaging.emit_warning") as mw,
        ):
            assert self._run() is True
            mw.assert_called_once()

    def test_truncation_strategy(self):
        agent = MagicMock()
        agent.get_message_history.return_value = ["m1", "m2", "m3"]
        agent.estimate_tokens_for_message.return_value = 100
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch(
                "code_puppy.config.get_compaction_strategy",
                return_value="truncation",
            ),
            patch("code_puppy.agents._compaction.compact", return_value=(["m3"], [])),
            patch("code_puppy.messaging.emit_info"),
            patch("code_puppy.messaging.emit_success") as ms,
        ):
            assert self._run() is True
            ms.assert_called_once()
            assert "truncation" in ms.call_args[0][0]

    def test_summarization_strategy(self):
        agent = MagicMock()
        agent.get_message_history.return_value = ["m1", "m2"]
        agent.estimate_tokens_for_message.return_value = 100
        agent.summarize_messages.return_value = (["summary"], ["m1"])
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch(
                "code_puppy.config.get_compaction_strategy",
                return_value="summarization",
            ),
            patch(
                "code_puppy.agents._compaction.compact",
                return_value=(["summary"], ["m1"]),
            ) as mock_compact,
            patch("code_puppy.messaging.emit_info"),
            patch("code_puppy.messaging.emit_success") as ms,
        ):
            assert self._run() is True
            ms.assert_called_once()
            mock_compact.assert_called_once_with(
                agent,
                ["m1", "m2"],
                agent._get_model_context_length(),
                agent._estimate_context_overhead(),
                force=True,
            )

    def test_compaction_fails(self):
        agent = MagicMock()
        agent.get_message_history.return_value = ["m1"]
        agent.estimate_tokens_for_message.return_value = 100
        agent.summarize_messages.return_value = ([], [])
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch(
                "code_puppy.config.get_compaction_strategy",
                return_value="summarization",
            ),
            patch("code_puppy.agents._compaction.compact", return_value=([], [])),
            patch("code_puppy.messaging.emit_info"),
            patch("code_puppy.messaging.emit_error") as me,
        ):
            assert self._run() is True
            me.assert_called_once()

    def test_exception(self):
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                side_effect=Exception("boom"),
            ),
            patch("code_puppy.messaging.emit_error") as me,
        ):
            assert self._run() is True
            assert "boom" in me.call_args[0][0]

    def test_zero_before_tokens(self):
        """Cover the before_tokens == 0 branch for reduction_pct."""
        agent = MagicMock()
        agent.get_message_history.return_value = ["m1"]
        agent.estimate_tokens_for_message.return_value = 0
        agent.summarize_messages.return_value = (["s"], [])
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch(
                "code_puppy.config.get_compaction_strategy",
                return_value="summarization",
            ),
            patch("code_puppy.agents._compaction.compact", return_value=(["s"], [])),
            patch("code_puppy.messaging.emit_info"),
            patch("code_puppy.messaging.emit_success"),
        ):
            assert self._run() is True


class TestHandleContinuityCommand:
    def _run(self, cmd="/continuity"):
        from code_puppy.plugins.continuity_compaction.register_callbacks import (
            _handle_continuity_command,
        )

        return _handle_continuity_command(cmd)

    def _agent_with_memory(self, tmp_path, monkeypatch):
        import code_puppy.config as cp_config
        from code_puppy.plugins.continuity_compaction.archives import (
            archive_observation,
        )
        from code_puppy.plugins.continuity_compaction.storage import (
            DurableState,
            TaskMemory,
            write_durable_state,
        )

        monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
        agent = MagicMock()
        agent.session_id = "continuity-command-session"
        state = DurableState(
            goal="Build command surface ROOT-CMD",
            current_task="Build command surface ROOT-CMD",
            latest_user_request="Show continuity ROOT-LATEST",
            global_constraints=["global constraint"],
            tasks=[
                TaskMemory(
                    task_id="task-cmd",
                    title="Build command surface ROOT-CMD",
                    status="active",
                    constraints=["task constraint"],
                    active_files=["src/cmd.py"],
                )
            ],
            current_task_id="task-cmd",
            original_root_task_id="task-cmd",
            semantic_status="semantic",
            active_files=["src/cmd.py"],
        )
        write_durable_state(agent, state)
        record = archive_observation(
            agent=agent,
            tool_name="run_shell_command",
            tool_call_id="call-cmd",
            content="AssertionError ROOT-CMD-SIGNAL in src/cmd.py",
            token_count=100,
            key_signal="AssertionError ROOT-CMD-SIGNAL in src/cmd.py",
            key_signals=["AssertionError ROOT-CMD-SIGNAL in src/cmd.py"],
            affected_files=["src/cmd.py"],
            status="failed",
        )
        return agent, record

    def test_continuity_show_and_tasks(self, tmp_path, monkeypatch):
        agent, _record = self._agent_with_memory(tmp_path, monkeypatch)
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch("code_puppy.messaging.emit_info") as mock_info,
        ):
            assert self._run("/continuity show") is True
            assert "ROOT-CMD" in mock_info.call_args[0][0]
            assert self._run("/continuity tasks") is True
            assert "task-cmd" in mock_info.call_args[0][0]

    def test_continuity_archives_search_show_and_diagnostics(
        self, tmp_path, monkeypatch
    ):
        agent, record = self._agent_with_memory(tmp_path, monkeypatch)
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch("code_puppy.messaging.emit_info") as mock_info,
        ):
            assert self._run("/continuity archives search ROOT-CMD-SIGNAL") is True
            assert record["observation_id"] in mock_info.call_args[0][0]
            assert (
                self._run(f"/continuity archives show {record['observation_id']}")
                is True
            )
            assert "checksum:" in mock_info.call_args[0][0]
            assert self._run("/continuity diagnostics") is True
            assert "semantic_timeout_seconds" in mock_info.call_args[0][0]

    def test_continuity_no_memory(self, tmp_path, monkeypatch):
        import code_puppy.config as cp_config

        monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path))
        agent = MagicMock()
        agent.session_id = "empty-continuity-session"
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch("code_puppy.messaging.emit_warning") as mock_warning,
        ):
            assert self._run("/continuity") is True
            mock_warning.assert_called_once()


class TestHandleTruncateCommand:
    def _run(self, cmd):
        from code_puppy.command_line.session_commands import handle_truncate_command

        return handle_truncate_command(cmd)

    def test_missing_arg(self):
        with patch("code_puppy.messaging.emit_error"):
            assert self._run("/truncate") is True

    def test_invalid_n(self):
        with patch("code_puppy.messaging.emit_error"):
            assert self._run("/truncate abc") is True

    def test_negative_n(self):
        with patch("code_puppy.messaging.emit_error"):
            assert self._run("/truncate -1") is True

    def test_no_history(self):
        agent = MagicMock()
        agent.get_message_history.return_value = []
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch("code_puppy.messaging.emit_warning"),
        ):
            assert self._run("/truncate 5") is True

    def test_already_small(self):
        agent = MagicMock()
        agent.get_message_history.return_value = ["a", "b"]
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch("code_puppy.messaging.emit_info"),
        ):
            assert self._run("/truncate 5") is True

    def test_success(self):
        agent = MagicMock()
        agent.get_message_history.return_value = ["sys", "a", "b", "c", "d"]
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch("code_puppy.messaging.emit_success"),
        ):
            assert self._run("/truncate 3") is True
            hist = agent.set_message_history.call_args[0][0]
            assert len(hist) == 3
            assert hist[0] == "sys"

    def test_n_equals_1(self):
        agent = MagicMock()
        agent.get_message_history.return_value = ["sys", "a", "b"]
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch("code_puppy.messaging.emit_success"),
        ):
            assert self._run("/truncate 1") is True
            assert agent.set_message_history.call_args[0][0] == ["sys"]

    def test_too_many_args(self):
        with patch("code_puppy.messaging.emit_error"):
            assert self._run("/truncate 1 2") is True


class TestHandleAutosaveLoadCommand:
    def test_returns_marker(self):
        from code_puppy.command_line.session_commands import (
            handle_autosave_load_command,
        )

        assert handle_autosave_load_command("/autosave_load") == "__AUTOSAVE_LOAD__"


class TestHandleDumpContextCommand:
    def _run(self, cmd):
        from code_puppy.command_line.session_commands import (
            handle_dump_context_command,
        )

        return handle_dump_context_command(cmd)

    def test_missing_name(self):
        with patch("code_puppy.messaging.emit_warning"):
            assert self._run("/dump_context") is True

    def test_no_history(self):
        agent = MagicMock()
        agent.get_message_history.return_value = []
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch("code_puppy.messaging.emit_warning"),
        ):
            assert self._run("/dump_context mysession") is True

    def test_success(self):
        agent = MagicMock()
        agent.get_message_history.return_value = ["m1", "m2"]
        meta = MagicMock(
            message_count=2,
            total_tokens=200,
            pickle_path="a.pkl",
            metadata_path="a.json",
        )
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch(
                "code_puppy.command_line.session_commands.save_session",
                return_value=meta,
            ),
            patch("code_puppy.messaging.emit_success"),
        ):
            assert self._run("/dump_context mysession") is True

    def test_exception(self):
        agent = MagicMock()
        agent.get_message_history.return_value = ["m1"]
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch(
                "code_puppy.command_line.session_commands.save_session",
                side_effect=Exception("disk full"),
            ),
            patch("code_puppy.messaging.emit_error") as me,
        ):
            assert self._run("/dump_context mysession") is True
            assert "disk full" in me.call_args[0][0]


class TestHandleLoadContextCommand:
    def _run(self, cmd):
        from code_puppy.command_line.session_commands import (
            handle_load_context_command,
        )

        return handle_load_context_command(cmd)

    def test_missing_name(self):
        with patch("code_puppy.messaging.emit_warning"):
            assert self._run("/load_context") is True

    def test_file_not_found_with_available(self):
        with (
            patch(
                "code_puppy.command_line.session_commands.load_session",
                side_effect=FileNotFoundError(),
            ),
            patch(
                "code_puppy.command_line.session_commands.list_sessions",
                return_value=["s1"],
            ),
            patch("code_puppy.messaging.emit_error"),
            patch("code_puppy.messaging.emit_info") as mi,
        ):
            assert self._run("/load_context missing") is True
            mi.assert_called_once()

    def test_file_not_found_no_available(self):
        with (
            patch(
                "code_puppy.command_line.session_commands.load_session",
                side_effect=FileNotFoundError(),
            ),
            patch(
                "code_puppy.command_line.session_commands.list_sessions",
                return_value=[],
            ),
            patch("code_puppy.messaging.emit_error"),
            patch("code_puppy.messaging.emit_info") as mi,
        ):
            assert self._run("/load_context missing") is True
            mi.assert_not_called()

    def test_generic_exception(self):
        with (
            patch(
                "code_puppy.command_line.session_commands.load_session",
                side_effect=Exception("corrupt"),
            ),
            patch("code_puppy.messaging.emit_error") as me,
        ):
            assert self._run("/load_context bad") is True
            assert "corrupt" in me.call_args[0][0]

    def test_success(self):
        agent = MagicMock()
        agent.estimate_tokens_for_message.return_value = 50
        with (
            patch(
                "code_puppy.command_line.session_commands.load_session",
                return_value=["m1", "m2"],
            ),
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch("code_puppy.config.rotate_autosave_id", return_value="new_id"),
            patch("code_puppy.messaging.emit_success"),
            patch("code_puppy.command_line.autosave_menu.display_resumed_history"),
        ):
            assert self._run("/load_context mysession") is True

    def test_success_rotate_fails(self):
        agent = MagicMock()
        agent.estimate_tokens_for_message.return_value = 50
        with (
            patch(
                "code_puppy.command_line.session_commands.load_session",
                return_value=["m1"],
            ),
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch(
                "code_puppy.config.rotate_autosave_id",
                side_effect=Exception("fail"),
            ),
            patch("code_puppy.messaging.emit_success"),
            patch("code_puppy.command_line.autosave_menu.display_resumed_history"),
        ):
            assert self._run("/load_context mysession") is True
