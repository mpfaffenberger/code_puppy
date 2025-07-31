import configparser
import json
import os
import pathlib

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".code_puppy")
CONFIG_FILE = os.path.join(CONFIG_DIR, "puppy.cfg")
MCP_SERVERS_FILE = os.path.join(CONFIG_DIR, "mcp_servers.json")

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
                    "What's your name (so Code Puppy knows its master)? "
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


def get_message_history_limit():
    """
    Returns the user-configured message truncation limit (for remembering context),
    or 40 if unset or misconfigured.
    Configurable by 'message_history_limit' key.
    """
    val = get_value("message_history_limit")
    try:
        return max(1, int(val)) if val else 40
    except (ValueError, TypeError):
        return 40


# --- CONFIG SETTER STARTS HERE ---
def get_config_keys():
    """
    Returns the list of all config keys currently in puppy.cfg,
    plus certain preset expected keys (e.g. "yolo_mode", "model").
    """
    default_keys = ["yolo_mode", "model"]
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

    Falls back to the hard-coded default (``claude-4-0-sonnet``) if the file
    cannot be read for any reason or is empty.
    """
    global _default_model_cache

    # Return cached default if we have one
    if _default_model_cache is not None:
        return _default_model_cache

    try:
        # Local import to avoid potential circular dependency on module import
        from code_puppy.model_factory import ModelFactory

        models_config_path = os.path.join(CONFIG_DIR, "models.json")
        models_config = ModelFactory.load_config(models_config_path)
        first_key = next(iter(models_config))  # Raises StopIteration if empty
        _default_model_cache = first_key
        return first_key
    except Exception:
        # Any problem (network, file missing, empty dict, etc.) => fall back
        _default_model_cache = "claude-4-0-sonnet"
        return "claude-4-0-sonnet"


def _validate_model_exists(model_name: str) -> bool:
    """Check if a model exists in models.json with caching to avoid redundant calls."""
    global _model_validation_cache

    # Check cache first
    if model_name in _model_validation_cache:
        return _model_validation_cache[model_name]

    try:
        from code_puppy.model_factory import ModelFactory

        models_config_path = os.path.join(CONFIG_DIR, "models.json")
        models_config = ModelFactory.load_config(models_config_path)
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


def get_yolo_mode():
    """
    Checks puppy.cfg for 'yolo_mode' (case-insensitive in value only).
    Defaults to False if not set.
    Allowed values for ON: 1, '1', 'true', 'yes', 'on' (all case-insensitive for value).
    """
    true_vals = {"1", "true", "yes", "on"}
    cfg_val = get_value("yolo_mode")
    if cfg_val is not None:
        if str(cfg_val).strip().lower() in true_vals:
            return True
        return False
    return False
