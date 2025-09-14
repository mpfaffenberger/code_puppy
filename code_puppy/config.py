import configparser
import json
import os
import pathlib

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".code_puppy")
CONFIG_FILE = os.path.join(CONFIG_DIR, "puppy.cfg")
MCP_SERVERS_FILE = os.path.join(CONFIG_DIR, "mcp_servers.json")
COMMAND_HISTORY_FILE = os.path.join(CONFIG_DIR, "command_history.txt")
MODELS_FILE = os.path.join(CONFIG_DIR, "models.json")
EXTRA_MODELS_FILE = os.path.join(CONFIG_DIR, "extra_models.json")
AGENTS_DIR = os.path.join(CONFIG_DIR, "agents")

DEFAULT_SECTION = "puppy"
REQUIRED_KEYS = ["puppy_name", "owner_name"]


def ensure_config_exists():
    """
    Ensure that the .code_puppy dir and puppy.cfg exist, prompting if needed.
    Returns configparser.ConfigParser for reading.
    """
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)
    exists = os.path.isfile(CONFIG_FILE)
    config = configparser.ConfigParser()
    if exists:
        config.read(CONFIG_FILE)
    missing = []
    if DEFAULT_SECTION not in config:
        config[DEFAULT_SECTION] = {}
    for key in REQUIRED_KEYS:
        if not config[DEFAULT_SECTION].get(key):
            missing.append(key)
    if missing:
        print("🐾 Let's get your Puppy ready!")
        for key in missing:
            if key == "puppy_name":
                val = input("What should we name the puppy? ").strip()
            elif key == "owner_name":
                val = input(
                    "What's your name (so Code Puppy knows its owner)? "
                ).strip()
            else:
                val = input(f"Enter {key}: ").strip()
            config[DEFAULT_SECTION][key] = val
        with open(CONFIG_FILE, "w") as f:
            config.write(f)
    return config


def get_value(key: str):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    val = config.get(DEFAULT_SECTION, key, fallback=None)
    return val


def get_puppy_name():
    return get_value("puppy_name") or "Puppy"


def get_owner_name():
    return get_value("owner_name") or "Master"


# Legacy function removed - message history limit is no longer used
# Message history is now managed by token-based compaction system
# using get_protected_token_count() and get_summarization_threshold()


def get_allow_recursion() -> bool:
    """
    Get the allow_recursion configuration value.
    Returns True if recursion is allowed, False otherwise.
    """
    val = get_value("allow_recursion")
    if val is None:
        return True  # Default to False for safety
    return str(val).lower() in ("1", "true", "yes", "on")


def get_model_context_length() -> int:
    """
    Get the context length for the currently configured model from models.json
    """
    try:
        from code_puppy.model_factory import ModelFactory

        model_configs = ModelFactory.load_config()
        model_name = get_model_name()

        # Get context length from model config
        model_config = model_configs.get(model_name, {})
        context_length = model_config.get("context_length", 128000)  # Default value

        return int(context_length)
    except Exception:
        # Fallback to default context length if anything goes wrong
        return 128000


# --- CONFIG SETTER STARTS HERE ---
def get_config_keys():
    """
    Returns the list of all config keys currently in puppy.cfg,
    plus certain preset expected keys (e.g. "yolo_mode", "model", "compaction_strategy", "message_limit", "allow_recursion").
    """
    default_keys = [
        "yolo_mode",
        "model",
        "compaction_strategy",
        "protected_token_count",
        "compaction_threshold",
        "message_limit",
        "allow_recursion",
    ]
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    keys = set(config[DEFAULT_SECTION].keys()) if DEFAULT_SECTION in config else set()
    keys.update(default_keys)
    return sorted(keys)


def set_config_value(key: str, value: str):
    """
    Sets a config value in the persistent config file.
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if DEFAULT_SECTION not in config:
        config[DEFAULT_SECTION] = {}
    config[DEFAULT_SECTION][key] = value
    with open(CONFIG_FILE, "w") as f:
        config.write(f)


# --- MODEL STICKY EXTENSION STARTS HERE ---
def load_mcp_server_configs():
    """
    Loads the MCP server configurations from ~/.code_puppy/mcp_servers.json.
    Returns a dict mapping names to their URL or config dict.
    If file does not exist, returns an empty dict.
    """
    from code_puppy.messaging.message_queue import emit_error, emit_system_message

    try:
        if not pathlib.Path(MCP_SERVERS_FILE).exists():
            emit_system_message("[dim]No MCP configuration was found[/dim]")
            return {}
        with open(MCP_SERVERS_FILE, "r") as f:
            conf = json.loads(f.read())
            return conf["mcp_servers"]
    except Exception as e:
        emit_error(f"Failed to load MCP servers - {str(e)}")
        return {}


# Cache for model validation to prevent hitting ModelFactory on every call
_model_validation_cache = {}
_default_model_cache = None


def _default_model_from_models_json():
    """Attempt to load the first model name from models.json.

    Falls back to the hard-coded default (``gpt-5``) if the file
    cannot be read for any reason or is empty.
    """
    global _default_model_cache

    # Return cached default if we have one
    if _default_model_cache is not None:
        return _default_model_cache

    try:
        # Local import to avoid potential circular dependency on module import
        from code_puppy.model_factory import ModelFactory

        models_config = ModelFactory.load_config()
        if models_config:
            # Get the first key from the models config
            first_key = next(iter(models_config))
            _default_model_cache = first_key
            return first_key
        else:
            # If models_config is empty, fall back to gpt-5
            _default_model_cache = "gpt-5"
            return "gpt-5"
    except Exception:
        # Any problem (network, file missing, empty dict, etc.) => fall back to gpt-5
        _default_model_cache = "gpt-5"
        return "gpt-5"


def _validate_model_exists(model_name: str) -> bool:
    """Check if a model exists in models.json with caching to avoid redundant calls."""
    global _model_validation_cache

    # Check cache first
    if model_name in _model_validation_cache:
        return _model_validation_cache[model_name]

    try:
        from code_puppy.model_factory import ModelFactory

        models_config = ModelFactory.load_config()
        exists = model_name in models_config

        # Cache the result
        _model_validation_cache[model_name] = exists
        return exists
    except Exception:
        # If we can't validate, assume it exists to avoid breaking things
        _model_validation_cache[model_name] = True
        return True


def clear_model_cache():
    """Clear the model validation cache. Call this when models.json changes."""
    global _model_validation_cache, _default_model_cache
    _model_validation_cache.clear()
    _default_model_cache = None


def get_model_name():
    """Return a valid model name for Code Puppy to use.

    1. Look at ``model`` in *puppy.cfg*.
    2. If that value exists **and** is present in *models.json*, use it.
    3. Otherwise return the first model listed in *models.json*.
    4. As a last resort (e.g.
       *models.json* unreadable) fall back to ``claude-4-0-sonnet``.
    """

    stored_model = get_value("model")

    if stored_model:
        # Use cached validation to avoid hitting ModelFactory every time
        if _validate_model_exists(stored_model):
            return stored_model

    # Either no stored model or it's not valid – choose default from models.json
    return _default_model_from_models_json()


def set_model_name(model: str):
    """Sets the model name in the persistent config file."""
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if DEFAULT_SECTION not in config:
        config[DEFAULT_SECTION] = {}
    config[DEFAULT_SECTION]["model"] = model or ""
    with open(CONFIG_FILE, "w") as f:
        config.write(f)

    # Clear model cache when switching models to ensure fresh validation
    clear_model_cache()


def get_puppy_token():
    """Returns the puppy_token from config, or None if not set."""
    return get_value("puppy_token")


def set_puppy_token(token: str):
    """Sets the puppy_token in the persistent config file."""
    set_config_value("puppy_token", token)


def normalize_command_history():
    """
    Normalize the command history file by converting old format timestamps to the new format.

    Old format example:
    - "# 2025-08-04 12:44:45.469829"

    New format example:
    - "# 2025-08-05T10:35:33" (ISO)
    """
    import os
    import re

    # Skip implementation during tests
    import sys

    if "pytest" in sys.modules:
        return

    # Skip normalization if file doesn't exist
    command_history_exists = os.path.isfile(COMMAND_HISTORY_FILE)
    if not command_history_exists:
        return

    try:
        # Read the entire file
        with open(COMMAND_HISTORY_FILE, "r") as f:
            content = f.read()

        # Skip empty files
        if not content.strip():
            return

        # Define regex pattern for old timestamp format
        # Format: "# YYYY-MM-DD HH:MM:SS.ffffff"
        old_timestamp_pattern = r"# (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})\.(\d+)"

        # Function to convert matched timestamp to ISO format
        def convert_to_iso(match):
            date = match.group(1)
            time = match.group(2)
            # Create ISO format (YYYY-MM-DDThh:mm:ss)
            return f"# {date}T{time}"

        # Replace all occurrences of the old timestamp format with the new ISO format
        updated_content = re.sub(old_timestamp_pattern, convert_to_iso, content)

        # Write the updated content back to the file only if changes were made
        if content != updated_content:
            with open(COMMAND_HISTORY_FILE, "w") as f:
                f.write(updated_content)
    except Exception as e:
        from rich.console import Console

        direct_console = Console()
        error_msg = f"❌ An unexpected error occurred while normalizing command history: {str(e)}"
        direct_console.print(f"[bold red]{error_msg}[/bold red]")


def get_user_agents_directory() -> str:
    """Get the user's agents directory path.

    Returns:
        Path to the user's Code Puppy agents directory.
    """
    # Ensure the agents directory exists
    os.makedirs(AGENTS_DIR, exist_ok=True)
    return AGENTS_DIR


def initialize_command_history_file():
    """Create the command history file if it doesn't exist.
    Handles migration from the old history file location for backward compatibility.
    Also normalizes the command history format if needed.
    """
    import os
    from pathlib import Path

    command_history_exists = os.path.isfile(COMMAND_HISTORY_FILE)
    if not command_history_exists:
        try:
            Path(COMMAND_HISTORY_FILE).touch()

            # For backwards compatibility, copy the old history file, then remove it
            old_history_file = os.path.join(
                os.path.expanduser("~"), ".code_puppy_history.txt"
            )
            old_history_exists = os.path.isfile(old_history_file)
            if old_history_exists:
                import shutil

                shutil.copy2(Path(old_history_file), Path(COMMAND_HISTORY_FILE))
                Path(old_history_file).unlink(missing_ok=True)

                # Normalize the command history format if needed
                normalize_command_history()
        except Exception as e:
            from rich.console import Console

            direct_console = Console()
            error_msg = f"❌ An unexpected error occurred while trying to initialize history file: {str(e)}"
            direct_console.print(f"[bold red]{error_msg}[/bold red]")


def get_yolo_mode():
    """
    Checks puppy.cfg for 'yolo_mode' (case-insensitive in value only).
    Defaults to True if not set.
    Allowed values for ON: 1, '1', 'true', 'yes', 'on' (all case-insensitive for value).
    """
    true_vals = {"1", "true", "yes", "on"}
    cfg_val = get_value("yolo_mode")
    if cfg_val is not None:
        if str(cfg_val).strip().lower() in true_vals:
            return True
        return False
    return True


def get_mcp_disabled():
    """
    Checks puppy.cfg for 'disable_mcp' (case-insensitive in value only).
    Defaults to False if not set.
    Allowed values for ON: 1, '1', 'true', 'yes', 'on' (all case-insensitive for value).
    When enabled, Code Puppy will skip loading MCP servers entirely.
    """
    true_vals = {"1", "true", "yes", "on"}
    cfg_val = get_value("disable_mcp")
    if cfg_val is not None:
        if str(cfg_val).strip().lower() in true_vals:
            return True
        return False
    return False


def get_protected_token_count():
    """
    Returns the user-configured protected token count for message history compaction.
    This is the number of tokens in recent messages that won't be summarized.
    Defaults to 50000 if unset or misconfigured.
    Configurable by 'protected_token_count' key.
    Enforces that protected tokens don't exceed 75% of model context length.
    """
    val = get_value("protected_token_count")
    try:
        # Get the model context length to enforce the 75% limit
        model_context_length = get_model_context_length()
        max_protected_tokens = int(model_context_length * 0.75)

        # Parse the configured value
        configured_value = int(val) if val else 50000

        # Apply constraints: minimum 1000, maximum 75% of context length
        return max(1000, min(configured_value, max_protected_tokens))
    except (ValueError, TypeError):
        # If parsing fails, return a reasonable default that respects the 75% limit
        model_context_length = get_model_context_length()
        max_protected_tokens = int(model_context_length * 0.75)
        return min(50000, max_protected_tokens)


def get_compaction_threshold():
    """
    Returns the user-configured compaction threshold as a float between 0.0 and 1.0.
    This is the proportion of model context that triggers compaction.
    Defaults to 0.85 (85%) if unset or misconfigured.
    Configurable by 'compaction_threshold' key.
    """
    val = get_value("compaction_threshold")
    try:
        threshold = float(val) if val else 0.85
        # Clamp between reasonable bounds
        return max(0.8, min(0.95, threshold))
    except (ValueError, TypeError):
        return 0.85


def get_compaction_strategy() -> str:
    """
    Returns the user-configured compaction strategy.
    Options are 'summarization' or 'truncation'.
    Defaults to 'summarization' if not set or misconfigured.
    Configurable by 'compaction_strategy' key.
    """
    val = get_value("compaction_strategy")
    if val and val.lower() in ["summarization", "truncation"]:
        return val.lower()
    # Default to summarization
    return "truncation"


def get_message_limit(default: int = 100) -> int:
    """
    Returns the user-configured message/request limit for the agent.
    This controls how many steps/requests the agent can take.
    Defaults to 100 if unset or misconfigured.
    Configurable by 'message_limit' key.
    """
    val = get_value("message_limit")
    try:
        return int(val) if val else default
    except (ValueError, TypeError):
        return default


def save_command_to_history(command: str):
    """Save a command to the history file with an ISO format timestamp.

    Args:
        command: The command to save
    """
    import datetime

    try:
        timestamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(COMMAND_HISTORY_FILE, "a") as f:
            f.write(f"\n# {timestamp}\n{command}\n")
    except Exception as e:
        from rich.console import Console

        direct_console = Console()
        error_msg = (
            f"❌ An unexpected error occurred while saving command history: {str(e)}"
        )
        direct_console.print(f"[bold red]{error_msg}[/bold red]")
