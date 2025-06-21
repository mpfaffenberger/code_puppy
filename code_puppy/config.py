import configparser
import os
import json
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
    try:
        if not pathlib.Path(MCP_SERVERS_FILE).exists():
            print("No MCP configuration was found")
            return {}
        with open(MCP_SERVERS_FILE, "r") as f:
            conf = json.loads(f.read())
            return conf["mcp_servers"]
    except Exception as e:
        print(f"Failed to load MCP servers - {str(e)}")
        return {}

def get_model_name():
    """Returns the last used model name stored in config, or None if unset."""
    return get_value("model") or "gpt-4.1"


def set_model_name(model: str):
    """Sets the model name in the persistent config file."""
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if DEFAULT_SECTION not in config:
        config[DEFAULT_SECTION] = {}
    config[DEFAULT_SECTION]["model"] = model or ""
    with open(CONFIG_FILE, "w") as f:
        config.write(f)


def get_yolo_mode():
    """
    Checks puppy.cfg for 'yolo_mode' (case-insensitive in value only).
    If not set, checks YOLO_MODE env var:
    - If found in env, saves that value to puppy.cfg for future use.
    - If neither present, defaults to False.
    Allowed values for ON: 1, '1', 'true', 'yes', 'on' (all case-insensitive for value).
    Always prioritizes the config once set!
    """
    true_vals = {"1", "true", "yes", "on"}
    cfg_val = get_value("yolo_mode")
    if cfg_val is not None:
        if str(cfg_val).strip().lower() in true_vals:
            return True
        return False
    env_val = os.getenv("YOLO_MODE")
    if env_val is not None:
        # Persist the env value now
        set_config_value("yolo_mode", env_val)
        if str(env_val).strip().lower() in true_vals:
            return True
        return False
    return False
