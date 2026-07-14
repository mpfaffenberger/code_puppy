"""Help content data structures for the help system."""

HELP_CATEGORIES = {
    "commands": {
        "description": "All available slash commands",
        "items": {
            "/help": {
                "brief": "Show this help message",
                "description": "Display the help system with categorized commands and guidance.",
                "syntax": "/help [category|command|search <term>|ask <question>]",
                "examples": [
                    "/help                      # Show main help",
                    "/help commands             # List all commands",
                    "/help /agent               # Detailed help for /agent",
                    "/help search model         # Search for 'model'",
                    "/help ask How do I...?     # AI-powered answer",
                ],
                "related": [],
            },
            "/agent": {
                "brief": "Switch to a different agent or show available agents",
                "description": "Switch between different coding agents. Each agent has its own personality, tools, and specialized knowledge.",
                "syntax": "/agent [agent-name]",
                "examples": [
                    "/agent                     # Show all agents",
                    "/agent code-puppy          # Switch to default agent",
                    "/agent python-tutor        # Switch to Python tutor",
                ],
                "related": ["/model", "/add_model"],
            },
            "/model": {
                "brief": "Set active model",
                "description": "Choose which LLM model to use for responses.",
                "syntax": "/model [model-name]",
                "examples": [
                    "/model                     # Show model picker",
                    "/model gpt-4               # Switch to GPT-4",
                    "/model claude-opus         # Switch to Claude",
                ],
                "related": ["/add_model", "/agent"],
            },
            "/add_model": {
                "brief": "Browse and add models from models.dev catalog",
                "description": "Browse and add 1000+ models from 65+ providers via models.dev.",
                "syntax": "/add_model",
                "examples": [
                    "/add_model                 # Open model browser",
                ],
                "related": ["/model", "/model_settings"],
            },
            "/model_settings": {
                "brief": "Configure per-model settings (temperature, seed, etc.)",
                "description": "Fine-tune model parameters like temperature, max tokens, and system prompts.",
                "syntax": "/model_settings [--show [model_name]]",
                "examples": [
                    "/model_settings            # Open settings TUI",
                    "/model_settings --show     # Show current settings",
                ],
                "related": ["/model", "/add_model"],
            },
            "/cd": {
                "brief": "Change directory or show directories",
                "description": "Change the working directory or list contents of the current directory.",
                "syntax": "/cd <dir>",
                "examples": [
                    "/cd                        # List current directory",
                    "/cd src                    # Change to src/ directory",
                    "/cd ~/projects             # Change to ~/projects",
                ],
                "related": [],
            },
            "/tools": {
                "brief": "Show available tools and capabilities",
                "description": "Display all tools available to the current agent.",
                "syntax": "/tools",
                "examples": [
                    "/tools                     # Show all tools",
                ],
                "related": ["/agent"],
            },
            "/paste": {
                "brief": "Paste image from clipboard",
                "description": "Paste an image from the clipboard into the pending attachments.",
                "syntax": "/paste, /clipboard, /cb",
                "examples": [
                    "/paste                     # Paste clipboard image",
                    "/clipboard                 # Same as /paste",
                ],
                "related": [],
            },
            "/exit": {
                "brief": "Exit interactive mode",
                "description": "End the current session and exit Code Puppy.",
                "syntax": "/exit, /quit",
                "examples": [
                    "/exit                      # Exit Code Puppy",
                    "/quit                      # Same as /exit",
                ],
                "related": [],
            },
            "/undo": {
                "brief": "Undo the last file modification",
                "description": "Undo the most recent file change made by the agent.",
                "syntax": "/undo",
                "examples": [
                    "/undo                      # Undo last file change",
                ],
                "related": [],
            },
            "/plan": {
                "brief": "Create a plan-only response without executing tools",
                "description": "Generate a planning prompt that returns only analysis and plans, no file changes.",
                "syntax": "/plan <goal>",
                "examples": [
                    "/plan Add user authentication",
                ],
                "related": [],
            },
            "/generate-pr-description": {
                "brief": "Generate comprehensive PR description",
                "description": "Analyze current branch changes and generate a PR description.",
                "syntax": "/generate-pr-description [@dir]",
                "examples": [
                    "/generate-pr-description    # Generate for current branch",
                ],
                "related": [],
            },
        },
    },
    "session": {
        "description": "Session management and history",
        "items": {
            "session": {
                "brief": "Show or rotate autosave session ID",
                "description": "Manage your autosave sessions for context preservation.",
            },
            "clear": {
                "brief": "Clear the current conversation",
                "description": "Reset the conversation history while keeping the current session.",
            },
            "load": {
                "brief": "Load a previous session",
                "description": "Restore a previously saved session to continue where you left off.",
            },
            "save": {
                "brief": "Save current session",
                "description": "Manually save the current session state.",
            },
        },
    },
    "config": {
        "description": "Configuration and settings",
        "items": {
            "set": {
                "brief": "Configure Code Puppy settings",
                "description": "Open the interactive settings menu to customize Code Puppy.",
            },
            "colors": {
                "brief": "Customize terminal colors",
                "description": "Change the color scheme for the terminal interface.",
            },
        },
    },
    "plugins": {
        "description": "Plugin and extension management",
        "items": {
            "hooks": {
                "brief": "Manage event hooks",
                "description": "View and manage hooks that trigger on events.",
            },
            "skills": {
                "brief": "Manage skills",
                "description": "View and manage available skills for agents.",
            },
            "kennel": {
                "brief": "Manage agent kennel",
                "description": "Manage your collection of agents in the kennel.",
            },
        },
    },
}

COMMAND_HELP = {
    "/agent": {
        "brief": "Manage and switch between agents",
        "description": "Switch between different coding agents. Each agent has its own personality, tools, and specialized knowledge.",
        "syntax": "/agent [agent-name]",
        "examples": [
            "/agent                     # Show all agents",
            "/agent code-puppy          # Switch to default agent",
            "/agent python-tutor        # Switch to Python tutor",
        ],
        "tips": [
            "Each agent has different tools and personalities",
            "Use /agent agent-creator to build your own",
            "Agents remember context within a session",
        ],
        "related": ["/model", "agent-creator"],
    },
    "/model": {
        "brief": "Select or configure AI models",
        "description": "Choose which LLM model to use for responses.",
        "syntax": "/model [model-name]",
        "examples": [
            "/model                     # Show model picker",
            "/model gpt-4               # Switch to GPT-4",
            "/model claude-opus         # Switch to Claude",
        ],
        "tips": [
            "Use /add_model to browse 1000+ models from models.dev",
            "Use /model_settings to fine-tune parameters",
            "Different models have different strengths",
        ],
        "related": ["/add_model", "/model_settings"],
    },
    "/help": {
        "brief": "Show this help message",
        "description": "Display the help system with categorized commands and guidance.",
        "syntax": "/help [category|command|search <term>|ask <question>]",
        "examples": [
            "/help                      # Show main help",
            "/help commands             # List all commands",
            "/help /agent               # Detailed help for /agent",
            "/help search model         # Search for 'model'",
            "/help ask How do I...?     # AI-powered answer",
        ],
        "tips": [
            "Use /help search <keyword> to find specific topics",
            "Use /help ask <question> for AI-powered answers",
            "Progressive disclosure - start simple, go deeper",
        ],
        "related": [],
    },
}

TIPS = {
    "model_selection": [
        "Use /model to switch between available models",
        "Use /add_model to browse models from models.dev",
        "Use /model_settings to configure temperature and other parameters",
    ],
    "agent_switching": [
        "Use /agent to switch between agents",
        "Each agent has different tools and capabilities",
        "Use /tools to see what's available for the current agent",
    ],
    "file_editing": [
        "Use /grep to search file contents before editing",
        "Use /undo to revert the last file change",
        "The agent automatically tracks file modifications",
    ],
    "getting_started": [
        "Start with /tutorial to learn the basics",
        "Use /help commands to see all available commands",
        "Try /plan for planning-only mode",
    ],
}
