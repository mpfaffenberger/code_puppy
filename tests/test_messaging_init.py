"""Tests for code_puppy.messaging package __init__.py.

This module tests that the messaging package properly exports all its public API.
"""

import code_puppy.messaging as messaging_package


class TestMessagingPackageExports:
    """Test that messaging package exports all expected symbols."""

    def test_all_exports_defined(self):
        """Test that __all__ is defined and is a list."""
        assert hasattr(messaging_package, "__all__")
        assert isinstance(messaging_package.__all__, list)
        assert len(messaging_package.__all__) > 0

    def test_message_queue_core_exports(self):
        """Test that core MessageQueue exports are available."""
        assert "MessageQueue" in messaging_package.__all__
        assert "MessageType" in messaging_package.__all__
        assert "UIMessage" in messaging_package.__all__
        assert "get_global_queue" in messaging_package.__all__

        assert hasattr(messaging_package, "MessageQueue")
        assert hasattr(messaging_package, "MessageType")
        assert hasattr(messaging_package, "UIMessage")
        assert hasattr(messaging_package, "get_global_queue")

    def test_emit_functions_exported(self):
        """Test that all emit_* functions are exported."""
        emit_functions = [
            "emit_message",
            "emit_info",
            "emit_success",
            "emit_warning",
            "emit_divider",
            "emit_error",
            "emit_tool_output",
            "emit_command_output",
            "emit_agent_reasoning",
            "emit_planned_next_steps",
            "emit_agent_response",
            "emit_system_message",
            "emit_prompt",
        ]

        for func_name in emit_functions:
            assert func_name in messaging_package.__all__
            assert hasattr(messaging_package, func_name)

    def test_prompt_functions_exported(self):
        """Test that prompt-related functions are exported."""
        assert "provide_prompt_response" in messaging_package.__all__
        assert "get_buffered_startup_messages" in messaging_package.__all__

        assert hasattr(messaging_package, "provide_prompt_response")
        assert hasattr(messaging_package, "get_buffered_startup_messages")

    def test_renderer_exports(self):
        """Test that all renderer classes are exported."""
        assert "InteractiveRenderer" in messaging_package.__all__
        assert "SynchronousInteractiveRenderer" in messaging_package.__all__

        assert hasattr(messaging_package, "InteractiveRenderer")
        assert hasattr(messaging_package, "SynchronousInteractiveRenderer")

    def test_console_exports(self):
        """Test that QueueConsole exports are available."""
        assert "QueueConsole" in messaging_package.__all__
        assert "get_queue_console" in messaging_package.__all__

        assert hasattr(messaging_package, "QueueConsole")
        assert hasattr(messaging_package, "get_queue_console")

    def test_all_exports_are_accessible(self):
        """Test that all items in __all__ are actually accessible."""
        for export_name in messaging_package.__all__:
            assert hasattr(messaging_package, export_name), (
                f"{export_name} in __all__ but not accessible"
            )

    def test_expected_export_count(self):
        """Test that __all__ has the expected number of exports."""
        # Legacy exports that must be present for backward compatibility
        legacy_exports = {
            "MessageQueue",
            "MessageType",
            "UIMessage",
            "get_global_queue",
            "emit_message",
            "emit_info",
            "emit_success",
            "emit_warning",
            "emit_divider",
            "emit_error",
            "emit_tool_output",
            "emit_command_output",
            "emit_agent_reasoning",
            "emit_planned_next_steps",
            "emit_agent_response",
            "emit_system_message",
            "emit_prompt",
            "provide_prompt_response",
            "get_buffered_startup_messages",
            "InteractiveRenderer",
            "SynchronousInteractiveRenderer",
            "QueueConsole",
            "get_queue_console",
        }

        # New structured messaging API exports
        new_api_exports = {
            # Enums
            "MessageLevel",
            "MessageCategory",
            # Base classes
            "BaseMessage",
            "BaseCommand",
            # Message types
            "TextMessage",
            "FileEntry",
            "FileListingMessage",
            "FileContentMessage",
            "GrepMatch",
            "GrepResultMessage",
            "DiffLine",
            "DiffMessage",
            "ShellOutputMessage",
            "ShellStartMessage",
            "AgentReasoningMessage",
            "AgentResponseMessage",
            "SubAgentInvocationMessage",
            "SubAgentResponseMessage",
            "UserInputRequest",
            "ConfirmationRequest",
            "SelectionRequest",
            "SpinnerControl",
            "DividerMessage",
            "StatusPanelMessage",
            "VersionCheckMessage",
            "AnyMessage",
            # Command types
            "CancelAgentCommand",
            "InterruptShellCommand",
            "UserInputResponse",
            "ConfirmationResponse",
            "SelectionResponse",
            "AnyCommand",
            # Message bus
            "MessageBus",
            "get_message_bus",
            "reset_message_bus",
            # New API convenience functions
            "bus_emit",
            "bus_emit_info",
            "bus_emit_warning",
            "bus_emit_error",
            "bus_emit_success",
            "bus_emit_debug",
            # Renderer
            "RendererProtocol",
            "RichConsoleRenderer",
            "DEFAULT_STYLES",
            "DIFF_STYLES",
            # Markdown patches
            "patch_markdown_headings",
            # Session management
            "set_session_context",
            "get_session_context",
            # Shell output rendering
            "ShellLineMessage",
            "emit_shell_line",
            # Sub-agent console manager
            "SubAgentStatusMessage",
            "AgentState",
            "SubAgentConsoleManager",
            "get_subagent_console_manager",
            "SUBAGENT_STATUS_STYLES",
            # Skill-related message types
            "SkillEntry",
            "SkillListMessage",
            "SkillActivateMessage",
        }

        expected_exports = legacy_exports | new_api_exports

        # Verify all legacy exports are still present (backward compatibility)
        assert legacy_exports.issubset(set(messaging_package.__all__)), (
            "Missing legacy exports for backward compatibility"
        )

        # Verify all expected exports match
        assert set(messaging_package.__all__) == expected_exports

    def test_new_messaging_api_exports(self):
        """Test that new structured messaging API exports are available."""
        # Message types
        assert hasattr(messaging_package, "TextMessage")
        assert hasattr(messaging_package, "MessageLevel")
        assert hasattr(messaging_package, "MessageCategory")
        assert hasattr(messaging_package, "DiffMessage")
        assert hasattr(messaging_package, "ShellOutputMessage")

        # Command types
        assert hasattr(messaging_package, "CancelAgentCommand")
        assert hasattr(messaging_package, "UserInputResponse")

        # Message bus
        assert hasattr(messaging_package, "MessageBus")
        assert hasattr(messaging_package, "get_message_bus")

        # Renderer
        assert hasattr(messaging_package, "RichConsoleRenderer")
        assert hasattr(messaging_package, "RendererProtocol")
