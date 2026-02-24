"""
Code Puppy Hook Creator Plugin

Registers the /create-hook command to guide users through hook creation.
Uses Context7 to provide up-to-date documentation and examples.
"""

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info, emit_success, emit_error
from .hook_creator import show_hook_wizard
from .hook_knowledge_base import list_all_hooks, get_hook_by_name


def _custom_help():
    """Help entries for create-hook commands."""
    return [
        ("create-hook", "Interactive wizard to create Code Puppy hooks"),
    ]


def _handle_custom_command(command: str, name: str):
    """Handle /create-hook command.
    
    Supports:
    - /create-hook                    → Launch interactive wizard
    - /create-hook callback <phase>   → Create lifecycle callback
    - /create-hook event <event>      → Create event-based hook
    """
    if name != "create-hook":
        return None
    
    # Parse subcommand
    parts = command.split(maxsplit=2)
    
    if len(parts) == 1:
        # /create-hook with no args → show wizard or menu
        return _show_create_hook_menu()
    
    subcommand = parts[1] if len(parts) > 1 else None
    arg = parts[2] if len(parts) > 2 else None
    
    if subcommand == "callback" and arg:
        return _create_callback_hook(arg)
    elif subcommand == "event" and arg:
        return _create_event_hook(arg)
    elif subcommand == "help":
        return _show_hook_help()
    else:
        emit_error("Unknown subcommand. Try: /create-hook help")
        return True


def _show_create_hook_menu() -> bool:
    """Show the main menu for hook creation."""
    emit_info("🎣 Code Puppy Hook Creator")
    emit_info("")
    emit_info("Choose what you'd like to create:")
    emit_info("")
    emit_info("📋 Commands:")
    emit_info("  /create-hook callback <phase>   Create a lifecycle callback")
    emit_info("  /create-hook event <event>      Create an event-based hook")
    emit_info("  /create-hook help               Show available phases and events")
    emit_info("  /create-hook list               List all available hooks")
    emit_info("")
    emit_info("📚 For comprehensive hook management, use /hooks menu")
    
    return True


def _create_callback_hook(phase: str) -> bool:
    """Guide user through creating a lifecycle callback hook."""
    emit_info(f"🔄 Creating lifecycle callback for phase: {phase}")
    
    # Validate phase
    hooks = list_all_hooks()
    lifecycle_hooks = {h.name: h for h in hooks["lifecycle"]}
    
    if phase.lower() not in lifecycle_hooks:
        available = ", ".join(h.name for h in hooks["lifecycle"])
        emit_error(f"Unknown phase '{phase}'. Available: {available}")
        return True
    
    hook = lifecycle_hooks[phase.lower()]
    
    emit_info("")
    emit_info(f"📝 {hook.name}")
    emit_info(f"   {hook.description}")
    emit_info("")
    emit_info("📥 Input fields:")
    for field, description in hook.input_fields.items():
        emit_info(f"   • {field}: {description}")
    emit_info("")
    emit_info("📤 Output options:")
    for output in hook.output_options:
        emit_info(f"   • {output}")
    emit_info("")
    emit_info("💾 Example:")
    emit_info("")
    for line in hook.code_example.split('\n'):
        emit_info(f"   {line}")
    emit_info("")
    
    emit_success("✓ Use this as a template to create your plugin!")
    emit_info("📚 See AGENTS.md for plugin development guidelines")
    
    return True


def _create_event_hook(event: str) -> bool:
    """Guide user through creating an event-based hook."""
    emit_info(f"📡 Creating event-based hook for: {event}")
    
    # Validate event
    hooks = list_all_hooks()
    event_hooks = {h.name: h for h in hooks["event"]}
    
    if event.lower() not in event_hooks:
        available = ", ".join(h.name for h in hooks["event"])
        emit_error(f"Unknown event '{event}'. Available: {available}")
        return True
    
    hook = event_hooks[event.lower()]
    
    emit_info("")
    emit_info(f"📝 {hook.name}")
    emit_info(f"   {hook.description}")
    emit_info("")
    
    if hook.matcher_support:
        emit_info("🎯 Matcher patterns:")
        for example in hook.matcher_examples:
            emit_info(f"   • {example or '(empty - matches all)'}")
        emit_info("")
    
    emit_info("📥 Input fields:")
    for field, description in hook.input_fields.items():
        emit_info(f"   • {field}: {description}")
    emit_info("")
    emit_info("📤 Output options:")
    for output in hook.output_options:
        emit_info(f"   • {output}")
    emit_info("")
    emit_info("💾 Bash script example:")
    emit_info("")
    for line in hook.code_example.split('\n'):
        emit_info(f"   {line}")
    emit_info("")
    
    emit_success("✓ Save this script to .claude/hooks/ and configure in .claude/settings.json")
    
    return True


def _show_hook_help() -> bool:
    """Show help for all available hooks."""
    emit_info("🎣 Available Hooks")
    emit_info("")
    
    hooks = list_all_hooks()
    
    emit_info("🔄 Lifecycle Callbacks:")
    emit_info("   (Python functions registered at startup)")
    for hook in hooks["lifecycle"]:
        emit_info(f"   • {hook.name}: {hook.description}")
    
    emit_info("")
    emit_info("📡 Event-Based Hooks:")
    emit_info("   (Shell scripts responding to Code Puppy events)")
    for hook in hooks["event"]:
        emit_info(f"   • {hook.name}: {hook.description}")
    
    emit_info("")
    emit_info("💡 Examples:")
    emit_info("   /create-hook callback startup")
    emit_info("   /create-hook event PreToolUse")
    emit_info("   /create-hook event PostToolUse")
    
    return True


# Register the custom command
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
