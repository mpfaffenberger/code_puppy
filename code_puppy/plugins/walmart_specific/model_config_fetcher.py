import json
import logging
import os
from typing import Any, Dict

import httpx

from code_puppy.http_utils import create_client
from code_puppy.plugins.walmart_specific.urls import get_models_url


class ModelConfigFetcher:
    # Class-level cache to prevent redundant fetching
    _config_cache: Dict[str, Dict[str, Any]] = {}
    _cache_initialized: Dict[str, bool] = {}

    @staticmethod
    def load_config(config_path: str) -> Dict[str, Any]:
        """Loads model configurations, checking for updates from remote source first.

        Uses a class-level cache to prevent redundant fetching during the same session.
        Cache is keyed by config_path to support multiple different config files.
        """
        # Check cache first - avoid redundant network calls! 🐕
        if (
            config_path in ModelConfigFetcher._config_cache
            and ModelConfigFetcher._cache_initialized.get(config_path, False)
        ):
            return ModelConfigFetcher._config_cache[config_path]
        remote_url = get_models_url()
        logger = logging.getLogger(__name__)

        # Try to fetch the latest config from remote
        remote_config = None
        try:
            logger.info(f"Fetching latest model config from {remote_url}")
            with create_client() as client:
                response = client.get(remote_url, timeout=10)
                response.raise_for_status()
                remote_config = response.json()["config"]
                logger.info("Successfully fetched remote model config")
        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch remote config: {e}")

        # Try to load existing local config
        local_config = None
        config_exists = os.path.exists(config_path)
        if config_exists:
            try:
                with open(config_path, "r") as f:
                    local_config = json.load(f)
                logger.info(f"Loaded local config from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load local config: {e}")

        # Determine which config to use and whether to update local file
        config_to_use = None
        should_update_local = False

        if remote_config:
            # We have remote config - use it
            config_to_use = remote_config

            # Check if we need to update local file
            if not config_exists or local_config != remote_config:
                should_update_local = True
                logger.info("Remote config differs from local, will update local file")
        elif local_config:
            # No remote config but we have local - use local
            config_to_use = local_config
            logger.info("Using local config as fallback")
        else:
            # Neither remote nor local config available
            raise FileNotFoundError(
                f"Could not load model configuration: remote fetch failed and no local config exists at {config_path}"
            )

        # Update local file if needed
        if should_update_local:
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(config_path), exist_ok=True)

                with open(config_path, "w") as f:
                    json.dump(config_to_use, f, indent=2)
                logger.info(f"Updated local config file at {config_path}")
            except Exception as e:
                logger.error(f"Failed to update local config file: {e}")
                # Don't fail if we can't write - we still have the config to use

        # Cache the config to prevent redundant fetching! 🎾
        ModelConfigFetcher._config_cache[config_path] = config_to_use
        ModelConfigFetcher._cache_initialized[config_path] = True
        logger.info(f"Cached model config for {config_path}")

        return config_to_use
