"""Reusable visibility store for picker menus.

Provides atomic persistence, stale entry cleanup, and toggle operations
for hiding items from picker UIs.

Usage:
    # Model visibility (current scope)
    from code_puppy.item_visibility import load_hidden_models, toggle_model_hidden

    hidden = load_hidden_models()
    toggle_model_hidden("gpt-4")

    # Agent visibility (future work)
    from code_puppy.item_visibility import VisibilityStore
    agent_store = VisibilityStore("agent")
    agent_store.toggle("typescript-reviewer")

    # MCP server visibility (future work)
    mcp_store = VisibilityStore("mcp_servers")
    mcp_store.toggle("my-custom-server")
"""

from __future__ import annotations

import json
import logging
import os
from typing import Iterable, Optional

from code_puppy.config import DATA_DIR

logger = logging.getLogger(__name__)


class VisibilityStore:
    """Reusable visibility store for picker menus.

    Provides atomic persistence, stale entry cleanup, and toggle operations
    for hiding items from picker UIs.

    Each store is independent — no shared mutable state between different
    store instances.

    Usage:
        store = VisibilityStore("model")  # → DATA_DIR/model_visibility.json
        store.toggle("gpt-4")
        store.prune_stale(["gpt-4", "claude-3"])  # cleanup removed items
    """

    def __init__(self, name: str):
        """Initialize a visibility store.

        Args:
            name: Identifier for this visibility store.
                  Results in DATA_DIR/{name}_visibility.json
                  e.g., "model" → "model_visibility.json"
        """
        self._name = name
        self._file_path = os.path.join(DATA_DIR, f"{name}_visibility.json")
        # JSON key: "hidden_models", "hidden_agents", etc.
        self._hidden_key = f"hidden_{name}s"

    @property
    def name(self) -> str:
        """Return the store name."""
        return self._name

    @property
    def file_path(self) -> str:
        """Return the path to the visibility config file."""
        return self._file_path

    def load_hidden(self) -> set[str]:
        """Load the set of hidden items from disk.

        Returns:
            Set of hidden item names. Empty set if file missing, corrupt,
            or permission denied.
        """
        file_path = self._file_path

        # File doesn't exist — nothing hidden
        if not os.path.exists(file_path):
            return set()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                f"Failed to read visibility file {file_path}: {exc}",
            )
            return set()

        # Validate structure
        if not isinstance(data, dict):
            logger.warning(
                f"Visibility file {file_path} has invalid structure (not a dict)",
            )
            return set()

        hidden_list = data.get(self._hidden_key)
        if not isinstance(hidden_list, list):
            # Key missing or wrong type — nothing hidden
            return set()

        return set(hidden_list)

    def save_hidden(self, hidden: set[str]) -> None:
        """Save the set of hidden items to disk atomically.

        Creates DATA_DIR if it doesn't exist. Uses atomic write
        (temp file + rename) to prevent corruption.

        Args:
            hidden: Set of hidden item names to persist.
        """
        file_path = self._file_path

        # Ensure directory exists
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
        except OSError as exc:
            logger.error(f"Failed to create data directory: {exc}")
            return

        # Build data structure
        data = {self._hidden_key: sorted(hidden)}

        # Atomic write: write to temp file, then rename
        tmp_path = file_path + ".tmp"
        try:
            content = json.dumps(data, indent=2) + "\n"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, file_path)
        except OSError as exc:
            logger.error(f"Failed to write visibility file {file_path}: {exc}")
            # Clean up temp file if it exists
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def is_hidden(self, item: str) -> bool:
        """Check if an item is hidden.

        Args:
            item: Item name to check.

        Returns:
            True if item is hidden, False otherwise.
        """
        return item in self.load_hidden()

    def toggle(self, item: str) -> bool:
        """Toggle the visibility of an item.

        If the item is visible, it becomes hidden.
        If the item is hidden, it becomes visible.

        Args:
            item: Item name to toggle.

        Returns:
            True if the item is now hidden, False if now visible.
        """
        hidden = self.load_hidden()

        if item in hidden:
            hidden.discard(item)
            now_hidden = False
        else:
            hidden.add(item)
            now_hidden = True

        self.save_hidden(hidden)
        return now_hidden

    def add_hidden(self, item: str) -> None:
        """Add an item to the hidden set.

        Args:
            item: Item name to hide.
        """
        hidden = self.load_hidden()
        hidden.add(item)
        self.save_hidden(hidden)

    def remove_hidden(self, item: str) -> None:
        """Remove an item from the hidden set.

        Args:
            item: Item name to unhide.
        """
        hidden = self.load_hidden()
        hidden.discard(item)
        self.save_hidden(hidden)

    def prune_stale(self, valid_items: Iterable[str]) -> set[str]:
        """Remove hidden items that are no longer valid.

        Compares the hidden set against provided valid items and removes
        any hidden entries that don't exist in valid_items.

        Writes back to disk if changes were made.

        Args:
            valid_items: Iterable of currently valid item names.

        Returns:
            Set of removed (stale) item names. Empty if nothing changed.
        """
        hidden = self.load_hidden()
        valid_set = set(valid_items)
        stale = hidden - valid_set

        if stale:
            new_hidden = hidden - stale
            self.save_hidden(new_hidden)

        return stale

    def clear(self) -> None:
        """Remove the visibility config file.

        Idempotent — safe to call even if file doesn't exist.
        """
        if os.path.exists(self._file_path):
            try:
                os.remove(self._file_path)
            except OSError as exc:
                logger.warning(f"Failed to remove visibility file: {exc}")


# -----------------------------------------------------------------------------
# Module-level convenience functions for model visibility
# These provide a stable API for the current scope (models only)
# -----------------------------------------------------------------------------

# Lazy-initialized module-level store instance
_model_store: Optional[VisibilityStore] = None


def _get_model_store() -> VisibilityStore:
    """Get the module-level model visibility store (lazy init)."""
    global _model_store
    if _model_store is None:
        _model_store = VisibilityStore("model")
    return _model_store


def load_hidden_models() -> set[str]:
    """Load the set of hidden model names.

    Returns:
        Set of hidden model names. Empty set if no visibility config exists.
    """
    return _get_model_store().load_hidden()


def save_hidden_models(hidden: set[str]) -> None:
    """Save the set of hidden model names.

    Args:
        hidden: Set of hidden model names to persist.
    """
    _get_model_store().save_hidden(hidden)


def toggle_model_hidden(model: str) -> bool:
    """Toggle the visibility of a model.

    Args:
        model: Model name to toggle.

    Returns:
        True if the model is now hidden, False if now visible.
    """
    return _get_model_store().toggle(model)


def is_model_hidden(model: str) -> bool:
    """Check if a model is hidden.

    Args:
        model: Model name to check.

    Returns:
        True if model is hidden, False otherwise.
    """
    return _get_model_store().is_hidden(model)


def prune_stale_entries(all_model_names: Iterable[str]) -> set[str]:
    """Remove hidden model entries that are no longer valid.

    Args:
        all_model_names: Iterable of currently valid model names.

    Returns:
        Set of removed (stale) model names. Empty if nothing changed.
    """
    return _get_model_store().prune_stale(all_model_names)


def clear_visibility_config() -> None:
    """Remove the model visibility config file.

    Idempotent — safe to call even if file doesn't exist.
    """
    _get_model_store().clear()


# -----------------------------------------------------------------------------
# Module-level convenience functions for agent visibility
# -----------------------------------------------------------------------------

# Lazy-initialized module-level store instance for agents
_agent_store: Optional[VisibilityStore] = None


def _get_agent_store() -> VisibilityStore:
    """Get the module-level agent visibility store (lazy init)."""
    global _agent_store
    if _agent_store is None:
        _agent_store = VisibilityStore("agent")
    return _agent_store


def load_hidden_agents() -> set[str]:
    """Load the set of hidden agent names.

    Returns:
        Set of hidden agent names. Empty set if no visibility config exists.
    """
    return _get_agent_store().load_hidden()


def save_hidden_agents(hidden: set[str]) -> None:
    """Save the set of hidden agent names.

    Args:
        hidden: Set of hidden agent names to persist.
    """
    _get_agent_store().save_hidden(hidden)


def toggle_agent_hidden(agent: str) -> bool:
    """Toggle the visibility of an agent.

    Args:
        agent: Agent name to toggle.

    Returns:
        True if the agent is now hidden, False if now visible.
    """
    return _get_agent_store().toggle(agent)


def is_agent_hidden(agent: str) -> bool:
    """Check if an agent is hidden.

    Args:
        agent: Agent name to check.

    Returns:
        True if agent is hidden, False otherwise.
    """
    return _get_agent_store().is_hidden(agent)


def prune_stale_agent_entries(all_agent_names: Iterable[str]) -> set[str]:
    """Remove hidden agent entries that are no longer valid.

    Args:
        all_agent_names: Iterable of currently valid agent names.

    Returns:
        Set of removed (stale) agent names. Empty if nothing changed.
    """
    return _get_agent_store().prune_stale(all_agent_names)


def clear_agent_visibility_config() -> None:
    """Remove the agent visibility config file.

    Idempotent — safe to call even if file doesn't exist.
    """
    _get_agent_store().clear()
