import configparser
import datetime
import hashlib
import json
import logging
import os
import pathlib
from typing import Optional

from code_puppy.session_storage import save_session

logger = logging.getLogger(__name__)


def _get_xdg_dir(env_var: str, fallback: str) -> str:
    """
    Get directory for code_puppy files, defaulting to ~/.code_puppy.

    XDG paths are only used when the corresponding environment variable
    is explicitly set by the user. Otherwise, we use the legacy ~/.code_puppy
    directory for all file types (config, data, cache, state).

    Args:
        env_var: XDG environment variable name (e.g., "XDG_CONFIG_HOME")
        fallback: Fallback path relative to home (e.g., ".config") - unused unless XDG var is set

    Returns:
        Path to the directory for code_puppy files
    """
    # Use XDG directory ONLY if environment variable is explicitly set
    xdg_base = os.getenv(env_var)
    if xdg_base:
        return os.path.join(xdg_base, "code_puppy")

    # Default to legacy ~/.code_puppy for all file types
    return os.path.join(os.path.expanduser("~"), ".code_puppy")


# XDG Base Directory paths
CONFIG_DIR = _get_xdg_dir("XDG_CONFIG_HOME", ".config")
DATA_DIR = _get_xdg_dir("XDG_DATA_HOME", ".local/share")
CACHE_DIR = _get_xdg_dir("XDG_CACHE_HOME", ".cache")
STATE_DIR = _get_xdg_dir("XDG_STATE_HOME", ".local/state")

# Configuration files (XDG_CONFIG_HOME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "puppy.cfg")
MCP_SERVERS_FILE = os.path.join(CONFIG_DIR, "mcp_servers.json")

# Data files (XDG_DATA_HOME)
MODELS_FILE = os.path.join(DATA_DIR, "models.json")
EXTRA_MODELS_FILE = os.path.join(DATA_DIR, "extra_models.json")
AGENTS_DIR = os.path.join(DATA_DIR, "agents")
SKILLS_DIR = os.path.join(DATA_DIR, "skills")
CONTEXTS_DIR = os.path.join(DATA_DIR, "contexts")

# OAuth plugin model files (XDG_DATA_HOME)
GEMINI_MODELS_FILE = os.path.join(DATA_DIR, "gemini_models.json")
CHATGPT_MODELS_FILE = os.path.join(DATA_DIR, "chatgpt_models.json")
CLAUDE_MODELS_FILE = os.path.join(DATA_DIR, "claude_models.json")
COPILOT_MODELS_FILE = os.path.join(DATA_DIR, "copilot_models.json")

# Cache files (XDG_CACHE_HOME)
AUTOSAVE_DIR = os.path.join(CACHE_DIR, "autosaves")

# State files (XDG_STATE_HOME)
COMMAND_HISTORY_FILE = os.path.join(STATE_DIR, "command_history.txt")


def get_subagent_verbose() -> bool:
    """Return True if sub-agent verbose output is enabled (default False).

    When False (default), sub-agents produce quiet, sparse output suitable
    for parallel execution. When True, sub-agents produce full verbose output
    like the main agent (useful for debugging).
    """
    cfg_val = get_value("subagent_verbose")
    if cfg_val is None:
        return False
    return str(cfg_val).strip().lower() in {"1", "true", "yes", "on"}


# Pack agents - the specialized sub-agents coordinated by Pack Leader
PACK_AGENT_NAMES = frozenset(
    [
        "pack-leader",
        "bloodhound",
        "shepherd",
        "terrier",
        "watchdog",
        "retriever",
    ]
)

# Agents that require Universal Constructor to be enabled
UC_AGENT_NAMES = frozenset(["helios"])


def get_pack_agents_enabled() -> bool:
    """Return True if pack agents are enabled (default False).

    When False (default), pack agents (pack-leader, bloodhound, shepherd,
    terrier, watchdog, retriever) are hidden from `list_agents` tool and `/agents`
    command. They cannot be invoked by other agents or selected by users.

    When True, pack agents are available for use.
    """
    cfg_val = get_value("enable_pack_agents")
    if cfg_val is None:
        return False
    return str(cfg_val).strip().lower() in {"1", "true", "yes", "on"}


def get_universal_constructor_enabled() -> bool:
    """Return True if the Universal Constructor is enabled (default True).

    The Universal Constructor allows agents to dynamically create, manage,
    and execute custom tools at runtime. When enabled, agents can extend
    their capabilities by writing Python code that becomes callable tools.

    When False, the universal_constructor tool is not registered with agents.
    """
    cfg_val = get_value("enable_universal_constructor")
    if cfg_val is None:
        return True  # Enabled by default
    return str(cfg_val).strip().lower() in {"1", "true", "yes", "on"}


def set_universal_constructor_enabled(enabled: bool) -> None:
    """Enable or disable the Universal Constructor.

    Args:
        enabled: True to enable, False to disable
    """
    set_value("enable_universal_constructor", "true" if enabled else "false")


def get_mcp_unbound_warning_silenced() -> bool:
    """Return True if the 'MCP server registered but not bound' warning is silenced.

    When True, ``code_puppy.mcp_.manager._warn_unbound_servers`` skips emitting
    its consolidated warning. Default False — the warning exists for a reason
    (it surfaces hand-edits to ``mcp_servers.json`` that didn't get bound),
    but power users who *know* about the unbound servers can silence the
    nag via ``/mcp silence-warning``.
    """
    cfg_val = get_value("mcp_unbound_warning_silenced")
    if cfg_val is None:
        return False
    return str(cfg_val).strip().lower() in {"1", "true", "yes", "on"}


def set_mcp_unbound_warning_silenced(silenced: bool) -> None:
    """Silence (or un-silence) the unbound-MCP-server warning.

    Args:
        silenced: True to silence forever, False to restore the warning.
    """
    set_value("mcp_unbound_warning_silenced", "true" if silenced else "false")


def get_max_hook_retries() -> int:
    """Return the maximum number of plugin hook retries after an agent run.

    When a plugin hook returns ``{"retry": True, ...}`` the agent re-runs.
    This caps how many times that can happen to prevent runaway loops.
    Defaults to 3.
    """
    val = get_value("max_hook_retries")
    if val is None:
        return 3
    try:
        n = int(val)
        return max(1, n)  # At least 1 to avoid nonsensical values
    except (ValueError, TypeError):
        return 3


def get_enable_streaming() -> bool:
    """
    Get the enable_streaming configuration value.
    Controls whether streaming (SSE) is used for model responses.
    Returns True if streaming is enabled, False otherwise.
    Defaults to True.
    """
    val = get_value("enable_streaming")
    if val is None:
        return True  # Default to True for better UX
    return str(val).lower() in ("1", "true", "yes", "on")


def get_suppress_directory_listing() -> bool:
    """
    Get the suppress_directory_listing configuration value.
    Returns True if directory listing displays should be suppressed, False otherwise.
    """
    val = get_value("suppress_directory_listing")
    if val is None:
        return True  # Default to True (suppress by default)
    return str(val).lower() in ("1", "true", "yes", "on")


DEFAULT_SECTION = "puppy"
REQUIRED_KEYS = ["puppy_name", "owner_name"]

# Runtime-only autosave session ID (per-process)
_CURRENT_AUTOSAVE_ID: Optional[str] = None

# Session-local model name (initialized from file on first access, then cached)
_SESSION_MODEL: Optional[str] = None

# Cache containers for model validation and defaults
_model_validation_cache = {}
_default_model_cache = None
_default_vision_model_cache = None

# One-shot guard so we don't spam the "no model configured" warning on every
# call to get_global_model_name() (which happens a LOT).
_warned_no_model = False


def ensure_config_exists():
    """
    Ensure that XDG directories and puppy.cfg exist, prompting if needed.
    Returns configparser.ConfigParser for reading.
    """
    # Create all XDG directories with 0700 permissions per XDG spec
    for directory in [CONFIG_DIR, DATA_DIR, CACHE_DIR, STATE_DIR, SKILLS_DIR]:
        if not os.path.exists(directory):
            os.makedirs(directory, mode=0o700, exist_ok=True)
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
        # Note: Using sys.stdout here for initial setup before messaging system is available
        import sys

        sys.stdout.write("🐾 Let's get your Puppy ready!\n")
        sys.stdout.flush()
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

    # Set default values for important config keys if they don't exist
    if not config[DEFAULT_SECTION].get("auto_save_session"):
        config[DEFAULT_SECTION]["auto_save_session"] = "true"

    # Write the config if we made any changes
    if missing or not exists:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
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
        return True  # Default to True to allow recursion unless explicitly disabled
    return str(val).lower() in ("1", "true", "yes", "on")


def get_model_context_length() -> int:
    """
    Get the context length for the currently configured model from models.json
    """
    try:
        from code_puppy.model_factory import ModelFactory

        model_configs = ModelFactory.load_config()
        model_name = get_global_model_name()

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
        "summarization_model",
        "message_limit",
        "allow_recursion",
        "openai_reasoning_effort",
        "openai_reasoning_summary",
        "openai_verbosity",
        "auto_save_session",
        "max_saved_sessions",
        "http2",
        "diff_context_lines",
        "default_agent",
        "temperature",
        "frontend_emitter_enabled",
        "frontend_emitter_max_recent_events",
        "frontend_emitter_queue_size",
    ]
    # 'enable_dbos' is reserved for the dbos_durable_exec plugin and is read
    # via the generic get_value API; intentionally not in default_keys.
    # Add pack agents control key
    default_keys.append("enable_pack_agents")
    # Add universal constructor control key
    default_keys.append("enable_universal_constructor")
    # Add hook retry limit key
    default_keys.append("max_hook_retries")
    # Add streaming control key
    default_keys.append("enable_streaming")
    # Add suppress directory listing key
    default_keys.append("suppress_directory_listing")
    # Add cancel agent key configuration
    default_keys.append("cancel_agent_key")
    # Add max pause seconds configuration (used by event_stream_handler's
    # wait_if_paused() to auto-resume long pauses before SSE upstream
    # times out).
    default_keys.append("max_pause_seconds")
    # Add banner color keys
    for banner_name in DEFAULT_BANNER_COLORS:
        default_keys.append(f"banner_color_{banner_name}")
    # Add resume message count configuration
    default_keys.append("resume_message_count")
    # Per-file AGENTS.md character cap (see get_agents_md_max_chars()).
    default_keys.append("agents_md_max_chars")
    # Add /goal iteration cap (owned by the wiggum plugin, surfaced here so
    # /set autocompletes it). See plugins/wiggum/register_callbacks.py.
    default_keys.append("goal_max_iterations")
    # Add dangerous command guard disable (skips force push and destructive command guards)
    default_keys.append("disable_dangerous_command_guard")

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
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        config.write(f)


# Alias for API compatibility
def set_value(key: str, value: str) -> None:
    """Set a config value. Alias for set_config_value."""
    set_config_value(key, value)


def reset_value(key: str) -> None:
    """Remove a key from the config file, resetting it to default."""
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if DEFAULT_SECTION in config and key in config[DEFAULT_SECTION]:
        del config[DEFAULT_SECTION][key]
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            config.write(f)


# --- MODEL STICKY EXTENSION STARTS HERE ---
def load_mcp_server_configs():
    """
    Loads the MCP server configurations from XDG_CONFIG_HOME/code_puppy/mcp_servers.json.
    Returns a dict mapping names to their URL or config dict.
    If file does not exist, returns an empty dict.
    """
    from code_puppy.messaging.message_queue import emit_error

    try:
        if not pathlib.Path(MCP_SERVERS_FILE).exists():
            return {}
        with open(MCP_SERVERS_FILE, "r", encoding="utf-8") as f:
            conf = json.loads(f.read())
            return conf["mcp_servers"]
    except Exception as e:
        emit_error(f"Failed to load MCP servers - {str(e)}")
        return {}


def _default_model_from_models_json():
    """Load the default model name from the merged models config.

    Returns the first available model as the default, or ``None`` when no
    models are configured at all (e.g. empty ``models.json`` and no
    ``extra_models.json`` / OAuth model files). Returning ``None`` lets
    callers detect the "no model available" state and warn the user instead
    of silently pointing at a model that doesn't exist.
    """
    global _default_model_cache

    if _default_model_cache is not None:
        return _default_model_cache

    try:
        from code_puppy.model_factory import ModelFactory

        models_config = ModelFactory.load_config()
        if models_config:
            # Use first model in the merged config as default
            first_key = next(iter(models_config))
            _default_model_cache = first_key
            return first_key
    except Exception:
        pass

    # No models configured anywhere. Don't cache None so that adding a model
    # later (e.g. via /add_model) is picked up without a full cache clear.
    return None


def _default_vision_model_from_models_json() -> str:
    """Select a default vision-capable model from models.json with caching."""
    global _default_vision_model_cache

    if _default_vision_model_cache is not None:
        return _default_vision_model_cache

    try:
        from code_puppy.model_factory import ModelFactory

        models_config = ModelFactory.load_config()
        if models_config:
            # Prefer explicitly tagged vision models
            for name, config in models_config.items():
                if config.get("supports_vision"):
                    _default_vision_model_cache = name
                    return name

            # Fallback heuristic: common multimodal models
            preferred_candidates = (
                "gpt-4.1",
                "gpt-4.1-mini",
                "gpt-4.1-nano",
                "claude-4-0-sonnet",
                "gemini-2.5-flash-preview-05-20",
            )
            for candidate in preferred_candidates:
                if candidate in models_config:
                    _default_vision_model_cache = candidate
                    return candidate

            # Last resort: use the general default model
            _default_vision_model_cache = _default_model_from_models_json()
            return _default_vision_model_cache

        _default_vision_model_cache = "gpt-4.1"
        return "gpt-4.1"
    except Exception:
        _default_vision_model_cache = "gpt-4.1"
        return "gpt-4.1"


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
    global _model_validation_cache, _default_model_cache, _default_vision_model_cache
    global _warned_no_model
    _model_validation_cache.clear()
    _default_model_cache = None
    _default_vision_model_cache = None
    # Re-arm the "no model" warning so a fresh config state can warn again.
    _warned_no_model = False


def reset_session_model():
    """Reset the session-local model cache.

    This is primarily for testing purposes. In normal operation, the session
    model is set once at startup and only changes via set_model_name().
    """
    global _SESSION_MODEL
    _SESSION_MODEL = None


def model_supports_setting(model_name: str, setting: str) -> bool:
    """Check if a model supports a particular setting (e.g., 'temperature', 'seed').

    Args:
        model_name: The name of the model to check.
        setting: The setting name to check for (e.g., 'temperature', 'seed', 'top_p').

    Returns:
        True if the model supports the setting, False otherwise.
        Defaults to True for backwards compatibility if model config doesn't specify.
    """
    # GLM-4.5+ models support deep-thinking controls (thinking_type,
    # clear_thinking); GLM-5.2+ additionally support reasoning_effort.
    if setting in ("thinking_type", "clear_thinking"):
        from code_puppy.model_utils import supports_glm_thinking

        if supports_glm_thinking(model_name):
            return True
    if setting == "glm_reasoning_effort":
        from code_puppy.model_utils import supports_glm_reasoning_effort

        if supports_glm_reasoning_effort(model_name):
            return True

    try:
        from code_puppy.model_factory import ModelFactory

        models_config = ModelFactory.load_config()
        model_config = models_config.get(model_name, {})

        # Get supported_settings list, default to supporting common settings
        supported_settings = model_config.get("supported_settings")

        if supported_settings is None:
            # Default: assume common settings are supported for backwards compatibility
            # For Anthropic/Claude models, include extended thinking settings
            if model_name.startswith("claude-") or model_name.startswith("anthropic-"):
                base = ["temperature", "extended_thinking", "budget_tokens"]
                from code_puppy.model_utils import supports_adaptive_thinking

                if supports_adaptive_thinking(model_name):
                    base.append("effort")
                return setting in base
            return setting in ["temperature", "seed"]

        return setting in supported_settings
    except Exception:
        # If we can't check, assume supported for safety
        return True


def _warn_no_model_available() -> None:
    """Emit a one-time warning when no model is configured.

    Called from :func:`get_global_model_name` when neither the stored model,
    nor any bundled/extra/OAuth model is available. Guarded so we only nag the
    user once per process instead of on every single resolution.
    """
    global _warned_no_model
    if _warned_no_model:
        return
    _warned_no_model = True
    try:
        from code_puppy.messaging import emit_warning

        emit_warning(
            "\u26a0\ufe0f  No model is configured! Code Puppy can't talk to an LLM "
            "until you add one.\n"
            "   \u2022 Run /add_model to pick a model + API key, or\n"
            "   \u2022 Run /tutorial and choose Claude Code or ChatGPT OAuth."
        )
    except Exception:
        # Messaging may not be wired up yet (very early startup) - never crash.
        pass


def get_global_model_name():
    """Return the model name for Code Puppy to use, or ``None`` if unset.

    Uses session-local caching so that model changes in other terminals
    don't affect this running instance. The file is only read once at startup.

    1. If _SESSION_MODEL is set, return it (session cache)
    2. Otherwise, look at ``model`` in *puppy.cfg*
    3. If that value exists **and** is a known model, use it
    4. Otherwise return the first available model from the merged config
    5. If no model is available anywhere, warn once and return ``None``

    The result is cached in _SESSION_MODEL for subsequent calls.
    """
    global _SESSION_MODEL

    # Return cached session model if already initialized
    if _SESSION_MODEL is not None:
        return _SESSION_MODEL

    # First access - initialize from file
    stored_model = get_value("model")

    if stored_model:
        # Use cached validation to avoid hitting ModelFactory every time
        if _validate_model_exists(stored_model):
            _SESSION_MODEL = stored_model
            return _SESSION_MODEL

    # Either no stored model or it's not valid – choose default from the
    # merged models config.
    default_model = _default_model_from_models_json()
    if default_model is None:
        # Nothing available anywhere. Warn (once) and leave the session model
        # uninitialized so a later /add_model can take effect immediately.
        _warn_no_model_available()
        return None

    _SESSION_MODEL = default_model
    return _SESSION_MODEL


def set_model_name(model: str):
    """Sets the model name in both the session cache and persistent config file.

    Updates _SESSION_MODEL immediately for this process, and writes to the
    config file so new terminals will pick up this model as their default.
    """
    global _SESSION_MODEL

    # Update session cache immediately
    _SESSION_MODEL = model

    # Also persist to file for new terminal sessions
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if DEFAULT_SECTION not in config:
        config[DEFAULT_SECTION] = {}
    config[DEFAULT_SECTION]["model"] = model or ""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        config.write(f)

    # Clear model cache when switching models to ensure fresh validation
    clear_model_cache()


def get_summarization_model_name() -> str:
    """Return the model used for compaction/summarization.

    Reads the ``summarization_model`` config key. If unset (or empty),
    falls back to :func:`get_global_model_name`, preserving legacy behavior
    for users who haven't explicitly configured a separate summarizer.

    Rationale: summarization is a different workload than main-agent chat —
    it's one-shot, large-context, and best served by a cheap-and-fast or
    long-context specialist model. Decoupling it from the global model lets
    users pick the right tool without changing their main agent.
    """
    value = get_value("summarization_model")
    if value:
        return value
    return get_global_model_name()


def set_summarization_model_name(model: str) -> None:
    """Persist the summarization model in the config file.

    Pass an empty string to clear the setting and fall back to the global
    model on subsequent calls to :func:`get_summarization_model_name`.
    """
    set_config_value("summarization_model", model or "")


def get_puppy_token():
    """Returns the puppy_token from config, or None if not set."""
    return get_value("puppy_token")


def set_puppy_token(token: str):
    """Sets the puppy_token in the persistent config file."""
    set_config_value("puppy_token", token)


def get_openai_reasoning_effort() -> str:
    """Return the configured OpenAI reasoning effort (minimal, low, medium, high, xhigh)."""
    allowed_values = {"minimal", "low", "medium", "high", "xhigh"}
    configured = (get_value("openai_reasoning_effort") or "medium").strip().lower()
    if configured not in allowed_values:
        return "medium"
    return configured


def set_openai_reasoning_effort(value: str) -> None:
    """Persist the OpenAI reasoning effort ensuring it remains within allowed values."""
    allowed_values = {"minimal", "low", "medium", "high", "xhigh"}
    normalized = (value or "").strip().lower()
    if normalized not in allowed_values:
        raise ValueError(
            f"Invalid reasoning effort '{value}'. Allowed: {', '.join(sorted(allowed_values))}"
        )
    set_config_value("openai_reasoning_effort", normalized)


def get_openai_reasoning_summary() -> str:
    """Return the configured OpenAI reasoning summary mode.

    Supported values:
    - auto: let the provider decide the best summary style
    - concise: shorter reasoning summaries
    - detailed: fuller reasoning summaries
    """
    allowed_values = {"auto", "concise", "detailed"}
    configured = (get_value("openai_reasoning_summary") or "detailed").strip().lower()
    if configured not in allowed_values:
        return "auto"
    return configured


def set_openai_reasoning_summary(value: str) -> None:
    """Persist the OpenAI reasoning summary mode ensuring it remains valid."""
    allowed_values = {"auto", "concise", "detailed"}
    normalized = (value or "").strip().lower()
    if normalized not in allowed_values:
        raise ValueError(
            f"Invalid reasoning summary '{value}'. Allowed: {', '.join(sorted(allowed_values))}"
        )
    set_config_value("openai_reasoning_summary", normalized)


def get_openai_verbosity() -> str:
    """Return the configured OpenAI verbosity (low, medium, high).

    Controls how concise vs. verbose the model's responses are:
    - low: more concise responses
    - medium: balanced (default)
    - high: more verbose responses
    """
    allowed_values = {"low", "medium", "high"}
    configured = (get_value("openai_verbosity") or "medium").strip().lower()
    if configured not in allowed_values:
        return "medium"
    return configured


def set_openai_verbosity(value: str) -> None:
    """Persist the OpenAI verbosity ensuring it remains within allowed values."""
    allowed_values = {"low", "medium", "high"}
    normalized = (value or "").strip().lower()
    if normalized not in allowed_values:
        raise ValueError(
            f"Invalid verbosity '{value}'. Allowed: {', '.join(sorted(allowed_values))}"
        )
    set_config_value("openai_verbosity", normalized)


def get_temperature() -> Optional[float]:
    """Return the configured model temperature (0.0 to 2.0).

    Returns:
        Float between 0.0 and 2.0 if set, None if not configured.
        This allows each model to use its own default when not overridden.
    """
    val = get_value("temperature")
    if val is None or val.strip() == "":
        return None
    try:
        temp = float(val)
        # Clamp to valid range (most APIs accept 0-2)
        return max(0.0, min(2.0, temp))
    except (ValueError, TypeError):
        return None


def set_temperature(value: Optional[float]) -> None:
    """Set the global model temperature in config.

    Args:
        value: Temperature between 0.0 and 2.0, or None to clear.
               Lower values = more deterministic, higher = more creative.

    Note: Consider using set_model_setting() for per-model temperature.
    """
    if value is None:
        set_config_value("temperature", "")
    else:
        # Validate and clamp
        temp = max(0.0, min(2.0, float(value)))
        set_config_value("temperature", str(temp))


# --- PER-MODEL SETTINGS ---


def _sanitize_model_name_for_key(model_name: str) -> str:
    """Sanitize model name for use in config keys.

    Replaces characters that might cause issues in config keys.
    """
    # Replace problematic characters with underscores
    sanitized = model_name.replace(".", "_").replace("-", "_").replace("/", "_")
    return sanitized.lower()


def get_model_setting(
    model_name: str, setting: str, default: Optional[float] = None
) -> Optional[float]:
    """Get a specific setting for a model.

    Args:
        model_name: The model name (e.g., 'gpt-5', 'zai-glm-5.1-api')
        setting: The setting name (e.g., 'temperature', 'top_p', 'seed')
        default: Default value if not set

    Returns:
        The setting value as a float, or default if not set.
    """
    sanitized_name = _sanitize_model_name_for_key(model_name)
    key = f"model_settings_{sanitized_name}_{setting}"
    val = get_value(key)

    if val is None or val.strip() == "":
        return default

    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def set_model_setting(model_name: str, setting: str, value: Optional[float]) -> None:
    """Set a specific setting for a model.

    Args:
        model_name: The model name (e.g., 'gpt-5', 'zai-glm-5.1-api')
        setting: The setting name (e.g., 'temperature', 'seed')
        value: The value to set, or None to clear
    """
    sanitized_name = _sanitize_model_name_for_key(model_name)
    key = f"model_settings_{sanitized_name}_{setting}"

    if value is None:
        set_config_value(key, "")
    elif isinstance(value, float):
        # Round floats to nearest hundredth to avoid floating point weirdness
        # (allows 0.05 step increments for temperature/top_p)
        set_config_value(key, str(round(value, 2)))
    else:
        set_config_value(key, str(value))


def get_all_model_settings(model_name: str) -> dict:
    """Get all settings for a specific model.

    Args:
        model_name: The model name

    Returns:
        Dictionary of setting_name -> value for all configured settings.
    """
    import configparser

    sanitized_name = _sanitize_model_name_for_key(model_name)
    prefix = f"model_settings_{sanitized_name}_"

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    settings = {}
    if DEFAULT_SECTION in config:
        for key, val in config[DEFAULT_SECTION].items():
            if key.startswith(prefix) and val.strip():
                setting_name = key[len(prefix) :]
                # Handle different value types
                val_stripped = val.strip()
                # Check for boolean values first
                if val_stripped.lower() in ("true", "false"):
                    settings[setting_name] = val_stripped.lower() == "true"
                else:
                    # Try to parse as number (int first, then float)
                    try:
                        # Try int first for cleaner values like budget_tokens
                        if "." not in val_stripped:
                            settings[setting_name] = int(val_stripped)
                        else:
                            settings[setting_name] = float(val_stripped)
                    except (ValueError, TypeError):
                        # Keep as string if not a number
                        settings[setting_name] = val_stripped

    return settings


def clear_model_settings(model_name: str) -> None:
    """Clear all settings for a specific model.

    Args:
        model_name: The model name
    """
    import configparser

    sanitized_name = _sanitize_model_name_for_key(model_name)
    prefix = f"model_settings_{sanitized_name}_"

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    if DEFAULT_SECTION in config:
        keys_to_remove = [
            key for key in config[DEFAULT_SECTION] if key.startswith(prefix)
        ]
        for key in keys_to_remove:
            del config[DEFAULT_SECTION][key]

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            config.write(f)


def get_effective_model_settings(model_name: Optional[str] = None) -> dict:
    """Get all effective settings for a model, filtered by what the model supports.

    This is the generalized way to get model settings. It:
    1. Gets all per-model settings from config
    2. Falls back to global temperature if not set per-model
    3. Filters to only include settings the model actually supports
    4. Converts seed to int (other settings stay as float)

    Args:
        model_name: The model name. If None, uses the current global model.

    Returns:
        Dictionary of setting_name -> value for all applicable settings.
        Ready to be unpacked into ModelSettings.
    """
    if model_name is None:
        model_name = get_global_model_name()

    # Start with all per-model settings
    settings = get_all_model_settings(model_name)

    # Fall back to global temperature if not set per-model
    if "temperature" not in settings:
        global_temp = get_temperature()
        if global_temp is not None:
            settings["temperature"] = global_temp

    # Filter to only settings the model supports
    effective_settings = {}
    for setting_name, value in settings.items():
        if model_supports_setting(model_name, setting_name):
            # Convert seed to int, keep others as float
            if setting_name == "seed" and value is not None:
                effective_settings[setting_name] = int(value)
            else:
                effective_settings[setting_name] = value

    return effective_settings


# Legacy functions for backward compatibility
def get_effective_temperature(model_name: Optional[str] = None) -> Optional[float]:
    """Get the effective temperature for a model.

    Checks per-model settings first, then falls back to global temperature.

    Args:
        model_name: The model name. If None, uses the current global model.

    Returns:
        Temperature value, or None if not configured.
    """
    settings = get_effective_model_settings(model_name)
    return settings.get("temperature")


def get_effective_top_p(model_name: Optional[str] = None) -> Optional[float]:
    """Get the effective top_p for a model.

    Args:
        model_name: The model name. If None, uses the current global model.

    Returns:
        top_p value, or None if not configured.
    """
    settings = get_effective_model_settings(model_name)
    return settings.get("top_p")


def get_effective_seed(model_name: Optional[str] = None) -> Optional[int]:
    """Get the effective seed for a model.

    Args:
        model_name: The model name. If None, uses the current global model.

    Returns:
        seed value as int, or None if not configured.
    """
    settings = get_effective_model_settings(model_name)
    return settings.get("seed")


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
        # Read the entire file with encoding error handling for Windows
        with open(
            COMMAND_HISTORY_FILE, "r", encoding="utf-8", errors="surrogateescape"
        ) as f:
            content = f.read()

        # Sanitize any surrogate characters that might have slipped in
        try:
            content = content.encode("utf-8", errors="surrogatepass").decode(
                "utf-8", errors="replace"
            )
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass  # Keep original if sanitization fails

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
            import tempfile

            fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(COMMAND_HISTORY_FILE), suffix=".tmp"
            )
            try:
                with os.fdopen(
                    fd, "w", encoding="utf-8", errors="surrogateescape"
                ) as f:
                    f.write(updated_content)
                os.replace(tmp_path, COMMAND_HISTORY_FILE)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
    except Exception as e:
        from code_puppy.messaging import emit_error

        emit_error(
            f"An unexpected error occurred while normalizing command history: {str(e)}"
        )


def get_user_agents_directory() -> str:
    """Get the user's agents directory path.

    Returns:
        Path to the user's Code Puppy agents directory.
    """
    # Ensure the agents directory exists
    os.makedirs(AGENTS_DIR, exist_ok=True)
    return AGENTS_DIR


def get_project_agents_directory() -> Optional[str]:
    """Get the project-local agents directory path.

    Looks for a .code_puppy/agents/ directory in the current working directory.
    Unlike get_user_agents_directory(), this does NOT create the directory
    if it doesn't exist -- the team must create it intentionally.

    Returns:
        Path to the project's agents directory if it exists, or None.
    """
    project_agents_dir = os.path.join(os.getcwd(), ".code_puppy", "agents")
    if os.path.isdir(project_agents_dir):
        return project_agents_dir
    return None


def initialize_command_history_file():
    """Create the command history file if it doesn't exist.
    Handles migration from the old history file location for backward compatibility.
    Also normalizes the command history format if needed.
    """
    import os
    from pathlib import Path

    # Ensure the state directory exists before trying to create the history file
    if not os.path.exists(STATE_DIR):
        os.makedirs(STATE_DIR, exist_ok=True)

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
            from code_puppy.messaging import emit_error

            emit_error(
                f"An unexpected error occurred while trying to initialize history file: {str(e)}"
            )


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


def get_safety_permission_level():
    """
    Checks puppy.cfg for 'safety_permission_level' (case-insensitive in value only).
    Defaults to 'medium' if not set.
    Allowed values: 'none', 'low', 'medium', 'high', 'critical' (all case-insensitive for value).
    Returns the normalized lowercase string.
    """
    valid_levels = {"none", "low", "medium", "high", "critical"}
    cfg_val = get_value("safety_permission_level")
    if cfg_val is not None:
        normalized = str(cfg_val).strip().lower()
        if normalized in valid_levels:
            return normalized
    return "medium"  # Default to medium risk threshold


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


def get_grep_output_verbose():
    """
    Checks puppy.cfg for 'grep_output_verbose' (case-insensitive in value only).
    Defaults to False (concise output) if not set.
    Allowed values for ON: 1, '1', 'true', 'yes', 'on' (all case-insensitive for value).

    When False (default): Shows only file names with match counts
    When True: Shows full output with line numbers and content
    """
    true_vals = {"1", "true", "yes", "on"}
    cfg_val = get_value("grep_output_verbose")
    if cfg_val is not None:
        if str(cfg_val).strip().lower() in true_vals:
            return True
        return False
    return False


def get_disable_dangerous_command_guard() -> bool:
    """
    Checks puppy.cfg for 'disable_dangerous_command_guard' (case-insensitive in value only).
    Defaults to False (guards enabled) if not set.
    Allowed values for ON: 1, '1', 'true', 'yes', 'on' (all case-insensitive for value).

    When False (default): Both force push guard and destructive command guard are active.
    When True: Both guards are bypassed - commands execute without prompts.

      Use with caution!

    This setting disables:
    - Force push guard (git push --force, git push -f, etc.)
    - Destructive command guard (rm -rf, docker system prune, etc.)
    """
    true_vals = {"1", "true", "yes", "on"}
    cfg_val = get_value("disable_dangerous_command_guard")
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


def get_resume_message_count() -> int:
    """
    Returns the number of messages to display when resuming a session.
    Defaults to 50 if unset or misconfigured.
    Configurable by 'resume_message_count' key via /set command.

    Example: /set resume_message_count=30
    """
    val = get_value("resume_message_count")
    try:
        configured_value = int(val) if val else 50
        # Enforce reasonable bounds: minimum 0 (disabled), maximum 100
        return max(0, min(configured_value, 100))
    except (ValueError, TypeError):
        return 50


# Default cap (in characters) for any single AGENTS.md file injected into
# the system prompt. Users can override this via
# ``/set agents_md_max_chars=<int>`` — any positive integer is honoured so
# models with very large context windows (1M+ tokens) can opt into bigger
# AGENTS.md files when it makes sense. The default of 10,000 just keeps
# the unbounded out-of-the-box behaviour from regressing.
AGENTS_MD_MAX_CHARS_DEFAULT = 10_000


def get_agents_md_max_chars() -> int:
    """Return the per-file AGENTS.md character cap, honouring user override.

    Read from the ``agents_md_max_chars`` config key (settable via
    ``/set agents_md_max_chars=<int>``). Defaults to
    ``AGENTS_MD_MAX_CHARS_DEFAULT`` (10,000) when unset, and falls back to
    the default on values that can't be a sensible cap (non-numeric,
    negative, zero). No upper clamp — if a user with a 1M-token model
    wants ``/set agents_md_max_chars=500000``, that's their call.
    """
    val = get_value("agents_md_max_chars")
    try:
        configured = int(val) if val else AGENTS_MD_MAX_CHARS_DEFAULT
    except (ValueError, TypeError):
        return AGENTS_MD_MAX_CHARS_DEFAULT
    if configured <= 0:
        return AGENTS_MD_MAX_CHARS_DEFAULT
    return configured


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
        return max(0.5, min(0.95, threshold))
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


def get_http2() -> bool:
    """
    Get the http2 configuration value.
    Returns False if not set (default).
    """
    val = get_value("http2")
    if val is None:
        return False
    return str(val).lower() in ("1", "true", "yes", "on")


def set_http2(enabled: bool) -> None:
    """
    Sets the http2 configuration value.

    Args:
        enabled: Whether to enable HTTP/2 for httpx clients
    """
    set_config_value("http2", "true" if enabled else "false")


def get_message_limit(default: int = 1000) -> int:
    """
    Returns the user-configured message/request limit for the agent.
    This controls how many steps/requests the agent can take.
    Defaults to 1000 if unset or misconfigured.
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

        # Sanitize command to remove any invalid surrogate characters
        # that could cause encoding errors on Windows
        try:
            command = command.encode("utf-8", errors="surrogatepass").decode(
                "utf-8", errors="replace"
            )
        except (UnicodeEncodeError, UnicodeDecodeError):
            # If that fails, do a more aggressive cleanup
            command = "".join(
                char if ord(char) < 0xD800 or ord(char) > 0xDFFF else "\ufffd"
                for char in command
            )

        with open(
            COMMAND_HISTORY_FILE, "a", encoding="utf-8", errors="surrogateescape"
        ) as f:
            f.write(f"\n# {timestamp}\n{command}\n")
    except Exception as e:
        from code_puppy.messaging import emit_error

        emit_error(
            f"An unexpected error occurred while saving command history: {str(e)}"
        )


def get_agent_pinned_model(agent_name: str) -> str:
    """Get the pinned model for a specific agent.

    Args:
        agent_name: Name of the agent to get the pinned model for.

    Returns:
        Pinned model name, or None if no model is pinned for this agent.
    """
    return get_value(f"agent_model_{agent_name}")


def set_agent_pinned_model(agent_name: str, model_name: str):
    """Set the pinned model for a specific agent.

    Args:
        agent_name: Name of the agent to pin the model for.
        model_name: Model name to pin to this agent.
    """
    set_config_value(f"agent_model_{agent_name}", model_name)


def clear_agent_pinned_model(agent_name: str):
    """Clear the pinned model for a specific agent.

    Args:
        agent_name: Name of the agent to clear the pinned model for.
    """
    # We can't easily delete keys from configparser, so set to empty string
    # which will be treated as None by get_agent_pinned_model
    set_config_value(f"agent_model_{agent_name}", "")


def get_all_agent_pinned_models() -> dict:
    """Get all agent-to-model pinnings from config.

    Returns:
        Dict mapping agent names to their pinned model names.
        Only includes agents that have a pinned model (non-empty value).
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    pinnings = {}
    if DEFAULT_SECTION in config:
        for key, value in config[DEFAULT_SECTION].items():
            if key.startswith("agent_model_") and value:
                agent_name = key[len("agent_model_") :]
                pinnings[agent_name] = value
    return pinnings


def get_agents_pinned_to_model(model_name: str) -> list:
    """Get all agents that are pinned to a specific model.

    Args:
        model_name: The model name to look up.

    Returns:
        List of agent names pinned to this model.
    """
    all_pinnings = get_all_agent_pinned_models()
    return [agent for agent, model in all_pinnings.items() if model == model_name]


def get_auto_save_session() -> bool:
    """
    Checks puppy.cfg for 'auto_save_session' (case-insensitive in value only).
    Defaults to True if not set.
    Allowed values for ON: 1, '1', 'true', 'yes', 'on' (all case-insensitive for value).
    """
    true_vals = {"1", "true", "yes", "on"}
    cfg_val = get_value("auto_save_session")
    if cfg_val is not None:
        if str(cfg_val).strip().lower() in true_vals:
            return True
        return False
    return True


def set_auto_save_session(enabled: bool):
    """Sets the auto_save_session configuration value.

    Args:
        enabled: Whether to enable auto-saving of sessions
    """
    set_config_value("auto_save_session", "true" if enabled else "false")


def get_max_saved_sessions() -> int:
    """
    Gets the maximum number of sessions to keep.
    Defaults to 20 if not set.
    """
    cfg_val = get_value("max_saved_sessions")
    if cfg_val is not None:
        try:
            val = int(cfg_val)
            return max(0, val)  # Ensure non-negative
        except (ValueError, TypeError):
            pass
    return 20


def set_max_saved_sessions(max_sessions: int):
    """Sets the max_saved_sessions configuration value.

    Args:
        max_sessions: Maximum number of sessions to keep (0 for unlimited)
    """
    set_config_value("max_saved_sessions", str(max_sessions))


def set_diff_highlight_style(style: str):
    """Set the diff highlight style.

    Note: Text mode has been removed. This function is kept for backwards compatibility
    but does nothing. All diffs use beautiful syntax highlighting now!

    Args:
        style: Ignored (always uses 'highlight' mode)
    """
    # Do nothing - we always use highlight mode now!
    pass


# Defaults for diff highlight colors — single source of truth.
_DEFAULT_DIFF_ADDITION_HEX = "#0b1f0b"  # darker green
_DEFAULT_DIFF_DELETION_HEX = "#390e1a"  # wine


def _coerce_to_hex(value: Optional[str], fallback: str) -> str:
    """Normalize any color string to '#RRGGBB'.

    Accepts:
      - '#RRGGBB' hex strings (any case) — returned lowercased.
      - Rich color names like 'green', 'orange1', 'bright_red'.
      - 'rgb(r,g,b)' forms that Rich understands.

    Anything Rich can't parse (including None/empty) falls back to ``fallback``.
    This keeps downstream consumers like ``brighten_hex`` happy — they only
    ever see a well-formed #RRGGBB string.
    """
    if not value:
        return fallback
    candidate = value.strip()
    # Fast-path: already a valid #RRGGBB.
    if (
        len(candidate) == 7
        and candidate.startswith("#")
        and all(c in "0123456789abcdefABCDEF" for c in candidate[1:])
    ):
        return candidate.lower()
    # Otherwise try Rich's parser (handles named colors, rgb(), etc.).
    try:
        from rich.color import Color  # local import keeps module import cheap

        triplet = Color.parse(candidate).get_truecolor()
        return f"#{triplet.red:02x}{triplet.green:02x}{triplet.blue:02x}"
    except Exception:
        return fallback


def get_diff_addition_color() -> str:
    """Get the base color for diff additions, always as a valid '#RRGGBB' hex.

    Falls back to the default darker green if the configured value is missing
    or unparseable.
    """
    return _coerce_to_hex(
        get_value("highlight_addition_color"), _DEFAULT_DIFF_ADDITION_HEX
    )


def set_diff_addition_color(color: str):
    """Set the color for diff additions.

    Accepts '#RRGGBB' hex, Rich color names ('green', 'bright_green', ...), or
    'rgb(r,g,b)'. The value is normalized to '#RRGGBB' before being written so
    downstream renderers never see a raw name.
    """
    set_config_value(
        "highlight_addition_color",
        _coerce_to_hex(color, _DEFAULT_DIFF_ADDITION_HEX),
    )


def get_diff_deletion_color() -> str:
    """Get the base color for diff deletions, always as a valid '#RRGGBB' hex.

    Falls back to the default wine if the configured value is missing or
    unparseable.
    """
    return _coerce_to_hex(
        get_value("highlight_deletion_color"), _DEFAULT_DIFF_DELETION_HEX
    )


def set_diff_deletion_color(color: str):
    """Set the color for diff deletions.

    Accepts '#RRGGBB' hex, Rich color names ('red', 'orange1', ...), or
    'rgb(r,g,b)'. The value is normalized to '#RRGGBB' before being written so
    downstream renderers never see a raw name.
    """
    set_config_value(
        "highlight_deletion_color",
        _coerce_to_hex(color, _DEFAULT_DIFF_DELETION_HEX),
    )


# =============================================================================
# Banner Color Configuration
# =============================================================================

# Default banner colors (Rich color names)
# A beautiful jewel-tone palette with semantic meaning:
#   - Blues/Teals: Reading & navigation (calm, informational)
#   - Warm tones: Actions & changes (edits, shell commands)
#   - Purples: AI thinking & reasoning (the "brain" colors)
#   - Greens: Completions & success
#   - Neutrals: Search & listings
DEFAULT_BANNER_COLORS = {
    "thinking": "deep_sky_blue4",  # Sapphire - contemplation
    "agent_response": "medium_purple4",  # Amethyst - main AI output
    "shell_command": "dark_orange3",  # Amber - system commands
    "read_file": "steel_blue",  # Steel - reading files
    "edit_file": "dark_goldenrod",  # Gold - modifications (legacy)
    "create_file": "dark_goldenrod",  # Gold - file creation
    "replace_in_file": "dark_goldenrod",  # Gold - file modifications
    "delete_snippet": "dark_goldenrod",  # Gold - snippet removal
    "grep": "grey37",  # Silver - search results
    "directory_listing": "dodger_blue2",  # Sky - navigation
    "agent_reasoning": "dark_violet",  # Violet - deep thought
    "invoke_agent": "deep_pink4",  # Ruby - agent invocation
    "subagent_response": "sea_green3",  # Emerald - sub-agent success
    "list_agents": "dark_slate_gray3",  # Slate - neutral listing
    "universal_constructor": "dark_cyan",  # Teal - constructing tools
    # Browser/Terminal tools - same color as edit_file (gold)
    "terminal_tool": "dark_goldenrod",  # Gold - browser terminal operations
    # MCP tools - distinct from builtin tools
    "mcp_tool_call": "dark_cyan",  # Teal - external MCP tool calls
    # User-initiated shell pass-through (! prefix) - distinct from agent's shell_command
    "shell_passthrough": "medium_sea_green",  # Green - user's own shell commands
    # LLM Judge - goal-mode verdict (distinct from agent reasoning)
    "llm_judge": "gold3",  # Gold - judicial authority / gavel
    # Transcript echo of the user's submitted prompt (persistent prompt path)
    "user_prompt": "dark_green",  # Green - the human speaks
}


def get_banner_color(banner_name: str) -> str:
    """Get the background color for a specific banner.

    Args:
        banner_name: The banner identifier (e.g., 'thinking', 'agent_response')

    Returns:
        Rich color name or hex code for the banner background
    """
    config_key = f"banner_color_{banner_name}"
    val = get_value(config_key)
    if val:
        return val
    return DEFAULT_BANNER_COLORS.get(banner_name, "blue")


def set_banner_color(banner_name: str, color: str):
    """Set the background color for a specific banner.

    Args:
        banner_name: The banner identifier (e.g., 'thinking', 'agent_response')
        color: Rich color name or hex code
    """
    config_key = f"banner_color_{banner_name}"
    set_config_value(config_key, color)


def get_all_banner_colors() -> dict:
    """Get all banner colors (configured or default).

    Returns:
        Dict mapping banner names to their colors
    """
    return {name: get_banner_color(name) for name in DEFAULT_BANNER_COLORS}


def reset_banner_color(banner_name: str):
    """Reset a banner color to its default.

    Args:
        banner_name: The banner identifier to reset
    """
    default_color = DEFAULT_BANNER_COLORS.get(banner_name, "blue")
    set_banner_color(banner_name, default_color)


def reset_all_banner_colors():
    """Reset all banner colors to their defaults."""
    for name, color in DEFAULT_BANNER_COLORS.items():
        set_banner_color(name, color)


def get_current_session_name() -> str:
    """Return the full filename of the session this process is writing to.

    On first call, lazily mints a fresh auto-flavored name
    (``auto_session_<YYYYMMDD>_<HHMMSS>``). Subsequent calls return the
    same string until ``rotate_session_name`` or ``pin_current_session_name``
    is called.

    The ``auto_session_`` prefix is RESERVED for system-generated names;
    user-input names cannot start with it (enforced by
    ``session_lifecycle.is_valid_session_name``).

    This replaces the pre-unification dance of ``get_current_autosave_id`` +
    runtime ``f"auto_session_{id}"`` construction, which silently broke
    named-session save-back the moment a user-named string was pinned.
    """
    global _CURRENT_AUTOSAVE_ID
    if not _CURRENT_AUTOSAVE_ID:
        _CURRENT_AUTOSAVE_ID = (
            f"auto_session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
    return _CURRENT_AUTOSAVE_ID


def rotate_session_name() -> str:
    """Reset the singleton; next read mints a fresh auto-flavored name.

    Used by ``/clear`` and ``/switch-agent`` to start a new session
    regardless of whether the previous one was auto- or user-named.
    """
    global _CURRENT_AUTOSAVE_ID
    _CURRENT_AUTOSAVE_ID = ""
    return get_current_session_name()


def pin_current_session_name(name: str) -> str:
    """Pin the session to a specific filename. NO transformation.

    Validates defensively against the stored-name rules so a forgetful
    caller cannot smuggle a path-traversal name into the singleton and have
    the next autosave write it to ``AUTOSAVE_DIR / "../../etc/passwd"``.
    Raises ``ValueError`` on invalid input.

    Callers that already validated (resolver, ``/load_context``) treat the
    raise as a "shouldn't happen" guard.
    """
    from code_puppy.session_lifecycle import is_valid_session_name

    if not is_valid_session_name(name, allow_reserved_prefix=True):
        raise ValueError(f"invalid session name: {name!r}")
    global _CURRENT_AUTOSAVE_ID
    _CURRENT_AUTOSAVE_ID = name
    return _CURRENT_AUTOSAVE_ID


# ----- Deprecated aliases (the unified-autosave migration) ---------------------------------
#
# The pre-unification API stored a bare ID in the singleton and synthesized
# ``auto_session_<id>`` on every read. That scheme broke the moment a
# user-named string (e.g. ``"mywork"``) was pinned: the next read produced
# ``"auto_session_mywork"`` and named-session save-back wrote the wrong file.
#
# These aliases preserve external plugin compatibility for ONE release. Every
# internal caller in this PR has been migrated to the new API; the aliases
# never fire from in-repo code (otherwise ``-W error`` test runs would fail
# and every startup would spam ``DeprecationWarning`` in user terminals).


def get_current_autosave_id() -> str:
    """DEPRECATED: use ``get_current_session_name()``.

    Returns the current session name with any ``auto_session_`` prefix
    stripped (matches the pre-unification return shape). For user-named
    sessions, returns the name verbatim.

    .. note::
       External callers that wrote
       ``f"auto_session_{get_current_autosave_id()}"`` to reconstruct a
       filename USED to be correct (the singleton always held a bare ID);
       after the unified-autosave migration the singleton can hold a user-named string like
       ``"mywork"``, in which case the reconstruction produces
       ``"auto_session_mywork"`` -- a WRONG filename. Switch to
       ``get_current_session_name()``.
    """
    import warnings

    warnings.warn(
        "get_current_autosave_id is deprecated; use get_current_session_name",
        DeprecationWarning,
        stacklevel=2,
    )
    name = get_current_session_name()
    prefix = "auto_session_"
    if name.startswith(prefix):
        return name[len(prefix) :]
    return name


def rotate_autosave_id() -> str:
    """DEPRECATED: use ``rotate_session_name()``.

    Returns the rotated name with any ``auto_session_`` prefix stripped,
    matching the pre-unification return shape. Internally always returns
    an auto-flavored name (rotate ALWAYS mints fresh), so the strip is a
    pure shape-preservation transformation.
    """
    import warnings

    warnings.warn(
        "rotate_autosave_id is deprecated; use rotate_session_name",
        DeprecationWarning,
        stacklevel=2,
    )
    name = rotate_session_name()
    prefix = "auto_session_"
    if name.startswith(prefix):
        return name[len(prefix) :]
    return name


def get_current_autosave_session_name() -> str:
    """DEPRECATED: use ``get_current_session_name()``.

    Returns the full stored name VERBATIM. NOT re-synthesized from a stripped
    ID -- doing so would produce ``"auto_session_mywork"`` for a user-named
    session and break TTY-keyed cross-restart resume.
    """
    import warnings

    warnings.warn(
        "get_current_autosave_session_name is deprecated; use get_current_session_name",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_current_session_name()


def set_current_autosave_from_session_name(session_name: str) -> str:
    """DEPRECATED: use ``pin_current_session_name(name)``.

    Behavior change vs. pre-unification: the old function stripped an
    ``auto_session_`` prefix on input. The new contract does NOT strip --
    the singleton holds the full filename verbatim. Callers that passed
    ``"auto_session_xyz"`` expecting the singleton to end up as ``"xyz"``
    (no in-repo callers do this) would now see ``"auto_session_xyz"`` in
    the singleton.

    Also: because ``pin_current_session_name`` validates input, this alias
    now raises ``ValueError`` for names that pre-unification it would have
    silently accepted (control chars, empty string, path-separator chars).
    """
    import warnings

    warnings.warn(
        "set_current_autosave_from_session_name is deprecated; "
        "use pin_current_session_name",
        DeprecationWarning,
        stacklevel=2,
    )
    return pin_current_session_name(session_name)


def auto_save_session_if_enabled() -> bool:
    """Automatically save the current session if auto_save_session is enabled."""
    if not get_auto_save_session():
        return False

    try:
        import pathlib

        from code_puppy.agents.agent_manager import get_current_agent
        from code_puppy.messaging import emit_info

        current_agent = get_current_agent()
        history = current_agent.get_message_history()
        if not history:
            return False

        now = datetime.datetime.now()
        session_name = get_current_session_name()
        autosave_dir = pathlib.Path(AUTOSAVE_DIR)

        metadata = save_session(
            history=history,
            session_name=session_name,
            base_dir=autosave_dir,
            timestamp=now.isoformat(),
            token_estimator=current_agent.estimate_tokens_for_message,
            auto_saved=True,
        )

        # Point quick-resume at this just-saved session. Every turn, exit, and
        # finalize routes through this single autosave chokepoint, so cwd and
        # any tool-observed child workspaces always map to a loadable pickle.
        # Best-effort: never let pointer bookkeeping block the autosave.
        record_quick_resume_sessions(session_name)

        # Append conversation-wide TTFT + TG averages if we have any data.
        stats_suffix = ""
        try:
            from code_puppy.agents.run_stats import AgentRunStats

            avg_ttft, avg_gen = AgentRunStats.get_conversation_stats()
            formatted = AgentRunStats.format_conversation_stats(avg_ttft, avg_gen)
            if formatted:
                stats_suffix = f" | {formatted}"
        except Exception:
            # Stats are decorative; never block the auto-save line on them.
            pass

        emit_info(
            f"\U0001f43e Auto-saved session: {metadata.message_count} messages "
            f"({metadata.total_tokens} tokens){stats_suffix}"
        )

        # Fire post_autosave so plugins can render follow-up lines
        # (token quota, etc.) without us knowing about them here.
        # Delegates to the shared lifecycle helper -- see its docstring for
        # why an executor wrap is needed and where to add disk-level
        # forensics if we ever want them across all callers.
        from code_puppy.session_lifecycle import fire_post_autosave_callback

        fire_post_autosave_callback(metadata)

        return True

    except Exception as exc:  # pragma: no cover - defensive logging
        from code_puppy.messaging import emit_error

        emit_error(f"Failed to auto-save session: {exc}")
        return False


def get_diff_context_lines() -> int:
    """
    Returns the user-configured number of context lines for diff display.
    This controls how many lines of surrounding context are shown in diffs.
    Defaults to 6 if unset or misconfigured.
    Configurable by 'diff_context_lines' key.
    """
    val = get_value("diff_context_lines")
    try:
        context_lines = int(val) if val else 6
        # Apply reasonable bounds: minimum 0, maximum 50
        return max(0, min(context_lines, 50))
    except (ValueError, TypeError):
        return 6


def get_terminal_tty() -> Optional[str]:
    """Return the TTY device path for stdin, or None if unavailable.

    This identifies the physical terminal so /switch-agent can resume the
    last autosave session from the same terminal window across restarts.
    """
    try:
        import sys

        return os.ttyname(sys.stdin.fileno())
    except (OSError, AttributeError, ValueError):
        return None


def _is_valid_autosave_session_name(session_name: str) -> bool:
    """Return True when a terminal marker names a safe stored session.

    Accepts both auto-flavored entries (``auto_session_<YYYYMMDD>_<HHMMSS>``)
    AND user-named entries (any slug matching
    ``session_lifecycle.is_valid_session_name(..., allow_reserved_prefix=True)``).
    Without this, TTY-keyed cross-restart resume would silently reject every
    user-named session.

    The name kept the ``_autosave_`` prefix for backward compatibility with
    external callers; conceptually it's a stored-name validator now.
    """
    from code_puppy.session_lifecycle import is_valid_session_name

    return is_valid_session_name(session_name, allow_reserved_prefix=True)


def _tty_session_path(tty: str) -> pathlib.Path:
    """Return the per-TTY autosave session file path."""
    tty_key = tty.replace("/", "_").lstrip("_")
    return pathlib.Path(CACHE_DIR) / "tty_sessions" / f"{tty_key}.txt"


def record_terminal_session(session_name: str, *, overwrite: bool = True) -> None:
    """Persist the current autosave session name for this terminal.

    Uses a dedicated file per TTY so concurrent terminals never clobber each
    other. Terminal emulators usually assign a fresh TTY per window/tab, and TTY
    reassignment while Code Puppy is running is rare, but possible after a
    terminal closes and the OS later reuses the device name. This mapping is
    therefore best-effort and silently no-ops when no TTY is available or when
    filesystem writes fail. Set ``overwrite=False`` for startup markers so a
    previous real session survives until a new session is saved.
    """
    tty = get_terminal_tty()
    if not tty:
        return
    try:
        session_file = _tty_session_path(tty)
        if session_file.exists() and not overwrite:
            return
        session_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = session_file.with_suffix(".tmp")
        tmp.write_text(session_name, encoding="utf-8")
        tmp.replace(session_file)
    except Exception:
        pass


def get_last_terminal_session() -> Optional[str]:
    """Return the last autosave session recorded for this terminal."""
    tty = get_terminal_tty()
    if not tty:
        return None
    try:
        session_name = _tty_session_path(tty).read_text(encoding="utf-8").strip()
        if not session_name or not _is_valid_autosave_session_name(session_name):
            return None
        return session_name
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Quick-resume: resume the latest autosave for a directory + git branch.
#
# Unlike terminal sessions (keyed by TTY, which is POSIX-only), quick-resume is
# keyed by canonical workspace + branch, so it works identically on Windows and
# macOS/Linux. All filesystem access goes through ``os.path``/``pathlib`` and
# git is probed via subprocess with failures swallowed, so a missing git or a
# non-repo directory degrades gracefully rather than raising.
# --------------------------------------------------------------------------- #

# Child workspaces touched by tools this run; flushed to pointers on next save.
_OBSERVED_QUICK_RESUME_KEYS: set[str] = set()


def format_quick_resume_scope(cwd: str, branch: Optional[str]) -> str:
    """Return a non-sensitive scope label for diagnostics (no raw paths)."""
    scope_id = hashlib.sha1(
        f"{cwd}\x00{branch or ''}".encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:12]
    branch_label = "detected" if branch else "null"
    return f"scope: {scope_id} | branch: {branch_label}"


def _quick_resume_key(cwd: str, branch: Optional[str]) -> str:
    """Return the stable pointer key for a workspace + branch (NUL-separated)."""
    return f"{cwd}\x00{branch or ''}"


def _absolute_quick_resume_path(target_path: Optional[str]) -> str:
    """Normalize a target into an absolute, user-expanded path (cwd if None)."""
    raw_path = os.getcwd() if target_path is None else str(target_path).strip()
    if not raw_path:
        raw_path = os.getcwd()
    expanded = os.path.expanduser(raw_path)
    if not os.path.isabs(expanded):
        expanded = os.path.join(os.getcwd(), expanded)
    return os.path.abspath(expanded)


def _candidate_scope_dir(target_path: Optional[str], path_kind: str) -> str:
    """Return the directory to probe for scope.

    ``path_kind='file'`` probes the path's parent dir; ``'directory'`` uses it
    as-is; ``'auto'`` checks the filesystem so ``-qr some_file.py`` still works.
    """
    candidate = _absolute_quick_resume_path(target_path)
    if path_kind == "file":
        return os.path.dirname(candidate) or candidate
    if path_kind == "directory":
        return candidate
    if os.path.isfile(candidate):
        return os.path.dirname(candidate) or candidate
    return candidate


def _nearest_existing_directory(path: str) -> Optional[str]:
    """Walk up from ``path`` to the first directory that exists, or None."""
    current = pathlib.Path(path)
    while True:
        try:
            if current.is_dir():
                return str(current)
        except OSError:
            return None
        if current.parent == current:  # reached filesystem root
            return None
        current = current.parent


def _detect_git_toplevel(path: str) -> Optional[str]:
    """Return the git worktree root for ``path``, or None outside git.

    Uses ``git rev-parse --show-toplevel`` (handles nested repos, submodules,
    and worktrees). Cross-platform; returns None if git is missing or fails.
    """
    probe_dir = _nearest_existing_directory(path)
    if not probe_dir:
        return None
    try:
        import subprocess

        out = subprocess.run(
            ["git", "-C", probe_dir, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        if out.returncode == 0:
            root = out.stdout.strip()
            return os.path.realpath(root) if root else None
    except Exception:
        return None
    return None


def _first_child_under_cwd(path: str) -> Optional[str]:
    """Return the first path component of ``path`` under cwd, else None.

    Lets a no-git ``-qr ./ticket/src/foo`` collapse to the ``ticket`` workspace
    instead of scattering pointers across deep subdirectories.
    """
    base = os.path.realpath(os.getcwd())
    target = os.path.realpath(path)
    if target == base:
        return None
    try:
        rel = os.path.relpath(target, base)
    except ValueError:  # different drive on Windows -> not under cwd
        return None
    parts = pathlib.Path(rel).parts
    if not parts or parts[0] in (".", ".."):
        return None
    return os.path.realpath(os.path.join(base, parts[0]))


def _fallback_scope_dir(candidate_dir: str, target_path: Optional[str]) -> str:
    """Return the non-git scope: cwd itself, or the first child for explicit paths."""
    if target_path is None:
        return os.path.realpath(candidate_dir)
    return _first_child_under_cwd(candidate_dir) or os.path.realpath(candidate_dir)


def get_quick_resume_location(
    target_path: Optional[str] = None, *, path_kind: str = "auto"
) -> tuple[str, Optional[str]]:
    """Return ``(canonical_workspace, branch_or_None)`` for a quick-resume scope.

    The canonical workspace is the nearest git worktree root when available,
    else a directory-only fallback. This is the single source of truth shared by
    the pointer key and the diagnostic label, so they can never drift.
    """
    candidate_dir = _candidate_scope_dir(target_path, path_kind)
    git_root = _detect_git_toplevel(candidate_dir)
    cwd = git_root or _fallback_scope_dir(candidate_dir, target_path)
    branch: Optional[str] = None
    if git_root:
        try:
            from code_puppy.plugins.statusline.payload import detect_git_branch

            branch = detect_git_branch(cwd)
        except Exception:
            branch = None
    return os.path.realpath(cwd), branch


def _dir_branch_key_for_path(
    target_path: Optional[str] = None, *, path_kind: str = "auto"
) -> str:
    """Return the pointer key for a target's canonical workspace + branch."""
    cwd, branch = get_quick_resume_location(target_path, path_kind=path_kind)
    return _quick_resume_key(cwd, branch)


def _dir_session_path(key: str) -> pathlib.Path:
    """Return the pointer file path for a workspace+branch key.

    The key is hashed so the filename is a short, filesystem-safe hex string on
    every OS (sidesteps Windows path-length/charset rules regardless of how long
    or exotic the directory or branch name is). SHA-1 truncated to 16 hex chars
    is a cache-pointer key, never a security signature -- ``usedforsecurity``
    flags that intent for scanners.
    """
    digest = hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return pathlib.Path(CACHE_DIR) / "dir_sessions" / f"{digest}.txt"


def _record_directory_session_key(session_name: str, key: str) -> None:
    """Atomically write ``session_name`` into the pointer file for ``key``."""
    session_file = _dir_session_path(key)
    session_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = session_file.with_suffix(".tmp")
    tmp.write_text(session_name, encoding="utf-8")
    tmp.replace(session_file)  # atomic + overwrites on Windows (unlike os.rename)


def record_directory_session(
    session_name: str, target_path: Optional[str] = None, *, path_kind: str = "auto"
) -> None:
    """Persist ``session_name`` as the latest autosave for a quick-resume scope.

    Best-effort, mirroring ``record_terminal_session``. ``target_path`` lets
    ``-qr ./child`` and observed workspaces reuse the same pointer machinery.
    """
    if not _is_valid_autosave_session_name(session_name):
        logger.debug("Ignoring invalid quick-resume autosave pointer name")
        return
    try:
        _record_directory_session_key(
            session_name, _dir_branch_key_for_path(target_path, path_kind=path_kind)
        )
    except Exception:
        logger.debug("Unable to record quick-resume autosave pointer", exc_info=True)


def observe_quick_resume_path(target_path: str, *, path_kind: str = "auto") -> bool:
    """Remember a child workspace touched by a tool for the next autosave.

    Only a hashed pointer key is stored (never the raw path). The next autosave
    writes its session name to every observed key so ``-qr ./child`` resolves
    even when Code Puppy was launched from the parent directory.
    """
    if not target_path or not str(target_path).strip():
        return False
    try:
        _OBSERVED_QUICK_RESUME_KEYS.add(
            _dir_branch_key_for_path(str(target_path), path_kind=path_kind)
        )
        return True
    except Exception:
        logger.debug("Unable to observe quick-resume path", exc_info=True)
        return False


def clear_observed_quick_resume_paths() -> None:
    """Clear the observed-workspace set (used by tests)."""
    _OBSERVED_QUICK_RESUME_KEYS.clear()


def record_quick_resume_sessions(session_name: str) -> None:
    """Record cwd plus every observed child workspace for ``session_name``."""
    record_directory_session(session_name)
    if not _is_valid_autosave_session_name(session_name):
        return
    for key in tuple(_OBSERVED_QUICK_RESUME_KEYS):
        try:
            _record_directory_session_key(session_name, key)
        except Exception:
            logger.debug(
                "Unable to record observed quick-resume pointer", exc_info=True
            )


def get_last_directory_session(
    target_path: Optional[str] = None, *, path_kind: str = "auto"
) -> Optional[str]:
    """Return the last autosave session name for a scope, or None.

    None when there is no pointer, it is empty, or the recorded name fails
    autosave-name validation. Never raises.
    """
    try:
        session_name = (
            _dir_session_path(
                _dir_branch_key_for_path(target_path, path_kind=path_kind)
            )
            .read_text(encoding="utf-8")
            .strip()
        )
        if not session_name or not _is_valid_autosave_session_name(session_name):
            return None
        return session_name
    except Exception:
        logger.debug("Unable to read quick-resume autosave pointer", exc_info=True)
        return None


def resolve_quick_resume_pickle(
    target_path: Optional[str] = None, *, path_kind: str = "auto"
) -> Optional[str]:
    """Return the absolute ``.pkl`` path for a scope's latest session, or None.

    The single source of truth the CLI ``--quick-resume`` flag consults. Resolves
    strictly inside ``AUTOSAVE_DIR`` (rejecting any path-traversal) and only
    returns a path that is an existing file.
    """
    session_name = get_last_directory_session(target_path, path_kind=path_kind)
    if not session_name:
        return None
    try:
        autosave_dir = pathlib.Path(AUTOSAVE_DIR).resolve()
        candidate = (autosave_dir / f"{session_name}.pkl").resolve(strict=False)
        if candidate.parent != autosave_dir or not candidate.is_file():
            return None
        return str(candidate)
    except OSError:
        logger.debug("Unable to resolve quick-resume autosave path", exc_info=True)
        return None


def finalize_autosave_session() -> str:
    """Persist the current autosave snapshot and rotate to a fresh session."""
    record_terminal_session(get_current_session_name())
    auto_save_session_if_enabled()
    return rotate_session_name()


def get_suppress_thinking_messages() -> bool:
    """
    Checks puppy.cfg for 'suppress_thinking_messages' (case-insensitive in value only).
    Defaults to False if not set.
    Allowed values for ON: 1, '1', 'true', 'yes', 'on' (all case-insensitive for value).
    When enabled, thinking messages (agent_reasoning, planned_next_steps) will be hidden.
    """
    true_vals = {"1", "true", "yes", "on"}
    cfg_val = get_value("suppress_thinking_messages")
    if cfg_val is not None:
        if str(cfg_val).strip().lower() in true_vals:
            return True
        return False
    return False


def set_suppress_thinking_messages(enabled: bool):
    """Sets the suppress_thinking_messages configuration value.

    Args:
        enabled: Whether to suppress thinking messages
    """
    set_config_value("suppress_thinking_messages", "true" if enabled else "false")


def get_smooth_thinking_stream() -> bool:
    """
    Checks puppy.cfg for 'smooth_thinking_stream' (case-insensitive in value only).
    Defaults to True if not set.
    Allowed values for OFF: 0, '0', 'false', 'no', 'off' (all case-insensitive).
    When enabled, THINKING block deltas are buffered and drained to the
    console at a steady, consistent rate instead of being printed in bursts.
    """
    false_vals = {"0", "false", "no", "off"}
    cfg_val = get_value("smooth_thinking_stream")
    if cfg_val is not None:
        if str(cfg_val).strip().lower() in false_vals:
            return False
    return True


def set_smooth_thinking_stream(enabled: bool):
    """Sets the smooth_thinking_stream configuration value.

    Args:
        enabled: Whether to smooth the THINKING stream output
    """
    set_config_value("smooth_thinking_stream", "true" if enabled else "false")


def get_smooth_response_stream() -> bool:
    """
    Checks puppy.cfg for 'smooth_response_stream' (case-insensitive in value only).
    Defaults to True if not set.
    Allowed values for OFF: 0, '0', 'false', 'no', 'off' (all case-insensitive).
    When enabled, the AGENT RESPONSE markdown is typed out one character at a
    time at a steady rate instead of appearing line-by-line in bursts.
    """
    false_vals = {"0", "false", "no", "off"}
    cfg_val = get_value("smooth_response_stream")
    if cfg_val is not None:
        if str(cfg_val).strip().lower() in false_vals:
            return False
    return True


def set_smooth_response_stream(enabled: bool):
    """Sets the smooth_response_stream configuration value.

    Args:
        enabled: Whether to type the AGENT RESPONSE stream out smoothly
    """
    set_config_value("smooth_response_stream", "true" if enabled else "false")


def get_suppress_informational_messages() -> bool:
    """
    Checks puppy.cfg for 'suppress_informational_messages' (case-insensitive in value only).
    Defaults to False if not set.
    Allowed values for ON: 1, '1', 'true', 'yes', 'on' (all case-insensitive for value).
    When enabled, informational messages (info, success, warning) will be hidden.
    """
    true_vals = {"1", "true", "yes", "on"}
    cfg_val = get_value("suppress_informational_messages")
    if cfg_val is not None:
        if str(cfg_val).strip().lower() in true_vals:
            return True
        return False
    return False


def set_suppress_informational_messages(enabled: bool):
    """Sets the suppress_informational_messages configuration value.

    Args:
        enabled: Whether to suppress informational messages
    """
    set_config_value("suppress_informational_messages", "true" if enabled else "false")


# ---------------------------------------------------------------------------
# Output level (unified density control)
# ---------------------------------------------------------------------------

_VALID_OUTPUT_LEVELS = frozenset({"low", "medium", "high"})


def get_output_level() -> str:
    """Return the current output density level.

    Valid values: ``low``, ``medium``, ``high``.  Default is ``medium``
    (current behaviour).  The value is read from ``puppy.cfg`` with the
    key ``output_level``.

    * **low** — collapse tool calls, thinking blocks, and info messages
      to one-line peeks.  Great for focused work.
    * **medium** — current default behaviour.
    * **high** — full metadata: timing, tokens, verbose grep, all
      sub-agent output.
    """
    cfg_val = get_value("output_level")
    if cfg_val is not None:
        normalised = str(cfg_val).strip().lower()
        if normalised in _VALID_OUTPUT_LEVELS:
            return normalised
    return "medium"


def set_output_level(level: str) -> None:
    """Set the output density level.

    Args:
        level: One of ``low``, ``medium``, or ``high``.

    Raises:
        ValueError: If *level* is not a valid choice.
    """
    normalised = level.strip().lower()
    if normalised not in _VALID_OUTPUT_LEVELS:
        raise ValueError(
            f"Invalid output_level {level!r}; choose from low, medium, high"
        )
    set_config_value("output_level", normalised)


# API Key management functions
def get_api_key(key_name: str) -> str:
    """Get an API key from puppy.cfg.

    Args:
        key_name: The name of the API key (e.g., 'OPENAI_API_KEY')

    Returns:
        The API key value, or empty string if not set
    """
    return get_value(key_name) or ""


def set_api_key(key_name: str, value: str):
    """Set an API key in puppy.cfg.

    Args:
        key_name: The name of the API key (e.g., 'OPENAI_API_KEY')
        value: The API key value (empty string to remove)
    """
    set_config_value(key_name, value)


def load_api_keys_to_environment():
    """Load all API keys from .env and puppy.cfg into environment variables.

    Priority order:
    1. .env file (highest priority) - if present in current directory
    2. puppy.cfg - fallback if not in .env
    3. Existing environment variables - preserved if already set

    This should be called on startup to ensure API keys are available.
    """
    from pathlib import Path

    # Static base list of well-known keys (always considered, even if no
    # model currently references them).
    api_key_names = [
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "CEREBRAS_API_KEY",
        "SYN_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "OPENROUTER_API_KEY",
        "ZAI_API_KEY",
    ]

    # Dynamically include every env var referenced by a configured model
    # (e.g. FIREWORKS_API_KEY / WAFER_API_KEY / CROF_API_KEY for local custom
    # providers). Without this, such keys saved in puppy.cfg never hydrate into
    # os.environ at startup. Best-effort: never let discovery break startup.
    try:
        from code_puppy.provider_credentials import all_required_env_vars

        for env_var in all_required_env_vars():
            if env_var not in api_key_names:
                api_key_names.append(env_var)
    except Exception:
        pass

    # Step 1: Load from .env file if it exists (highest priority)
    # Look for .env in current working directory
    env_file = Path.cwd() / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv

            # override=True means .env values take precedence over existing env vars
            load_dotenv(env_file, override=True)
        except ImportError:
            # python-dotenv not installed, skip .env loading
            pass

    # Step 2: Load from puppy.cfg, but only if not already set
    # This ensures .env has priority over puppy.cfg
    for key_name in api_key_names:
        # Only load from config if not already in environment
        if key_name not in os.environ or not os.environ[key_name]:
            value = get_api_key(key_name)
            if value:
                os.environ[key_name] = value


def get_default_agent() -> str:
    """
    Get the default agent name from puppy.cfg.

    Returns:
        str: The default agent name, or "code-puppy" if not set.
    """
    return get_value("default_agent") or "code-puppy"


def set_default_agent(agent_name: str) -> None:
    """
    Set the default agent name in puppy.cfg.

    Args:
        agent_name: The name of the agent to set as default.
    """
    set_config_value("default_agent", agent_name)


# --- FRONTEND EMITTER CONFIGURATION ---
def get_frontend_emitter_enabled() -> bool:
    """Check if frontend emitter is enabled."""
    val = get_value("frontend_emitter_enabled")
    if val is None:
        return True  # Enabled by default
    return str(val).lower() in ("1", "true", "yes", "on")


def get_frontend_emitter_max_recent_events() -> int:
    """Get max number of recent events to buffer."""
    val = get_value("frontend_emitter_max_recent_events")
    if val is None:
        return 100
    try:
        return int(val)
    except ValueError:
        return 100


def get_frontend_emitter_queue_size() -> int:
    """Get max subscriber queue size."""
    val = get_value("frontend_emitter_queue_size")
    if val is None:
        return 100
    try:
        return int(val)
    except ValueError:
        return 100
