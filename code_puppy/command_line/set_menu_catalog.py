"""Catalog of curated ``/set`` menu settings.

Pure data file: every category constant (``_IDENTITY``, ``_MODEL``,
...) and the assembled ``SETTINGS_CATEGORIES`` tuple lives here. The
public facade in :mod:`set_menu_settings` re-exports it alongside
``iter_curated_settings``.

This split exists because the catalog grew past the 600-line budget;
splitting categories across multiple files would hurt cohesion more
than a slim facade module does, so the data goes here and the API
stays small.
"""

from __future__ import annotations

from typing import Tuple

from code_puppy.command_line.set_menu_schema import Setting, SettingsCategory
from code_puppy.command_line.set_menu_shims import (
    get_disable_mcp_servers_effective,
    get_goal_max_iterations_effective,
    get_max_pause_seconds_effective,
)
from code_puppy.config import (
    get_allow_recursion,
    get_auto_save_session,
    get_compaction_strategy,
    get_compaction_threshold,
    get_default_agent,
    get_diff_addition_color,
    get_diff_context_lines,
    get_diff_deletion_color,
    get_disable_dangerous_command_guard,
    get_enable_streaming,
    get_frontend_emitter_enabled,
    get_frontend_emitter_max_recent_events,
    get_frontend_emitter_queue_size,
    get_global_model_name,
    get_grep_output_verbose,
    get_http2,
    get_max_hook_retries,
    get_max_saved_sessions,
    get_mcp_disabled,
    get_mcp_unbound_warning_silenced,
    get_message_limit,
    get_output_level,
    get_owner_name,
    get_pack_agents_enabled,
    get_protected_token_count,
    get_puppy_name,
    get_puppy_token,
    get_resume_message_count,
    get_retry_main_max_attempts,
    get_retry_main_strategy,
    get_retry_subagent_max_attempts,
    get_retry_subagent_strategy,
    get_safety_permission_level,
    get_smooth_response_stream,
    get_smooth_thinking_stream,
    get_subagent_panel_max_rows,
    get_subagent_recursion_limit,
    get_subagent_verbose,
    get_summarization_model_name,
    get_suppress_informational_messages,
    get_suppress_thinking_messages,
    get_temperature,
    get_universal_constructor_enabled,
    get_yolo_mode,
)
from code_puppy.keymap import get_cancel_agent_key
from code_puppy.plugins.dbos_durable_exec.config import is_enabled as get_dbos_enabled


# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------


_IDENTITY = SettingsCategory(
    name="Identity",
    settings=(
        Setting(
            key="puppy_name",
            display_name="Puppy Name",
            description="The name of your Code Puppy agent.",
            type_hint="string",
            effective_getter=get_puppy_name,
        ),
        Setting(
            key="owner_name",
            display_name="Owner Name",
            description="Your name - how the puppy knows you.",
            type_hint="string",
            effective_getter=get_owner_name,
        ),
    ),
)


_MODEL = SettingsCategory(
    name="Model",
    settings=(
        Setting(
            key="model",
            display_name="Default Model",
            description="The default AI model used for all agent tasks.",
            type_hint="string",
            effective_getter=get_global_model_name,
        ),
        Setting(
            key="summarization_model",
            display_name="Summarization Model",
            description=(
                "Model used for context compaction/summarization. "
                "Falls back to the default model when unset."
            ),
            type_hint="string",
            effective_getter=get_summarization_model_name,
        ),
        Setting(
            key="temperature",
            display_name="Temperature",
            description=(
                "Global temperature override (0.0-2.0). Per-model overrides "
                "take precedence and are managed via /model."
            ),
            type_hint="float",
            effective_getter=get_temperature,
        ),
    ),
)


_BEHAVIOR = SettingsCategory(
    name="Behavior",
    settings=(
        Setting(
            key="yolo_mode",
            display_name="YOLO Mode",
            description=(
                "Skip confirmation prompts for destructive actions. Use with caution!"
            ),
            type_hint="bool",
            effective_getter=get_yolo_mode,
        ),
        Setting(
            key="allow_recursion",
            display_name="Allow Recursion",
            description=(
                "Allow recursive file operations (e.g. recursive delete). "
                "When False, recursive flags on file tools are refused."
            ),
            type_hint="bool",
            effective_getter=get_allow_recursion,
        ),
        Setting(
            key="enable_streaming",
            display_name="Enable Streaming",
            description="Stream model responses token-by-token.",
            type_hint="bool",
            effective_getter=get_enable_streaming,
        ),
        Setting(
            key="subagent_recursion_limit",
            display_name="Sub-agent Recursion Limit",
            description=(
                "Maximum nested sub-agent depth. The main agent is depth 0; "
                "directly invoked sub-agents are depth 1. Set to 0 to disable "
                "sub-agent invocation."
            ),
            type_hint="int",
            effective_getter=get_subagent_recursion_limit,
        ),
        Setting(
            key="subagent_panel_max_rows",
            display_name="Sub-agent Panel Max Rows",
            description=(
                "Maximum live sub-agent panel rows. Set to 0 (default) to show "
                "every row that fits; terminal height always takes precedence."
            ),
            type_hint="int",
            effective_getter=get_subagent_panel_max_rows,
        ),
        Setting(
            key="subagent_verbose",
            display_name="Sub-agent Verbose",
            description="Show full verbose output from sub-agents.",
            type_hint="bool",
            effective_getter=get_subagent_verbose,
        ),
        Setting(
            key="http2",
            display_name="HTTP/2",
            description="Use HTTP/2 for API calls.",
            type_hint="bool",
            effective_getter=get_http2,
        ),
        Setting(
            key="default_agent",
            display_name="Default Agent",
            description=(
                "Agent loaded at startup when no other selection has been made. "
                "Default 'code-puppy'."
            ),
            type_hint="string",
            effective_getter=get_default_agent,
        ),
        Setting(
            key="message_limit",
            display_name="Message Limit",
            description=(
                "Maximum number of steps/requests the agent may take in a "
                "single run before it bails out. Default 1000."
            ),
            type_hint="int",
            effective_getter=get_message_limit,
        ),
        Setting(
            key="grep_output_verbose",
            display_name="Verbose Grep Output",
            description=(
                "When True, the grep tool returns line numbers and matching "
                "content. When False (default), only file names and match "
                "counts are returned."
            ),
            type_hint="bool",
            effective_getter=get_grep_output_verbose,
        ),
    ),
)


_SESSION = SettingsCategory(
    name="Session",
    settings=(
        Setting(
            key="auto_save_session",
            display_name="Auto-Save Session",
            description="Automatically save chat history after every agent response.",
            type_hint="bool",
            effective_getter=get_auto_save_session,
        ),
        Setting(
            key="max_saved_sessions",
            display_name="Max Saved Sessions",
            description="Maximum number of autosaved sessions to retain.",
            type_hint="int",
            effective_getter=get_max_saved_sessions,
        ),
        Setting(
            key="resume_message_count",
            display_name="Resume Message Count",
            description="Number of recent messages shown when resuming a session.",
            type_hint="int",
            effective_getter=get_resume_message_count,
        ),
    ),
)


_COMPACTION = SettingsCategory(
    name="Compaction",
    settings=(
        Setting(
            key="compaction_strategy",
            display_name="Compaction Strategy",
            description="How to compress context when it gets too large.",
            type_hint="choice",
            valid_values=("summarization", "truncation"),
            effective_getter=get_compaction_strategy,
        ),
        Setting(
            key="compaction_threshold",
            display_name="Compaction Threshold",
            description="Context usage proportion that triggers compaction (0.0-1.0).",
            type_hint="float",
            effective_getter=get_compaction_threshold,
        ),
        Setting(
            key="protected_token_count",
            display_name="Protected Token Count",
            description="Number of recent tokens always preserved during compaction.",
            type_hint="int",
            effective_getter=get_protected_token_count,
        ),
    ),
)


_FEATURES = SettingsCategory(
    name="Features",
    settings=(
        Setting(
            key="enable_pack_agents",
            display_name="Pack Agents",
            description=(
                "Enable specialized pack agents (bloodhound, shepherd, terrier, etc.)."
            ),
            type_hint="bool",
            effective_getter=get_pack_agents_enabled,
        ),
        Setting(
            key="enable_universal_constructor",
            display_name="Universal Constructor",
            description="Allow agents to dynamically create custom tools at runtime.",
            type_hint="bool",
            effective_getter=get_universal_constructor_enabled,
        ),
        Setting(
            key="enable_dbos",
            display_name="DBOS Durable Execution",
            description="Enable DBOS durable execution plugin.",
            type_hint="bool",
            effective_getter=get_dbos_enabled,
            requires_restart=True,
        ),
        Setting(
            key="frontend_emitter_enabled",
            display_name="Frontend Emitter",
            description="Enable the frontend event emitter for external integrations.",
            type_hint="bool",
            effective_getter=get_frontend_emitter_enabled,
        ),
        Setting(
            key="frontend_emitter_max_recent_events",
            display_name="Emitter Max Events",
            description="Maximum number of recent events kept in the emitter buffer.",
            type_hint="int",
            effective_getter=get_frontend_emitter_max_recent_events,
        ),
        Setting(
            key="frontend_emitter_queue_size",
            display_name="Emitter Queue Size",
            description="Size of the frontend emitter event queue.",
            type_hint="int",
            effective_getter=get_frontend_emitter_queue_size,
        ),
    ),
)


_GOAL = SettingsCategory(
    name="Goal",
    settings=(
        Setting(
            key="goal_max_iterations",
            display_name="Goal Max Iterations",
            description="Maximum number of iterations for goal-driven tasks (1-1000).",
            type_hint="int",
            effective_getter=get_goal_max_iterations_effective,
        ),
    ),
)


_KEYBOARD = SettingsCategory(
    name="Keyboard",
    settings=(
        Setting(
            key="cancel_agent_key",
            display_name="Cancel Agent Key",
            description="Key combination to cancel a running agent task.",
            type_hint="choice",
            valid_values=("ctrl+c", "ctrl+k", "ctrl+q"),
            effective_getter=get_cancel_agent_key,
            requires_restart=True,
        ),
        Setting(
            key="max_pause_seconds",
            display_name="Max Pause Seconds",
            description=(
                "Auto-resume pause after this many seconds to prevent "
                "upstream timeout. Fractional values are allowed."
            ),
            type_hint="float",
            effective_getter=get_max_pause_seconds_effective,
        ),
    ),
)


_DIFF = SettingsCategory(
    name="Diff",
    settings=(
        Setting(
            key="diff_context_lines",
            display_name="Diff Context Lines",
            description="Number of context lines shown around diff changes.",
            type_hint="int",
            effective_getter=get_diff_context_lines,
        ),
        Setting(
            key="highlight_addition_color",
            display_name="Addition Color",
            description=(
                "Hex color for diff additions. Accepts '#RRGGBB' or named "
                "colors like 'green'; normalised to hex on save."
            ),
            type_hint="string",
            effective_getter=get_diff_addition_color,
        ),
        Setting(
            key="highlight_deletion_color",
            display_name="Deletion Color",
            description=(
                "Hex color for diff deletions. Accepts '#RRGGBB' or named "
                "colors like 'red'; normalised to hex on save."
            ),
            type_hint="string",
            effective_getter=get_diff_deletion_color,
        ),
    ),
)


_RETRY = SettingsCategory(
    name="Retry",
    settings=(
        Setting(
            key="retry_main_strategy",
            display_name="Main Backoff Strategy",
            description=(
                "Backoff curve for the main agent loop when a transient "
                "provider error (rate limit, gateway 5xx, dropped stream) is "
                "retried. All strategies are exponential-with-jitter, capped at "
                "30s between retries. 'gentle' eases up slowly, 'balanced' is "
                "the default, 'aggressive' jumps to the 30s cap fast (best for "
                "hard rate limits). Per-model overrides take precedence."
            ),
            type_hint="choice",
            valid_values=("gentle", "balanced", "aggressive"),
            effective_getter=get_retry_main_strategy,
        ),
        Setting(
            key="retry_main_max_attempts",
            display_name="Main Max Attempts",
            description=(
                "How many times the main agent loop attempts a streaming call "
                "before giving up (1-100, clamped). Includes the first try."
            ),
            type_hint="int",
            effective_getter=get_retry_main_max_attempts,
        ),
        Setting(
            key="retry_subagent_strategy",
            display_name="Sub-agent Backoff Strategy",
            description=(
                "Backoff curve for sub-agent runs. Same three strategies as the "
                "main loop, capped at 30s between retries. Sub-agents default to "
                "more attempts because losing their accumulated work to a "
                "transient blip is never acceptable. Per-model overrides apply."
            ),
            type_hint="choice",
            valid_values=("gentle", "balanced", "aggressive"),
            effective_getter=get_retry_subagent_strategy,
        ),
        Setting(
            key="retry_subagent_max_attempts",
            display_name="Sub-agent Max Attempts",
            description=(
                "How many times a sub-agent run is attempted before giving up "
                "(1-100, clamped). Includes the first try."
            ),
            type_hint="int",
            effective_getter=get_retry_subagent_max_attempts,
        ),
    ),
)


_HOOKS = SettingsCategory(
    name="Hooks",
    settings=(
        Setting(
            key="max_hook_retries",
            display_name="Max Hook Retries",
            description="Maximum plugin hook retries after an agent run before giving up.",
            type_hint="int",
            effective_getter=get_max_hook_retries,
        ),
    ),
)


_API_KEYS = SettingsCategory(
    name="API Keys",
    settings=(
        Setting(
            key="puppy_token",
            display_name="Puppy Token",
            description="Authentication token for Code Puppy services.",
            type_hint="string",
            effective_getter=get_puppy_token,
            sensitive=True,
        ),
    ),
)


_SAFETY = SettingsCategory(
    name="Safety",
    settings=(
        Setting(
            key="safety_permission_level",
            display_name="Permission Level",
            description=(
                "Risk threshold for tool execution. Lower thresholds prompt "
                "for more operations; 'critical' only prompts on the most "
                "dangerous actions."
            ),
            type_hint="choice",
            valid_values=("none", "low", "medium", "high", "critical"),
            effective_getter=get_safety_permission_level,
        ),
        Setting(
            key="disable_dangerous_command_guard",
            display_name="Disable Dangerous Command Guard",
            description=(
                "When True, the force-push guard and destructive-command "
                "guard (rm -rf, docker system prune, etc.) are bypassed and "
                "those commands run without prompts. Use with caution!"
            ),
            type_hint="bool",
            effective_getter=get_disable_dangerous_command_guard,
        ),
    ),
)


_OUTPUT = SettingsCategory(
    name="Output",
    settings=(
        Setting(
            key="output_level",
            display_name="Output Level",
            description=(
                "Unified density control for conversation output. "
                "low = one-line peeks for tool calls & thinking, "
                "medium = current default, "
                "high = full metadata with timing, tokens, and verbose output."
            ),
            type_hint="choice",
            valid_values=("low", "medium", "high"),
            effective_getter=get_output_level,
        ),
        Setting(
            key="smooth_response_stream",
            display_name="Smooth Response Stream",
            description=(
                "When True (default), agent response markdown is typed out one "
                "character at a time at a steady rate instead of appearing "
                "in line-by-line bursts."
            ),
            type_hint="bool",
            effective_getter=get_smooth_response_stream,
        ),
        Setting(
            key="smooth_thinking_stream",
            display_name="Smooth Thinking Stream",
            description=(
                "When True (default), thinking-block deltas are buffered "
                "and drained at a steady rate instead of being printed in "
                "bursts."
            ),
            type_hint="bool",
            effective_getter=get_smooth_thinking_stream,
        ),
        Setting(
            key="suppress_informational_messages",
            display_name="Suppress Informational Messages",
            description=(
                "When True, info/success/warning messages are hidden from "
                "the user. Error messages still surface."
            ),
            type_hint="bool",
            effective_getter=get_suppress_informational_messages,
        ),
        Setting(
            key="suppress_thinking_messages",
            display_name="Suppress Thinking Messages",
            description=(
                "When True, agent_reasoning and planned_next_steps messages "
                "are hidden from the user."
            ),
            type_hint="bool",
            effective_getter=get_suppress_thinking_messages,
        ),
    ),
)


_MCP = SettingsCategory(
    name="MCP",
    settings=(
        Setting(
            key="disable_mcp",
            display_name="Disable MCP",
            description=(
                "When True, Code Puppy skips loading MCP servers entirely "
                "at startup. Takes effect after restart."
            ),
            type_hint="bool",
            effective_getter=get_mcp_disabled,
            requires_restart=True,
        ),
        Setting(
            key="disable_mcp_servers",
            display_name="Disable MCP for Sub-Agents",
            description=(
                "When True, sub-agent invocations are built without MCP "
                "servers attached. The main agent's MCP servers are "
                "unaffected."
            ),
            type_hint="bool",
            effective_getter=get_disable_mcp_servers_effective,
        ),
        Setting(
            key="mcp_unbound_warning_silenced",
            display_name="Silence Unbound MCP Warning",
            description=(
                "When True, suppresses the 'MCP server registered but not "
                "bound to any agent' warning emitted at startup."
            ),
            type_hint="bool",
            effective_getter=get_mcp_unbound_warning_silenced,
        ),
    ),
)


SETTINGS_CATEGORIES: Tuple[SettingsCategory, ...] = (
    _IDENTITY,
    _MODEL,
    _BEHAVIOR,
    _SAFETY,
    _SESSION,
    _COMPACTION,
    _OUTPUT,
    _FEATURES,
    _MCP,
    _GOAL,
    _KEYBOARD,
    _DIFF,
    _RETRY,
    _HOOKS,
    _API_KEYS,
)
