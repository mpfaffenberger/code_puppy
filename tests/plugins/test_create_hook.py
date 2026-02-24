"""Tests for create_hook plugin."""

import pytest
from code_puppy.plugins.create_hook.hook_knowledge_base import (
    get_hooks_by_category,
    get_hook_by_name,
    list_all_hooks,
    LIFECYCLE_CALLBACKS,
    EVENT_BASED_HOOKS,
)
from code_puppy.plugins.create_hook.hook_templates import (
    generate_lifecycle_callback_plugin,
    generate_event_hook_command,
    generate_hook_config,
)


class TestHookKnowledgeBase:
    """Test hook knowledge base."""
    
    def test_lifecycle_callbacks_exist(self):
        """Verify lifecycle callbacks are defined."""
        assert len(LIFECYCLE_CALLBACKS) > 0
        names = [h.name for h in LIFECYCLE_CALLBACKS]
        assert "startup" in names
        assert "custom_command" in names
        assert "pre_tool_call" in names
    
    def test_event_based_hooks_exist(self):
        """Verify event-based hooks are defined."""
        assert len(EVENT_BASED_HOOKS) > 0
        names = [h.name for h in EVENT_BASED_HOOKS]
        assert "PreToolUse" in names
        assert "PostToolUse" in names
        assert "SessionStart" in names
    
    def test_get_hooks_by_category(self):
        """Test filtering hooks by category."""
        lifecycle = get_hooks_by_category("lifecycle")
        assert all(h.category == "lifecycle" for h in lifecycle)
        assert len(lifecycle) > 0
        
        event = get_hooks_by_category("event")
        assert all(h.category == "event" for h in event)
        assert len(event) > 0
    
    def test_get_hook_by_name(self):
        """Test finding hooks by name."""
        hook = get_hook_by_name("startup")
        assert hook is not None
        assert hook.name == "startup"
        
        hook = get_hook_by_name("PreToolUse")
        assert hook is not None
        assert hook.name == "PreToolUse"
        
        hook = get_hook_by_name("nonexistent")
        assert hook is None
    
    def test_list_all_hooks(self):
        """Test listing all hooks."""
        all_hooks = list_all_hooks()
        assert "lifecycle" in all_hooks
        assert "event" in all_hooks
        assert len(all_hooks["lifecycle"]) > 0
        assert len(all_hooks["event"]) > 0


class TestHookTemplates:
    """Test template generation."""
    
    def test_generate_lifecycle_callback_startup(self):
        """Test generating startup callback."""
        code = generate_lifecycle_callback_plugin(
            hook_phase="startup",
            hook_name="my_feature",
            description="Initialize my feature",
        )
        assert "register_callback" in code
        assert "startup" in code
        assert "async def" in code
    
    def test_generate_lifecycle_callback_custom_command(self):
        """Test generating custom command callback."""
        code = generate_lifecycle_callback_plugin(
            hook_phase="custom_command",
            hook_name="greet",
            description="Emit a greeting",
        )
        assert "custom_command" in code
        assert "/greet" in code or "greet" in code
        assert "def _handle_custom_command" in code
        assert "def _custom_help" in code
    
    def test_generate_event_hook_pretooluse_bash(self):
        """Test generating PreToolUse hook in bash."""
        code = generate_event_hook_command(
            event="PreToolUse",
            matcher="Bash",
            description="Validate bash commands",
            language="bash",
        )
        assert "#!/bin/bash" in code
        assert "jq" in code
        assert "exit 0" in code or "exit 2" in code
    
    def test_generate_event_hook_posttooluse_bash(self):
        """Test generating PostToolUse hook."""
        code = generate_event_hook_command(
            event="PostToolUse",
            matcher="Edit|Write",
            description="Log file edits",
            language="bash",
        )
        assert "#!/bin/bash" in code
        assert "TOOL_NAME" in code
    
    def test_generate_event_hook_sessionstart_bash(self):
        """Test generating SessionStart hook."""
        code = generate_event_hook_command(
            event="SessionStart",
            matcher="compact",
            description="Reinject context after compaction",
            language="bash",
        )
        assert "echo" in code
        assert "SESSION" in code or "SOURCE" in code
    
    def test_generate_hook_config(self):
        """Test generating hook configuration JSON."""
        config = generate_hook_config(
            event="PreToolUse",
            matcher="Bash",
            hook_type="command",
            command_or_prompt="echo 'test'",
            timeout=5000,
        )
        assert "PreToolUse" in config
        assert "Bash" in config
        assert "echo 'test'" in config


class TestCustomCommand:
    """Test custom command handler."""
    
    def test_help_entries(self):
        """Test help menu entries."""
        from code_puppy.plugins.create_hook.register_callbacks import _custom_help
        
        entries = _custom_help()
        assert len(entries) > 0
        names = [name for name, _ in entries]
        assert "create-hook" in names
    
    def test_command_handler_imports(self):
        """Test that command handler can be imported."""
        from code_puppy.plugins.create_hook.register_callbacks import (
            _handle_custom_command,
        )
        assert callable(_handle_custom_command)
