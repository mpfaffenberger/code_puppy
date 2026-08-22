"""JSON-based agent configuration system."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_puppy import atomic_json

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


def model_settings_validation_errors(model_settings: Dict[str, Any]) -> List[str]:
    """Return validation error messages for a ``model_settings`` mapping.

    Checks keys against the known setting registry and values against each
    setting's declared type/range/choices, so a typo'd key or a malformed
    value (e.g. ``"temperature": "hot"``) is caught before it can either
    silently vanish (unknown keys are filtered out downstream by
    ``model_supports_setting``) or ride unfiltered into a provider request.

    Shared by :class:`JSONAgent` (raises on load) and
    ``AgentCreatorAgent.validate_agent_json`` (collects errors for the
    create/edit flow) so the two validation paths can't drift apart.
    """
    from code_puppy.command_line.model_settings_menu import SETTING_DEFINITIONS

    errors: List[str] = []
    for key, value in model_settings.items():
        definition = SETTING_DEFINITIONS.get(key)
        if definition is None:
            valid_keys = ", ".join(sorted(SETTING_DEFINITIONS))
            errors.append(
                f"Unknown model_settings key {key!r}. Valid keys: {valid_keys}"
            )
            continue

        setting_type = definition.get("type")
        if setting_type == "numeric":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(
                    f"model_settings[{key!r}] must be a number (got {value!r})"
                )
                continue
            min_value = definition.get("min")
            max_value = definition.get("max")
            if min_value is not None and value < min_value:
                errors.append(
                    f"model_settings[{key!r}] must be >= {min_value} (got {value!r})"
                )
            if max_value is not None and value > max_value:
                errors.append(
                    f"model_settings[{key!r}] must be <= {max_value} (got {value!r})"
                )
        elif setting_type == "choice":
            choices = definition.get("choices", [])
            if value not in choices:
                errors.append(
                    f"model_settings[{key!r}] must be one of {choices} (got {value!r})"
                )
        elif setting_type == "boolean":
            if not isinstance(value, bool):
                errors.append(
                    f"model_settings[{key!r}] must be true or false (got {value!r})"
                )
        # "custom" settings are a free-form dict of provider extra_body
        # params; no further shape is enforced here.

    return errors


class JSONAgent(BaseAgent):
    """Agent configured from a JSON file."""

    def __init__(self, json_path: str):
        """Initialize agent from JSON file.

        Args:
            json_path: Path to the JSON configuration file.
        """
        super().__init__()
        self.json_path = json_path
        self._config = self._load_config()
        self._validate_config()

    def _load_config(self) -> Dict:
        """Load configuration from JSON file.

        Bounded via :mod:`code_puppy.atomic_json` -- a pathologically large
        agent file dropped in ``~/.code_puppy/agents/`` can no longer
        balloon memory the way the original ``configparser`` bug did.
        """
        try:
            data = atomic_json.load_json(self.json_path)
        except (atomic_json.JsonFileCorrupt, OSError) as e:
            raise ValueError(
                f"Failed to load JSON agent config from {self.json_path}: {e}"
            ) from e
        if data is None:
            raise ValueError(
                f"Failed to load JSON agent config from {self.json_path}: "
                "file not found or empty"
            )
        return data

    def _validate_config(self) -> None:
        """Validate required fields in configuration."""
        required_fields = ["name", "description", "system_prompt", "tools"]
        for field in required_fields:
            if field not in self._config:
                raise ValueError(
                    f"Missing required field '{field}' in JSON agent config: {self.json_path}"
                )

        # Validate tools is a list
        if not isinstance(self._config["tools"], list):
            raise ValueError(
                f"'tools' must be a list in JSON agent config: {self.json_path}"
            )

        # Validate system_prompt is string or list
        system_prompt = self._config["system_prompt"]
        if not isinstance(system_prompt, (str, list)):
            raise ValueError(
                f"'system_prompt' must be a string or list in JSON agent config: {self.json_path}"
            )

        if "model_settings" in self._config:
            model_settings = self._config["model_settings"]
            if not isinstance(model_settings, dict):
                raise ValueError(
                    f"'model_settings' must be an object in JSON agent config: {self.json_path}"
                )
            self._validate_model_settings(model_settings)

        # mcp_servers: list[str] (shorthand, auto_start=True) or dict[str, dict]
        # (per-server options). Anything else is a config error with a clear
        # message.
        if "mcp_servers" in self._config:
            mcp_servers = self._config["mcp_servers"]
            if isinstance(mcp_servers, list):
                for entry in mcp_servers:
                    if not isinstance(entry, str):
                        raise ValueError(
                            f"'mcp_servers' list entries must be strings (server names) in "
                            f"JSON agent config: {self.json_path}"
                        )
            elif isinstance(mcp_servers, dict):
                for server_name, opts in mcp_servers.items():
                    if not isinstance(server_name, str):
                        raise ValueError(
                            f"'mcp_servers' keys must be strings in JSON agent config: "
                            f"{self.json_path}"
                        )
                    if not isinstance(opts, dict):
                        raise ValueError(
                            f"'mcp_servers[{server_name!r}]' must be a dict of options "
                            f'(e.g. {{"auto_start": true}}) in JSON agent config: '
                            f"{self.json_path}"
                        )
            else:
                raise ValueError(
                    f"'mcp_servers' must be a list of names or a dict of "
                    f"{{name: options}} in JSON agent config: {self.json_path}"
                )

    def _validate_model_settings(self, model_settings: Dict[str, Any]) -> None:
        """Validate model_settings keys and values against known definitions.

        Catches typos and obviously-wrong values at agent load time instead
        of letting an unknown key silently vanish (filtered out downstream by
        ``model_supports_setting``) or a malformed value ride unfiltered into
        the provider request.
        """
        errors = model_settings_validation_errors(model_settings)
        if errors:
            raise ValueError(
                f"Invalid 'model_settings' in JSON agent config: {self.json_path}: "
                + "; ".join(errors)
            )

    @property
    def name(self) -> str:
        """Get agent name from JSON config."""
        return self._config["name"]

    @property
    def display_name(self) -> str:
        """Get display name from JSON config, fallback to name with emoji."""
        return self._config.get("display_name", f"{self.name.title()} 🤖")

    @property
    def description(self) -> str:
        """Get description from JSON config."""
        return self._config["description"]

    def get_system_prompt(self) -> str:
        """Get system prompt from JSON config."""
        system_prompt = self._config["system_prompt"]

        # If it's a list, join with newlines
        if isinstance(system_prompt, list):
            return "\n".join(system_prompt)

        return system_prompt

    def get_available_tools(self) -> List[str]:
        """Get available tools from JSON config.

        Supports both built-in tools and Universal Constructor (UC) tools.
        UC tools are identified by checking the UC registry.
        """
        from code_puppy.tools import get_available_tool_names

        available_tools = get_available_tool_names()

        # Also get UC tool names
        uc_tool_names = set()
        try:
            from code_puppy.universal_constructor_provider import (
                get_universal_constructor_provider,
            )

            provider = get_universal_constructor_provider()
            for tool in provider.list_tools() if provider else []:
                if tool.meta.enabled:
                    uc_tool_names.add(tool.full_name)
        except ImportError:
            pass  # UC module not available
        except Exception as e:
            # Log unexpected errors but don't fail
            import logging

            logging.debug(f"UC registry access failed: {e}")

        # Return tools that are either built-in OR UC tools
        requested_tools = []
        for tool in self._config["tools"]:
            if tool in available_tools:
                requested_tools.append(tool)
            elif tool in uc_tool_names:
                # UC tool - mark it specially so base_agent knows to handle it
                requested_tools.append(f"uc:{tool}")

        return requested_tools

    def get_user_prompt(self) -> Optional[str]:
        """Get custom user prompt from JSON config."""
        return self._config.get("user_prompt")

    def get_tools_config(self) -> Optional[Dict]:
        """Get tool configuration from JSON config."""
        return self._config.get("tools_config")

    def get_model_settings_overrides(self) -> Dict[str, Any]:
        """Get model request-setting overrides from JSON config."""
        return dict(self._config.get("model_settings", {}))

    def get_declared_mcp_bindings(self) -> Dict[str, Dict[str, Any]]:
        """Return MCP bindings declared in the JSON config, normalized.

        The ``mcp_servers`` field accepts two shapes for ergonomics:

        * ``["serena", "puppeteer"]`` -- list shorthand; each entry
          defaults to ``auto_start=True`` (matching the bindings menu's
          default — the obvious intent when you list a server).
        * ``{"serena": {"auto_start": true}, "puppeteer": {"auto_start": false}}``
          -- explicit per-server options.

        Both are normalized here to ``{name: {"auto_start": bool}}`` so the
        rest of the system only ever deals with one shape. Returns ``{}``
        when the field is absent.
        """
        raw = self._config.get("mcp_servers")
        if raw is None:
            return {}

        normalized: Dict[str, Dict[str, Any]] = {}
        if isinstance(raw, list):
            for name in raw:
                normalized[name] = {"auto_start": True}
        elif isinstance(raw, dict):
            for name, opts in raw.items():
                normalized[name] = {
                    "auto_start": bool(opts.get("auto_start", True)),
                }
        # Any other shape was rejected at validation time; defensive no-op.
        return normalized

    def refresh_config(self) -> None:
        """Reload the agent configuration from disk.

        This keeps long-lived agent instances in sync after external edits.
        """
        self._config = self._load_config()
        self._validate_config()

    def get_model_name(self) -> Optional[str]:
        """Get the effective model name for this JSON agent.

        A runtime override is deliberately checked first so orchestrators can
        choose a model for one invocation without editing the JSON file.
        """
        override = self.get_runtime_model_name_override()
        if override:
            return override

        # A ``model_select`` hook choice outranks the JSON ``model`` field so
        # per-turn routing works for JSON agents too (see get_model_name in
        # BaseAgent for the full precedence ladder).
        auto = self.get_auto_model_override()
        if auto:
            return auto

        result = self._config.get("model")
        if result is None or (isinstance(result, str) and not result.strip()):
            result = super().get_model_name()
        return result


def discover_json_agents() -> Dict[str, str]:
    """Discover JSON agent files in the user's and project's agents directories.

    Searches two locations:
    1. User agents directory (~/.code_puppy/agents/)
    2. Project agents directory (<CWD>/.code_puppy/agents/) - if it exists

    Project agents take priority over user agents when names collide.

    Returns:
        Dict mapping agent names to their JSON file paths.
    """
    from code_puppy.config import (
        get_project_agents_directory,
        get_user_agents_directory,
    )

    agents: Dict[str, str] = {}

    # 1. Discover user-level agents first
    user_agents_dir = Path(get_user_agents_directory())
    if user_agents_dir.exists() and user_agents_dir.is_dir():
        for json_file in user_agents_dir.glob("*.json"):
            try:
                agent = JSONAgent(str(json_file))
                agents[agent.name] = str(json_file)
            except Exception as e:
                logger.debug(
                    "Skipping invalid user agent file: %s (reason: %s: %s)",
                    json_file,
                    type(e).__name__,
                    str(e),
                )
                continue

    # 2. Discover project-level agents (overrides user agents on name collision)
    project_agents_dir_str = get_project_agents_directory()
    if project_agents_dir_str is not None:
        project_agents_dir = Path(project_agents_dir_str)
        for json_file in project_agents_dir.glob("*.json"):
            try:
                agent = JSONAgent(str(json_file))
                agents[agent.name] = str(json_file)
            except Exception as e:
                logger.debug(
                    "Skipping invalid project agent file: %s (reason: %s: %s)",
                    json_file,
                    type(e).__name__,
                    str(e),
                )
                continue

    return agents
