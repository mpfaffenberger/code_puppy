"""Handler and utilities for uploading agents to the marketplace.

Provides functionality to upload custom agents to the marketplace,
including validation, hashing, and local state management.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from code_puppy.messaging import emit_error, emit_info, emit_success

# Required fields for a valid agent JSON
REQUIRED_FIELDS = ["name", "description", "system_prompt", "tools"]

# Local storage for tracking uploaded agent hashes
AGENTS_DIR = Path.home() / ".code_puppy" / "agents"
MARKETPLACE_META_DIR = AGENTS_DIR / ".marketplace"


def load_agent_file(file_path: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Load and parse an agent JSON file.

    Args:
        file_path: Path to the agent JSON file.

    Returns:
        Tuple of (agent_data, error_message).
        If successful, error_message is None.
        If failed, agent_data is None.
    """
    path = Path(file_path).expanduser()

    if not path.exists():
        return None, f"File not found: {path}"

    if not path.is_file():
        return None, f"Not a file: {path}"

    if path.suffix.lower() != ".json":
        return None, f"Expected .json file, got: {path.suffix}"

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data, None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"
    except Exception as e:
        return None, f"Error reading file: {e}"


def validate_agent_data(agent_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate that agent data has required fields and correct types.

    Args:
        agent_data: The agent configuration dictionary.

    Returns:
        Tuple of (is_valid, list_of_errors).
    """
    errors = []

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in agent_data:
            errors.append(f"Missing required field: '{field}'")

    if errors:
        return False, errors

    # Validate types
    name = agent_data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("'name' must be a non-empty string")
    elif " " in name:
        errors.append("'name' should use hyphens instead of spaces")

    description = agent_data.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append("'description' must be a non-empty string")

    system_prompt = agent_data.get("system_prompt")
    if not isinstance(system_prompt, (str, list)):
        errors.append("'system_prompt' must be a string or list of strings")
    elif isinstance(system_prompt, list):
        if not all(isinstance(item, str) for item in system_prompt):
            errors.append("All items in 'system_prompt' list must be strings")

    tools = agent_data.get("tools")
    if not isinstance(tools, list):
        errors.append("'tools' must be a list")
    elif not all(isinstance(tool, str) for tool in tools):
        errors.append("All items in 'tools' must be strings")

    return len(errors) == 0, errors


def generate_agent_hash(agent_data: Dict[str, Any]) -> str:
    """Generate a content hash for an agent.

    The hash is based on the functional content of the agent,
    excluding metadata like version or timestamps.

    Args:
        agent_data: The agent configuration dictionary.

    Returns:
        SHA-1 hash of the agent content.
    """
    # Include only functional content in the hash
    content_to_hash = {
        "name": agent_data.get("name", ""),
        "description": agent_data.get("description", ""),
        "system_prompt": agent_data.get("system_prompt", ""),
        "tools": sorted(agent_data.get("tools", [])),
        "tools_config": agent_data.get("tools_config"),
        "user_prompt": agent_data.get("user_prompt"),
        "model": agent_data.get("model"),
    }

    # Create deterministic JSON string
    json_str = json.dumps(content_to_hash, sort_keys=True, ensure_ascii=True)
    return hashlib.sha1(json_str.encode()).hexdigest()


def get_local_hash(agent_name: str) -> Optional[str]:
    """Get the stored hash for a locally downloaded agent.

    Args:
        agent_name: Name of the agent.

    Returns:
        The stored hash, or None if not found.
    """
    meta_file = MARKETPLACE_META_DIR / f"{agent_name}.meta.json"
    if not meta_file.exists():
        return None

    try:
        with open(meta_file, "r") as f:
            meta = json.load(f)
        return meta.get("content_hash")
    except Exception:
        return None


def save_local_hash(agent_name: str, content_hash: str, version: int = 1) -> bool:
    """Save the hash for a downloaded/uploaded agent.

    Args:
        agent_name: Name of the agent.
        content_hash: The content hash to store.
        version: The version number.

    Returns:
        True if saved successfully.
    """
    MARKETPLACE_META_DIR.mkdir(parents=True, exist_ok=True)
    meta_file = MARKETPLACE_META_DIR / f"{agent_name}.meta.json"

    try:
        meta = {
            "agent_name": agent_name,
            "content_hash": content_hash,
            "version": version,
        }
        with open(meta_file, "w") as f:
            json.dump(meta, f, indent=2)
        return True
    except Exception:
        return False


def handle_upload_agent(command: str) -> bool:
    """Handle the upload-agent command.

    Args:
        command: The full command string including any arguments.

    Returns:
        bool: True to indicate the command was handled.
    """
    emit_info("Use the /upload-agent command with a file path, or use the agent-creator's marketplace tools.")
    return True
