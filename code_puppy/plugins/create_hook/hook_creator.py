"""
Interactive hook creator wizard for Code Puppy.

Guides users through creating hooks step-by-step.
"""

from typing import Optional, List, Tuple
from code_puppy.messaging import emit_info, emit_success, emit_error, emit_warning
from .hook_knowledge_base import (
    get_hooks_by_category,
    get_hook_by_name,
    HookEvent,
)


class HookCreatorWizard:
    """Interactive wizard for creating Code Puppy hooks."""
    
    def __init__(self):
        self.hook_type: Optional[str] = None  # "lifecycle" or "event"
        self.hook_event: Optional[HookEvent] = None
        self.matcher: Optional[str] = None
        self.command: Optional[str] = None
        self.timeout: int = 5000
        self.language: str = "bash"
    
    def start(self) -> bool:
        """Start the interactive wizard. Returns True if user completed it."""
        emit_info("🎣 Code Puppy Hook Creator")
        emit_info("")
        emit_info("This wizard helps you create hooks to automate Code Puppy.")
        emit_info("")
        
        # Step 1: Choose hook type
        if not self._choose_hook_type():
            emit_warning("Hook creation cancelled.")
            return False
        
        # Step 2: Choose specific event/phase
        if not self._choose_hook_event():
            emit_warning("Hook creation cancelled.")
            return False
        
        # Step 3: Configure matcher (if applicable)
        if self.hook_event.matcher_support:
            if not self._choose_matcher():
                emit_warning("Hook creation cancelled.")
                return False
        
        # Step 4: Choose implementation details
        if not self._choose_implementation():
            emit_warning("Hook creation cancelled.")
            return False
        
        # Step 5: Show summary and generate
        return self._generate_and_save()
    
    def _choose_hook_type(self) -> bool:
        """Ask user to choose between lifecycle and event-based hooks."""
        emit_info("What type of hook would you like to create?")
        emit_info("")
        emit_info("1. 🔄 Lifecycle Callback")
        emit_info("   Python function that runs at specific Code Puppy phases")
        emit_info("   (startup, shutdown, custom_command, pre_tool_call, etc.)")
        emit_info("")
        emit_info("2. 📡 Event-Based Hook")
        emit_info("   Shell command/script that responds to Code Puppy events")
        emit_info("   (PreToolUse, PostToolUse, SessionStart, Stop, etc.)")
        emit_info("")
        
        # TODO: Replace with actual input mechanism
        # For now, just document the flow
        emit_warning("⚠️  Interactive input not yet implemented in this wizard.")
        emit_info("See /hooks menu for full hook configuration interface.")
        return False
    
    def _choose_hook_event(self) -> bool:
        """Ask user to choose which event/phase."""
        if not self.hook_type:
            return False
        
        hooks = get_hooks_by_category(self.hook_type)
        
        emit_info(f"Available {self.hook_type} hooks:")
        emit_info("")
        
        for i, hook in enumerate(hooks, 1):
            emit_info(f"{i}. {hook.name}")
            emit_info(f"   {hook.description}")
        
        return True
    
    def _choose_matcher(self) -> bool:
        """Ask user to configure matcher pattern."""
        if not self.hook_event or not self.hook_event.matcher_support:
            return True
        
        emit_info(f"Configure matcher for {self.hook_event.name}")
        emit_info("")
        emit_info("Examples:")
        for example in self.hook_event.matcher_examples:
            emit_info(f"  • {example or '(empty - matches all)'}")
        
        return True
    
    def _choose_implementation(self) -> bool:
        """Ask user for implementation details."""
        emit_info("How would you like to implement this?")
        emit_info("")
        
        if self.hook_type == "lifecycle":
            emit_info("1. Python async function (default)")
            emit_info("2. Python sync function")
            return True
        else:
            emit_info("1. Bash script (default)")
            emit_info("2. Python script")
            return True
    
    def _generate_and_save(self) -> bool:
        """Show summary and generate code."""
        emit_success("✓ Hook configuration ready!")
        emit_info("")
        emit_info("📋 Summary:")
        emit_info(f"  Type: {self.hook_type}")
        emit_info(f"  Event: {self.hook_event.name if self.hook_event else 'N/A'}")
        
        if self.hook_event and self.hook_event.matcher_support and self.matcher:
            emit_info(f"  Matcher: {self.matcher}")
        
        emit_info("")
        emit_warning("⚠️  Code generation would go here.")
        emit_info("Use /hooks menu to add and configure hooks.")
        
        return True


def show_hook_wizard():
    """Launch the interactive hook creator."""
    wizard = HookCreatorWizard()
    return wizard.start()
