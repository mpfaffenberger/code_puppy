"""Mist - the default coding agent."""

from code_puppy.branding import DEFAULT_AGENT_NAME, PRODUCT_EMOJI, PRODUCT_NAME
from code_puppy.config import get_mist_name, get_owner_name

from .base_agent import BaseAgent


class MistAgent(BaseAgent):
    """The default Mist coding agent."""

    @property
    def name(self) -> str:
        return DEFAULT_AGENT_NAME

    @property
    def display_name(self) -> str:
        return f"{PRODUCT_NAME} {PRODUCT_EMOJI}"

    @property
    def description(self) -> str:
        return "A contextual, adaptive coding agent for end-to-end software work"

    def get_available_tools(self) -> list[str]:
        """Get the tools available to Mist."""
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
        """Get Mist's current system prompt.

        A deeper prompt redesign is intentionally deferred; this change only
        removes the previous mascot identity and applies the Mist brand.
        """
        mist_name = get_mist_name()
        owner_name = get_owner_name()
        r = self._get_reasoning_prompt_sections()

        result = f"""
You are {mist_name}, an AI coding agent helping {owner_name} complete software-engineering work.
You are a code-agent assistant with the ability to use tools to help users complete coding tasks.
You MUST use the provided tools to write, modify, and execute code rather than just describing what to do.

Be very pedantic about code principles like DRY, YAGNI, and SOLID.

Keep files under 600 lines. If a file grows beyond that, consider splitting into smaller subcomponents—but don't split purely to hit a line count if it hurts cohesion.
Always obey the Zen of Python, even if you are not writing Python code.

If asked what you are: 'I am {mist_name}, an open-source AI coding agent.'

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
        # NOTE: runtime ``load_prompt`` fragments (plugin-injected notes such
        # as environment context, file-permission rules, memory recall, ...)
        # are intentionally NOT appended here — they're injected fresh at
        # runtime by ``BaseAgent.get_full_system_prompt`` so they never get
        # baked into a cloned/persisted agent definition.
        return result


# Import compatibility for integrations that referenced the old class name.
CodePuppyAgent = MistAgent
