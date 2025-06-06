import os
import configparser

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".code_puppy")
CONFIG_FILE = os.path.join(CONFIG_DIR, "puppy.cfg")

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
                val = input("What's your name (so Code Puppy knows its master)? ").strip()
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

# --- MODEL STICKY EXTENSION STARTS HERE ---
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
