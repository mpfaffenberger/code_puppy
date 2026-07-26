"""Atomic sidecar persistence for conversation trees.

The normal Code Puppy session pickle remains linear for backwards
compatibility.  A sibling tree sidecar retains inactive branches; if it is
missing or unreadable, the plugin simply rebuilds from linear history.
"""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from typing import Optional

from code_puppy.plugins.tree.tree_model import ConversationTree


def storage_path(session_name: str, agent_name: str) -> Path:
    from code_puppy.config import AUTOSAVE_DIR

    agent_key = hashlib.sha256(agent_name.encode("utf-8")).hexdigest()[:12]
    return Path(AUTOSAVE_DIR) / "trees" / f"{session_name}_{agent_key}.pkl"


def load_tree(session_name: str, agent_name: str) -> Optional[ConversationTree]:
    path = storage_path(session_name, agent_name)
    if not path.is_file():
        return None
    try:
        value = pickle.loads(path.read_bytes())  # noqa: S301
    except Exception:
        return None
    return value if isinstance(value, ConversationTree) else None


def save_tree(session_name: str, agent_name: str, tree: ConversationTree) -> bool:
    path = storage_path(session_name, agent_name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(pickle.dumps(tree, protocol=pickle.HIGHEST_PROTOCOL))
        temporary.replace(path)
        return True
    except Exception:
        # Losing optional branch metadata is preferable to breaking autosave or
        # the active conversation because a cache directory became read-only.
        return False


__all__ = ["load_tree", "save_tree", "storage_path"]
