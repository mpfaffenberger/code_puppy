"""
ServerRegistry implementation for managing MCP server configurations.

This module provides a registry that tracks all MCP server configurations
and provides thread-safe CRUD operations with JSON persistence.
"""

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from .managed_server import ServerConfig

# Configure logging
logger = logging.getLogger(__name__)


class ServerRegistry:
    """
    Registry for managing MCP server configurations.

    Provides CRUD operations for server configurations with thread-safe access,
    validation, and persistent storage to ~/.code_puppy/mcp_registry.json.

    All operations are thread-safe and use JSON serialization for ServerConfig objects.
    Handles file not existing gracefully and validates configurations according to
    server type requirements.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize the server registry.

        Args:
            storage_path: Optional custom path for registry storage.
                         Defaults to ~/.code_puppy/mcp_registry.json
        """
        if storage_path is None:
            home_dir = Path.home()
            code_puppy_dir = home_dir / ".code_puppy"
            code_puppy_dir.mkdir(exist_ok=True)
            self._storage_path = code_puppy_dir / "mcp_registry.json"
        else:
            self._storage_path = Path(storage_path)

        # Thread safety lock (reentrant)
        self._lock = threading.RLock()

        # In-memory storage: server_id -> ServerConfig
        self._servers: Dict[str, ServerConfig] = {}

        # Load existing configurations
        self._load()

        logger.info(f"Initialized ServerRegistry with storage at {self._storage_path}")

    def register(self, config: ServerConfig) -> str:
        """
        Add new server configuration.

        Args:
            config: Server configuration to register

        Returns:
            Server ID of the registered server

        Raises:
            ValueError: If validation fails or server already exists
        """
        with self._lock:
            # Validate configuration
            validation_errors = self.validate_config(config)
            if validation_errors:
                raise ValueError(f"Validation failed: {'; '.join(validation_errors)}")

            # Generate ID if not provided or ensure uniqueness
            if not config.id:
                config.id = str(uuid.uuid4())
            elif config.id in self._servers:
                raise ValueError(f"Server with ID {config.id} already exists")

            # Check name uniqueness
            existing_config = self.get_by_name(config.name)
            if existing_config and existing_config.id != config.id:
                raise ValueError(f"Server with name '{config.name}' already exists")

            # Store configuration
            self._servers[config.id] = config

            # Persist to disk
            self._persist()

            logger.info(f"Registered server: {config.name} (ID: {config.id})")
            return config.id

    def unregister(self, server_id: str) -> bool:
        """
        Remove server configuration.

        Args:
            server_id: ID of server to remove

        Returns:
            True if server was removed, False if not found
        """
        with self._lock:
            if server_id not in self._servers:
                logger.warning(
                    f"Attempted to unregister non-existent server: {server_id}"
                )
                return False

            server_name = self._servers[server_id].name
            del self._servers[server_id]

            # Persist to disk
            self._persist()

            logger.info(f"Unregistered server: {server_name} (ID: {server_id})")
            return True

    def get(self, server_id: str) -> Optional[ServerConfig]:
        """
        Get server configuration by ID.

        Args:
            server_id: ID of server to retrieve

        Returns:
            ServerConfig if found, None otherwise
        """
        with self._lock:
            return self._servers.get(server_id)

    def get_by_name(self, name: str) -> Optional[ServerConfig]:
        """
        Get server configuration by name.

        Args:
            name: Name of server to retrieve

        Returns:
            ServerConfig if found, None otherwise
        """
        with self._lock:
            for config in self._servers.values():
                if config.name == name:
                    return config
            return None

    def list_all(self) -> List[ServerConfig]:
        """
        Get all server configurations.

        Returns:
            List of all ServerConfig objects
        """
        with self._lock:
            return list(self._servers.values())

    def update(self, server_id: str, config: ServerConfig) -> bool:
        """
        Update existing server configuration.

        Args:
            server_id: ID of server to update
            config: New configuration

        Returns:
            True if update succeeded, False if server not found

        Raises:
            ValueError: If validation fails
        """
        with self._lock:
            if server_id not in self._servers:
                logger.warning(f"Attempted to update non-existent server: {server_id}")
                return False

            # Ensure the ID matches
            config.id = server_id

            # Validate configuration
            validation_errors = self.validate_config(config)
            if validation_errors:
                raise ValueError(f"Validation failed: {'; '.join(validation_errors)}")

            # Check name uniqueness (excluding current server)
            existing_config = self.get_by_name(config.name)
            if existing_config and existing_config.id != server_id:
                raise ValueError(f"Server with name '{config.name}' already exists")

            # Update configuration
            old_name = self._servers[server_id].name
            self._servers[server_id] = config

            # Persist to disk
            self._persist()

            logger.info(
                f"Updated server: {old_name} -> {config.name} (ID: {server_id})"
            )
            return True

    def exists(self, server_id: str) -> bool:
        """
        Check if server exists.

        Args:
            server_id: ID of server to check

        Returns:
            True if server exists, False otherwise
        """
        with self._lock:
            return server_id in self._servers

    def validate_config(self, config: ServerConfig) -> List[str]:
        """
        Validate server configuration.

        Args:
            config: Configuration to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Basic validation
        if not config.name or not config.name.strip():
            errors.append("Server name is required")
        elif not config.name.replace("-", "").replace("_", "").isalnum():
            errors.append(
                "Server name must be alphanumeric (hyphens and underscores allowed)"
            )

        if not config.type:
            errors.append("Server type is required")
        elif config.type.lower() not in ["sse", "stdio", "http"]:
            errors.append("Server type must be one of: sse, stdio, http")

        if not isinstance(config.config, dict):
            errors.append("Server config must be a dictionary")
            return errors  # Can't validate further without valid config dict

        # Type-specific validation
        server_type = config.type.lower()
        server_config = config.config

        if server_type in ["sse", "http"]:
            if "url" not in server_config:
                errors.append(f"{server_type.upper()} server requires 'url' in config")
            elif (
                not isinstance(server_config["url"], str)
                or not server_config["url"].strip()
            ):
                errors.append(
                    f"{server_type.upper()} server URL must be a non-empty string"
                )
            elif not (
                server_config["url"].startswith("http://")
                or server_config["url"].startswith("https://")
            ):
                errors.append(
                    f"{server_type.upper()} server URL must start with http:// or https://"
                )

            # Optional parameter validation
            if "timeout" in server_config:
                try:
                    timeout = float(server_config["timeout"])
                    if timeout <= 0:
                        errors.append("Timeout must be positive")
                except (ValueError, TypeError):
                    errors.append("Timeout must be a number")

            if "read_timeout" in server_config:
                try:
                    read_timeout = float(server_config["read_timeout"])
                    if read_timeout <= 0:
                        errors.append("Read timeout must be positive")
                except (ValueError, TypeError):
                    errors.append("Read timeout must be a number")

            if "headers" in server_config:
                if not isinstance(server_config["headers"], dict):
                    errors.append("Headers must be a dictionary")

        elif server_type == "stdio":
            if "command" not in server_config:
                errors.append("Stdio server requires 'command' in config")
            elif (
                not isinstance(server_config["command"], str)
                or not server_config["command"].strip()
            ):
                errors.append("Stdio server command must be a non-empty string")

            # Optional parameter validation
            if "args" in server_config:
                args = server_config["args"]
                if not isinstance(args, (list, str)):
                    errors.append("Args must be a list or string")
                elif isinstance(args, list):
                    if not all(isinstance(arg, str) for arg in args):
                        errors.append("All args must be strings")

            if "env" in server_config:
                if not isinstance(server_config["env"], dict):
                    errors.append("Environment variables must be a dictionary")
                elif not all(
                    isinstance(k, str) and isinstance(v, str)
                    for k, v in server_config["env"].items()
                ):
                    errors.append("All environment variables must be strings")

            if "cwd" in server_config:
                if not isinstance(server_config["cwd"], str):
                    errors.append("Working directory must be a string")

        return errors

    def _persist(self) -> None:
        """
        Save registry to disk.

        This method assumes it's called within a lock context.

        Raises:
            Exception: If unable to write to storage file
        """
        try:
            # Convert ServerConfig objects to dictionaries for JSON serialization
            data = {}
            for server_id, config in self._servers.items():
                data[server_id] = {
                    "id": config.id,
                    "name": config.name,
                    "type": config.type,
                    "enabled": config.enabled,
                    "config": config.config,
                }

            # Ensure directory exists
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)

            # Write to temporary file first, then rename (atomic operation)
            temp_path = self._storage_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Atomic rename
            temp_path.replace(self._storage_path)

            logger.debug(
                f"Persisted {len(self._servers)} server configurations to {self._storage_path}"
            )

        except Exception as e:
            logger.error(f"Failed to persist server registry: {e}")
            raise

    def _load(self) -> None:
        """
        Load registry from disk.

        Handles file not existing gracefully by starting with empty registry.
        Invalid entries are logged and skipped.
        """
        try:
            if not self._storage_path.exists():
                logger.info(
                    f"Registry file {self._storage_path} does not exist, starting with empty registry"
                )
                return

            # Check if file is empty
            if self._storage_path.stat().st_size == 0:
                logger.info(
                    f"Registry file {self._storage_path} is empty, starting with empty registry"
                )
                return

            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                logger.warning(
                    f"Invalid registry format in {self._storage_path}, starting with empty registry"
                )
                return

            # Load server configurations
            loaded_count = 0
            for server_id, config_data in data.items():
                try:
                    # Validate the structure
                    if not isinstance(config_data, dict):
                        logger.warning(
                            f"Skipping invalid config for server {server_id}: not a dictionary"
                        )
                        continue

                    required_fields = ["id", "name", "type", "config"]
                    if not all(field in config_data for field in required_fields):
                        logger.warning(
                            f"Skipping incomplete config for server {server_id}: missing required fields"
                        )
                        continue

                    # Create ServerConfig object
                    config = ServerConfig(
                        id=config_data["id"],
                        name=config_data["name"],
                        type=config_data["type"],
                        enabled=config_data.get("enabled", True),
                        config=config_data["config"],
                    )

                    # Basic validation
                    validation_errors = self.validate_config(config)
                    if validation_errors:
                        logger.warning(
                            f"Skipping invalid config for server {server_id}: {'; '.join(validation_errors)}"
                        )
                        continue

                    # Store configuration
                    self._servers[server_id] = config
                    loaded_count += 1

                except Exception as e:
                    logger.warning(
                        f"Skipping invalid config for server {server_id}: {e}"
                    )
                    continue

            logger.info(
                f"Loaded {loaded_count} server configurations from {self._storage_path}"
            )

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in registry file {self._storage_path}: {e}")
            logger.info("Starting with empty registry")
        except Exception as e:
            logger.error(f"Failed to load server registry: {e}")
            logger.info("Starting with empty registry")
