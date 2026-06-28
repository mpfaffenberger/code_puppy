"""Main help provider - coordinates all help system features."""

from typing import Dict, Optional

from code_puppy.help_system.help_content import (
    COMMAND_HELP,
    HELP_CATEGORIES,
    TIPS,
)
from code_puppy.help_system.search_engine import format_search_results, search_help


class HelpProvider:
    """Main provider for the help system."""

    def __init__(self):
        self.categories = HELP_CATEGORIES
        self.command_help = COMMAND_HELP
        self.tips = TIPS

    def show_main_help(self) -> str:
        """Display main help screen."""
        from code_puppy.command_line.command_registry import get_unique_commands

        lines = []
        lines.append("Code Puppy Help System")
        lines.append("=" * 40)
        lines.append("")

        # Built-in Commands section for backward compatibility
        lines.append("Built-in Commands")
        registered_commands = get_unique_commands()
        for cmd_info in sorted(registered_commands, key=lambda c: c.name):
            lines.append(f"  {cmd_info.usage:30} {cmd_info.description}")

        lines.append("")
        lines.append("Need more?")
        lines.append("  /help search <term>   Search help by keyword")
        lines.append("  /help <command>       Detailed help for a command")
        lines.append("  /help <category>      Help for a category")
        lines.append("")

        return "\n".join(lines)

    def show_categories(self) -> str:
        """Show all help categories."""
        output = "Available help categories:\n\n"

        for category, info in self.categories.items():
            if isinstance(info, dict) and "description" in info:
                output += f"  {category:15} - {info['description']}\n"

        output += "\nUsage: /help <category> for more details"
        return output

    def get_command_help(self, command: str) -> str:
        """Get detailed help for a command."""
        cmd_info = self.command_help.get(command)

        if not cmd_info:
            return f"Unknown command: {command}\n\nType /help commands for list"

        return self._format_command_help(command, cmd_info)

    def get_category_help(self, category: str) -> str:
        """Get help for a category."""
        if category not in self.categories:
            return self.search(category)

        cat_info = self.categories[category]
        return self._format_category_help(category, cat_info)

    def search(self, query: str) -> str:
        """Search help content by keyword."""
        results = search_help(query, self.categories)
        return format_search_results(results, query)

    def get_suggestion(self, input_text: str) -> Optional[str]:
        """Get suggestion for mistyped command."""
        from difflib import get_close_matches

        all_commands = list(self.command_help.keys())
        matches = get_close_matches(input_text, all_commands, n=3, cutoff=0.6)

        if matches:
            suggestions = "\n  ".join(matches)
            return f"Did you mean one of these?\n  {suggestions}\n\nType /help <command> for details."

        return None

    def get_context_tip(self, context: str) -> Optional[str]:
        """Show relevant tip for current context."""
        import random

        tips = self.tips.get(context, [])
        if tips:
            tip = random.choice(tips)
            return f"Tip: {tip}"
        return None

    def _format_command_help(self, cmd: str, info: Dict) -> str:
        """Format detailed command help."""
        output = f"\n{cmd} - {info['brief']}\n"
        output += "=" * 40 + "\n\n"

        output += "Description:\n"
        output += f"  {info['description']}\n\n"

        output += "Syntax:\n"
        output += f"  {info['syntax']}\n\n"

        if info.get("examples"):
            output += "Examples:\n"
            for ex in info["examples"]:
                output += f"  {ex}\n"
            output += "\n"

        if info.get("tips"):
            output += "Tips:\n"
            for tip in info["tips"]:
                output += f"  - {tip}\n"
            output += "\n"

        if info.get("related"):
            output += "Related:\n"
            for rel in info["related"]:
                output += f"  {rel}\n"

        return output

    def _format_category_help(self, category: str, info: Dict) -> str:
        """Format category help."""
        output = f"\n{category.title()}\n"
        output += "=" * 40 + "\n\n"

        if "description" in info:
            output += f"{info['description']}\n\n"

        if "items" in info:
            for name, details in info["items"].items():
                if isinstance(details, dict):
                    brief = details.get("brief", "")
                    output += f"  {name:25} {brief}\n"
                else:
                    output += f"  {name:25} {details}\n"

        output += "\nUsage: /help <command> for detailed help"
        return output
