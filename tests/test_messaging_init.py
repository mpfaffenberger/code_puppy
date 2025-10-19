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
        assert "TUIRenderer" in messaging_package.__all__
        assert "SynchronousInteractiveRenderer" in messaging_package.__all__
        
        assert hasattr(messaging_package, "InteractiveRenderer")
        assert hasattr(messaging_package, "TUIRenderer")
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
        # Based on the __all__ list in the module
        expected_exports = {
            "MessageQueue", "MessageType", "UIMessage", "get_global_queue",
            "emit_message", "emit_info", "emit_success", "emit_warning",
            "emit_divider", "emit_error", "emit_tool_output", "emit_command_output",
            "emit_agent_reasoning", "emit_planned_next_steps", "emit_agent_response",
            "emit_system_message", "emit_prompt", "provide_prompt_response",
            "get_buffered_startup_messages", "InteractiveRenderer", "TUIRenderer",
            "SynchronousInteractiveRenderer", "QueueConsole", "get_queue_console",
        }
        
        assert set(messaging_package.__all__) == expected_exports
