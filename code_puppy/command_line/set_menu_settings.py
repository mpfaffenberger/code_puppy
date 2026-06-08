"""Settings definitions for the interactive /set config menu.

Each setting is a tuple:
  (key, display_name, description, type_hint, valid_values_or_none)

type_hint: "bool", "int", "float", "string", "choice"
valid_values: list of allowed strings (for choice) or None
"""

from typing import List, Tuple

# ============================================================================
# Setting definitions: each category contains a list of setting descriptors
# ============================================================================

SETTINGS_CATEGORIES: List[Tuple[str, List[Tuple]]] = [
    # --- Identity ---
    (
        " Identity",
        [
            (
                "puppy_name",
                "Puppy Name",
                "The name of your Code Puppy agent.",
                "string",
                None,
            ),
            (
                "owner_name",
                "Owner Name",
                "Your name - how the puppy knows you.",
                "string",
                None,
            ),
        ],
    ),
    # --- Model ---
    (
        " Model",
        [
            (
                "model",
                "Default Model",
                "The default AI model used for all agent tasks.",
                "string",
                None,
            ),
            (
                "summarization_model",
                "Summarization Model",
                "Model used for context compaction/summarization. Leave empty to use default model.",
                "string",
                None,
            ),
            (
                "temperature",
                "Temperature",
                "Global temperature override (0.0-2.0). Lower = deterministic, higher = creative. Empty = model default.",
                "float",
                None,
            ),
        ],
    ),
    # --- Behavior ---
    (
        " Behavior",
        [
            (
                "yolo_mode",
                "YOLO Mode",
                "Skip confirmation prompts for destructive actions. Use with caution!",
                "bool",
                None,
            ),
            (
                "allow_recursion",
                "Allow Recursion",
                "Allow agents to invoke other agents recursively.",
                "bool",
                None,
            ),
            (
                "enable_streaming",
                "Enable Streaming",
                "Stream model responses token-by-token instead of waiting for full response.",
                "bool",
                None,
            ),
            (
                "subagent_verbose",
                "Sub-agent Verbose",
                "Show full verbose output from sub-agents (useful for debugging).",
                "bool",
                None,
            ),
            (
                "http2",
                "HTTP/2",
                "Use HTTP/2 for API calls (may improve performance with some providers).",
                "bool",
                None,
            ),
        ],
    ),
    # --- Session ---
    (
        " Session",
        [
            (
                "auto_save_session",
                "Auto-Save Session",
                "Automatically save chat history after every agent response.",
                "bool",
                None,
            ),
            (
                "max_saved_sessions",
                "Max Saved Sessions",
                "Maximum number of autosaved sessions to retain.",
                "int",
                None,
            ),
            (
                "resume_message_count",
                "Resume Message Count",
                "Number of recent messages shown when resuming a session.",
                "int",
                None,
            ),
        ],
    ),
    # --- Compaction ---
    (
        " Compaction",
        [
            (
                "compaction_strategy",
                "Compaction Strategy",
                "How to compress context when it gets too large.",
                "choice",
                ["summarization", "truncation"],
            ),
            (
                "compaction_threshold",
                "Compaction Threshold",
                "Context usage percentage that triggers compaction (0.0-1.0).",
                "float",
                None,
            ),
            (
                "protected_token_count",
                "Protected Token Count",
                "Number of recent tokens always preserved during compaction.",
                "int",
                None,
            ),
        ],
    ),
    # --- OpenAI ---
    (
        " OpenAI",
        [
            (
                "openai_reasoning_effort",
                "Reasoning Effort",
                "How much reasoning effort GPT-5 models should use.",
                "choice",
                ["minimal", "low", "medium", "high", "xhigh"],
            ),
            (
                "openai_reasoning_summary",
                "Reasoning Summary",
                "Style of reasoning summary shown to the user.",
                "choice",
                ["auto", "concise", "detailed"],
            ),
            (
                "openai_verbosity",
                "Verbosity",
                "How verbose GPT-5 model responses should be.",
                "choice",
                ["low", "medium", "high"],
            ),
        ],
    ),
    # --- Features ---
    (
        " Features",
        [
            (
                "enable_pack_agents",
                "Pack Agents",
                "Enable specialized pack agents (bloodhound, shepherd, terrier, etc.).",
                "bool",
                None,
            ),
            (
                "enable_universal_constructor",
                "Universal Constructor",
                "Allow agents to dynamically create custom tools at runtime.",
                "bool",
                None,
            ),
            (
                "enable_dbos",
                "DBOS Durable Execution",
                "Enable DBOS durable execution plugin. Restart required after changing.",
                "bool",
                None,
            ),
            (
                "frontend_emitter_enabled",
                "Frontend Emitter",
                "Enable the frontend event emitter for external integrations.",
                "bool",
                None,
            ),
            (
                "frontend_emitter_max_recent_events",
                "Emitter Max Events",
                "Maximum number of recent events kept in the emitter buffer.",
                "int",
                None,
            ),
            (
                "frontend_emitter_queue_size",
                "Emitter Queue Size",
                "Size of the frontend emitter event queue.",
                "int",
                None,
            ),
        ],
    ),
    # --- Goal / Wiggum ---
    (
        " Goal",
        [
            (
                "goal_max_iterations",
                "Goal Max Iterations",
                "Maximum number of iterations for goal-driven tasks.",
                "int",
                None,
            ),
            (
                "goal_expert_threshold",
                "Expert Threshold",
                "Number of normal loops before switching to expert model.",
                "int",
                None,
            ),
            (
                "goal_expert_model",
                "Expert Model",
                "Model to use for expert-mode goal iterations.",
                "string",
                None,
            ),
        ],
    ),
    # --- Keyboard ---
    (
        " Keyboard",
        [
            (
                "cancel_agent_key",
                "Cancel Agent Key",
                "Key combination to cancel a running agent task. Restart required.",
                "choice",
                ["ctrl+c", "ctrl+k", "ctrl+q"],
            ),
            (
                "pause_agent_key",
                "Pause Agent Key",
                "Key combination to pause a running agent task.",
                "choice",
                ["ctrl+c", "ctrl+k", "ctrl+q"],
            ),
            (
                "max_pause_seconds",
                "Max Pause Seconds",
                "Auto-resume pause after this many seconds to prevent upstream timeout.",
                "int",
                None,
            ),
        ],
    ),
    # --- Diff ---
    (
        " Diff",
        [
            (
                "diff_context_lines",
                "Diff Context Lines",
                "Number of context lines shown around diff changes.",
                "int",
                None,
            ),
        ],
    ),
    # --- Hooks ---
    (
        " Hooks",
        [
            (
                "max_hook_retries",
                "Max Hook Retries",
                "Maximum plugin hook retries after an agent run before giving up.",
                "int",
                None,
            ),
        ],
    ),
    # --- API Keys ---
    (
        " API Keys",
        [
            (
                "puppy_token",
                "Puppy Token",
                "Authentication token for Code Puppy services.",
                "string",
                None,
            ),
        ],
    ),
]  # End of SETTINGS_CATEGORIES
