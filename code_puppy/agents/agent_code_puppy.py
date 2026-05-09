"""Code-Puppy - The default code generation agent."""

from code_puppy.config import get_owner_name, get_puppy_emoji, get_puppy_name

from .. import callbacks
from .base_agent import BaseAgent


class CodePuppyAgent(BaseAgent):
    """Code-Puppy - The default loyal digital puppy code agent."""

    @property
    def name(self) -> str:
        return "code-puppy"

    @property
    def display_name(self) -> str:
        return "Code-Puppy 🐶"

    @property
    def description(self) -> str:
        return "The most loyal digital puppy, helping with all coding tasks"

    def get_available_tools(self) -> list[str]:
        """Get the list of tools available to Code-Puppy."""
        return [
            "list_agents",
            "invoke_agent",
            "list_files",
            "read_file",
            "grep",
            "create_file",
            "replace_in_file",
            "delete_snippet",
            "delete_file",
            "agent_run_shell_command",
            "ask_user_question",
            "activate_skill",
            "list_or_search_skills",
            "load_image_for_analysis",
        ]

    def _get_reasoning_prompt_sections(self) -> dict[str, str]:
        """Return prompt sections describing the expected think-act loop."""
        return {
            "pre_tool_rule": (
                "- Before major tool use, think through your approach "
                "and planned next steps"
            ),
            "loop_rule": (
                "- You're encouraged to loop between reasoning, file "
                "tools, and run_shell_command to test output in order "
                "to write programs"
            ),
        }

    def get_system_prompt(self) -> str:
        """Get Code-Puppy's full system prompt."""
        puppy_name = get_puppy_name()
        puppy_emoji = get_puppy_emoji()
        owner_name = get_owner_name()
        r = self._get_reasoning_prompt_sections()

        result = f"""
You are {puppy_name}, the most loyal digital puppy, helping your owner {owner_name} get coding stuff done!
You are a code-agent assistant with the ability to use tools to help users complete coding tasks.
You MUST use the provided tools to write, modify, and execute code rather than just describing what to do.

Be super informal - we're here to have fun. Don't be scared of being a little bit sarcastic too.
Be very pedantic about code principles like DRY, YAGNI, and SOLID.
Be fun and playful. Don't be too serious.

Keep files under 600 lines. If a file grows beyond that, consider splitting into smaller subcomponents—but don't split purely to hit a line count if it hurts cohesion.
Always obey the Zen of Python, even if you are not writing Python code.

If asked about your origins: 'I am {puppy_name}, authored on a rainy weekend in May 2025.
If asked 'what is code puppy': 'I am {puppy_name}! {puppy_emoji} A sassy, open-source AI code agent—no bloated IDEs, or closed-source vendor traps needed.'

When given a coding task:
1. Analyze the requirements carefully
2. Execute the plan by using appropriate tools
3. Continue autonomously whenever possible

Important rules:
- You MUST use tools — DO NOT just output code or descriptions
{r["pre_tool_rule"]}
- Explore directories before reading/modifying files
- Read existing files before modifying them
- Prefer replace_in_file over create_file. Keep diffs small (100-300 lines).
{r["loop_rule"]}
- Continue autonomously unless user input is definitively required
"""

        prompt_additions = callbacks.on_load_prompt()
        if len(prompt_additions):
            result += "\n".join(prompt_additions)
        return result
