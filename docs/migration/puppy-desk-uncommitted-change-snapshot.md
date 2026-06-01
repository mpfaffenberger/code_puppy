# Puppy Desk Migration — Uncommitted Change Snapshot

Purpose: preserve and document existing uncommitted app-code changes on `feature/puppy-desk-migration` before Gate 2.

Generated: 2026-06-01T15:15:33Z

## Branch and status
```text
feature/puppy-desk-migration
 M code_puppy/config.py
 M code_puppy/plugins/frontend_emitter/emitter.py
 M code_puppy/session_storage.py
 M code_puppy/tools/command_runner.py
 M pyproject.toml
 M uv.lock
?? docs/migration/
```

## Diff stat
```text
 code_puppy/config.py                           |  44 ++-
 code_puppy/plugins/frontend_emitter/emitter.py |  13 +-
 code_puppy/session_storage.py                  | 464 ++++++++++---------------
 code_puppy/tools/command_runner.py             | 372 ++++++++++++++------
 pyproject.toml                                 |   6 +
 uv.lock                                        | 220 ++++++++++++
 6 files changed, 715 insertions(+), 404 deletions(-)
```

## File-level notes

| File | Observed status | Migration handling |
|---|---|---|
| `code_puppy/config.py` | Modified; includes config/schema/default differences vs source branch | Preserve and reconcile intentionally; do not overwrite wholesale |
| `code_puppy/plugins/frontend_emitter/emitter.py` | Modified; current/external ContextVar-capable emitter direction | Preserve as base; ensure strict live session filtering |
| `code_puppy/session_storage.py` | Modified relative to branch, but source/current comparison previously showed same as source | Preserve until inspected; likely session compatibility work |
| `code_puppy/tools/command_runner.py` | Modified; observed callback import fallback | Preserve unless tests show callback breakage |
| `pyproject.toml` | Modified dependency/project config | Preserve; requires Snyk scan before test phase if dependency changes remain |
| `uv.lock` | Modified lockfile | Preserve; requires Snyk scan before test phase if dependency changes remain |

## Detailed diff excerpts / full current diff for tracked modified files

> This section intentionally captures the current tracked diff so it can be recovered if later work accidentally overwrites it.

```diff
diff --git a/code_puppy/config.py b/code_puppy/config.py
index 997d7935..a2d058b8 100644
--- a/code_puppy/config.py
+++ b/code_puppy/config.py
@@ -48,18 +48,38 @@ EXTRA_MODELS_FILE = os.path.join(DATA_DIR, "extra_models.json")
 AGENTS_DIR = os.path.join(DATA_DIR, "agents")
 SKILLS_DIR = os.path.join(DATA_DIR, "skills")
 CONTEXTS_DIR = os.path.join(DATA_DIR, "contexts")
-
-# OAuth plugin model files (XDG_DATA_HOME)
-GEMINI_MODELS_FILE = os.path.join(DATA_DIR, "gemini_models.json")
-CHATGPT_MODELS_FILE = os.path.join(DATA_DIR, "chatgpt_models.json")
-CLAUDE_MODELS_FILE = os.path.join(DATA_DIR, "claude_models.json")
-COPILOT_MODELS_FILE = os.path.join(DATA_DIR, "copilot_models.json")
+_DEFAULT_SQLITE_FILE = os.path.join(DATA_DIR, "dbos_store.sqlite")
 
 # Cache files (XDG_CACHE_HOME)
 AUTOSAVE_DIR = os.path.join(CACHE_DIR, "autosaves")
+WS_SESSION_DIR = os.path.join(CACHE_DIR, "ws_sessions")
+
+def get_ws_sessions_dir() -> pathlib.Path:
+    """Return the ws_sessions directory path and ensure it exists."""
+    p = pathlib.Path(WS_SESSION_DIR)
+    p.mkdir(parents=True, exist_ok=True, mode=0o700)
+    return p
 
 # State files (XDG_STATE_HOME)
 COMMAND_HISTORY_FILE = os.path.join(STATE_DIR, "command_history.txt")
+DBOS_DATABASE_URL = os.environ.get(
+    "DBOS_SYSTEM_DATABASE_URL", f"sqlite:///{_DEFAULT_SQLITE_FILE}"
+)
+# DBOS enable switch is controlled solely via puppy.cfg using key 'enable_dbos'.
+# Default: True (DBOS enabled) unless explicitly disabled.
+
+def get_use_dbos() -> bool:
+    """Return True if DBOS should be used based on 'enable_dbos' (default True)."""
+    cfg_val = get_value("enable_dbos")
+    if cfg_val is None:
+        return True
+    return str(cfg_val).strip().lower() in {"1", "true", "yes", "on"}
+
+# OAuth plugin model files (XDG_DATA_HOME)
+GEMINI_MODELS_FILE = os.path.join(DATA_DIR, "gemini_models.json")
+CHATGPT_MODELS_FILE = os.path.join(DATA_DIR, "chatgpt_models.json")
+CLAUDE_MODELS_FILE = os.path.join(DATA_DIR, "claude_models.json")
+COPILOT_MODELS_FILE = os.path.join(DATA_DIR, "copilot_models.json")
 
 
 def get_subagent_verbose() -> bool:
@@ -184,6 +204,18 @@ def get_enable_streaming() -> bool:
     return str(val).lower() in ("1", "true", "yes", "on")
 
 
+def get_command_timeout_seconds() -> int:
+    """Return shell command timeout in seconds (default: 30)."""
+    val = get_value("command_timeout_seconds")
+    if val is None:
+        return 30
+    try:
+        parsed = int(str(val).strip())
+    except (ValueError, TypeError):
+        return 30
+    return max(1, parsed)
+
+
 DEFAULT_SECTION = "puppy"
 REQUIRED_KEYS = ["puppy_name", "owner_name"]
 
diff --git a/code_puppy/plugins/frontend_emitter/emitter.py b/code_puppy/plugins/frontend_emitter/emitter.py
index 55836d90..cd0ffab6 100644
--- a/code_puppy/plugins/frontend_emitter/emitter.py
+++ b/code_puppy/plugins/frontend_emitter/emitter.py
@@ -234,17 +234,20 @@ def unsubscribe(queue: "asyncio.Queue[Dict[str, Any]]") -> None:
     )
 
 
-def get_recent_events() -> List[Dict[str, Any]]:
+def get_recent_events(session_id: Optional[str] = None) -> List[Dict[str, Any]]:
     """Get recent events for new subscribers.
 
-    Returns a copy of the most recent events (up to
-    ``frontend_emitter_max_recent_events``).  Useful for letting new
-    WebSocket connections "catch up" on recent activity.
+    Args:
+        session_id: Optional session filter. If provided, only events whose
+            ``event["session_id"] == session_id`` are returned.
 
     Returns:
         A list of recent event dictionaries.
     """
-    return _recent_events.copy()
+    events = _recent_events.copy()
+    if session_id is None:
+        return events
+    return [e for e in events if e.get("session_id") == session_id]
 
 
 def get_subscriber_count() -> int:
diff --git a/code_puppy/session_storage.py b/code_puppy/session_storage.py
index d8b9201c..ab9a849b 100644
--- a/code_puppy/session_storage.py
+++ b/code_puppy/session_storage.py
@@ -1,338 +1,238 @@
 """Shared helpers for persisting and restoring chat sessions.
 
-This module centralises the pickle + metadata handling that used to live in
-both the CLI command handler and the auto-save feature. Keeping it here helps
-us avoid duplication while staying inside the Zen-of-Python sweet spot: simple
-is better than complex, nested side effects are worse than deliberate helpers.
+MIGRATION NOTE: Pickle-based storage has been removed. All sessions are now
+persisted exclusively to SQLite via code_puppy.api.db.queries.
+This module retains only stateless helpers (title generation) and stubs for
+removed functionality to maintain import compatibility during the transition.
 """
 
 from __future__ import annotations
 
 import json
-import pickle
+import re
 from dataclasses import dataclass
 from pathlib import Path
-from typing import Any, Callable, List
+from typing import Any, List
 
-
-def _safe_loads(data: bytes) -> Any:
-    """Deserialize pickle data."""
-    return pickle.loads(data)  # noqa: S301
-
-
-_LEGACY_SIGNED_HEADER = b"CPSESSION\x01"
-_LEGACY_SIGNATURE_SIZE = (
-    32  # legacy signature bytes, retained only for backward-compat parsing
-)
+from pydantic import TypeAdapter
+from pydantic_ai.messages import ModelMessage
 
 SessionHistory = List[Any]
-TokenEstimator = Callable[[Any], int]
-
 
-@dataclass(slots=True)
-class SessionPaths:
-    pickle_path: Path
-    metadata_path: Path
 
-
-@dataclass(slots=True)
+@dataclass
 class SessionMetadata:
-    session_name: str
-    timestamp: str
+    """Metadata returned after saving a session."""
+
     message_count: int
     total_tokens: int
-    pickle_path: Path
-    metadata_path: Path
-    auto_saved: bool = False
-
-    def as_serialisable(self) -> dict[str, Any]:
-        return {
-            "session_name": self.session_name,
-            "timestamp": self.timestamp,
-            "message_count": self.message_count,
-            "total_tokens": self.total_tokens,
-            "file_path": str(self.pickle_path),
-            "auto_saved": self.auto_saved,
-        }
-
-
-def _extract_pickle_payload(raw: bytes) -> bytes:
-    """Return the pickle payload from raw session file bytes.
-
-    New format is raw pickle bytes.
-    Legacy format was: header + 32-byte signature + pickle payload.
-    We no longer verify or generate signatures.
-    """
-    if raw.startswith(_LEGACY_SIGNED_HEADER):
-        offset = len(_LEGACY_SIGNED_HEADER) + _LEGACY_SIGNATURE_SIZE
-        return raw[offset:]
-    return raw
+    pickle_path: Path  # Kept for compatibility, points to .json file
+    metadata_path: Path  # Points to .json file (same as above)
 
 
-def ensure_directory(path: Path) -> Path:
-    path.mkdir(parents=True, exist_ok=True)
-    return path
+def generate_heuristic_title(history: SessionHistory, max_length: int = 50) -> str:
+    """Generate a short title from the first user message in the history.
 
+    Extracts the first user message, takes the first ~50 chars, and converts
+    to a filename-safe format (lowercase, spaces to hyphens, remove special chars).
 
-def build_session_paths(base_dir: Path, session_name: str) -> SessionPaths:
-    pickle_path = base_dir / f"{session_name}.pkl"
-    metadata_path = base_dir / f"{session_name}_meta.json"
-    return SessionPaths(pickle_path=pickle_path, metadata_path=metadata_path)
+    Handles multiple message formats:
+    1. Pydantic-ai format: msg.kind == 'request' with msg.parts[].content
+    2. Enhanced/wrapped format: {'msg': <pydantic-ai message>, 'agent': str, ...}
+    3. Simple dict format: {'role': 'user', 'content': str}
+    """
+
+    def extract_user_content(msg: Any) -> str | None:
+        """Extract user message content from various message formats."""
+        # Handle wrapped/enhanced format: {'msg': <actual message>, 'agent': ...}
+        if isinstance(msg, dict) and "msg" in msg:
+            msg = msg["msg"]
+
+        # Handle pydantic-ai format: msg.kind == 'request'
+        if hasattr(msg, "kind") and msg.kind == "request":
+            for part in getattr(msg, "parts", []):
+                if hasattr(part, "content") and isinstance(part.content, str):
+                    content = part.content.strip()
+                    if content:
+                        return content
+
+        # Handle simple dict format: {'role': 'user', 'content': str}
+        if isinstance(msg, dict):
+            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
+                content = msg["content"].strip()
+                if content:
+                    return content
+
+        return None
+
+    def content_to_title(content: str) -> str:
+        """Convert content to a filename-safe kebab-case title."""
+        # Take first line or first max_length chars
+        first_line = content.split("\n")[0][:max_length]
+        # Convert to kebab-case filename-safe format
+        title = first_line.lower()
+        title = re.sub(r"[^a-z0-9\s-]", "", title)  # Remove special chars
+        title = re.sub(r"\s+", "-", title)  # Spaces to hyphens
+        title = re.sub(r"-+", "-", title)  # Collapse multiple hyphens
+        title = title.strip("-")[:max_length]
+        return title
+
+    # Find first user message
+    for msg in history:
+        content = extract_user_content(msg)
+        if content:
+            title = content_to_title(content)
+            return title if title else "untitled-session"
+
+    return "untitled-session"
+
+
+# ---------------------------------------------------------------------------
+# Deprecated / Removed Pickle Functionality -> Replaced with JSON for Export
+# ---------------------------------------------------------------------------
 
 
 def save_session(
-    *,
     history: SessionHistory,
     session_name: str,
     base_dir: Path,
-    timestamp: str,
-    token_estimator: TokenEstimator,
-    auto_saved: bool = False,
+    timestamp: str | None = None,
+    token_estimator: Any | None = None,
+    **kwargs: Any,
 ) -> SessionMetadata:
-    ensure_directory(base_dir)
-    paths = build_session_paths(base_dir, session_name)
-
-    pickle_data = pickle.dumps(history)
-    tmp_pickle = paths.pickle_path.with_suffix(".tmp")
-    with tmp_pickle.open("wb") as pickle_file:
-        pickle_file.write(pickle_data)
-    tmp_pickle.replace(paths.pickle_path)
-
-    total_tokens = sum(token_estimator(message) for message in history)
-    metadata = SessionMetadata(
-        session_name=session_name,
-        timestamp=timestamp,
+    """Save session history to a JSON file (replacing legacy pickle).
+
+    This is used for 'pinning' or exporting sessions via /dump_context.
+    """
+    base_dir.mkdir(parents=True, exist_ok=True)
+    file_path = base_dir / f"{session_name}.json"
+
+    # Try to serialize the history, handling mixed types:
+    # - ModelMessage objects: serialize via Pydantic
+    # - System dicts: serialize as plain dicts
+    try:
+        from pydantic_ai.messages import ModelMessagesTypeAdapter
+
+        history_data = []
+        for item in history:
+            # Unwrap from {msg: ..., agent: ..., ts: ...} wrapper if present
+            if isinstance(item, dict) and "msg" in item:
+                inner = item["msg"]
+                wrapper_meta = {k: v for k, v in item.items() if k != "msg"}
+
+                # Check if inner is a ModelMessage (has 'parts' attribute)
+                if hasattr(inner, "parts"):
+                    # Serialize ModelMessage, then add wrapper metadata
+                    try:
+                        serialized = ModelMessagesTypeAdapter.dump_python(
+                            [inner], mode="json"
+                        )[0]
+                        serialized["_wrapper"] = wrapper_meta
+                        history_data.append(serialized)
+                    except Exception:
+                        # Fallback: keep as-is
+                        history_data.append(item)
+                else:
+                    # It's a system dict like {msg: 'system', ...} - keep as-is
+                    history_data.append(item)
+            elif hasattr(item, "parts"):
+                # Direct ModelMessage without wrapper
+                try:
+                    serialized = ModelMessagesTypeAdapter.dump_python(
+                        [item], mode="json"
+                    )[0]
+                    history_data.append(serialized)
+                except Exception:
+                    history_data.append({"_raw": str(item)})
+            else:
+                # Unknown type - keep as-is
+                history_data.append(item)
+
+        json_bytes = json.dumps(history_data, indent=2, default=str).encode("utf-8")
+    except Exception:
+        # Fallback: generic JSON dump
+        json_bytes = json.dumps(history, default=str, indent=2).encode("utf-8")
+
+    file_path.write_bytes(json_bytes)
+
+    # Calculate tokens if estimator provided
+    total_tokens = 0
+    if token_estimator:
+        for msg in history:
+            try:
+                # estimator might expect the original object or dict
+                total_tokens += token_estimator(msg)
+            except Exception:
+                pass
+
+    return SessionMetadata(
         message_count=len(history),
         total_tokens=total_tokens,
-        pickle_path=paths.pickle_path,
-        metadata_path=paths.metadata_path,
-        auto_saved=auto_saved,
+        pickle_path=file_path,
+        metadata_path=file_path,
     )
 
-    tmp_metadata = paths.metadata_path.with_suffix(".tmp")
-    with tmp_metadata.open("w", encoding="utf-8") as metadata_file:
-        json.dump(metadata.as_serialisable(), metadata_file, indent=2)
-    tmp_metadata.replace(paths.metadata_path)
-
-    return metadata
-
 
 def load_session(
     session_name: str, base_dir: Path, *, allow_legacy: bool = False
 ) -> SessionHistory:
-    # Kept for API compatibility; legacy loading is always supported now.
-    _ = allow_legacy
+    """Load session history from a JSON file."""
+    file_path = base_dir / f"{session_name}.json"
+    if not file_path.exists():
+        # Fallback check for legacy .pkl if explicitly requested?
+        legacy_path = base_dir / f"{session_name}.pkl"
+        if allow_legacy and legacy_path.exists():
+            raise NotImplementedError(
+                f"Found legacy pickle at {legacy_path} but pickle loading is removed."
+            )
+        raise FileNotFoundError(f"Session file not found: {file_path}")
 
-    paths = build_session_paths(base_dir, session_name)
-    if not paths.pickle_path.exists():
-        raise FileNotFoundError(paths.pickle_path)
+    json_data = file_path.read_bytes()
 
-    raw = paths.pickle_path.read_bytes()
-    pickle_data = _extract_pickle_payload(raw)
-    return _safe_loads(pickle_data)
+    # Try to load as ModelMessage objects
+    try:
+        adapter = TypeAdapter(List[ModelMessage])
+        return adapter.validate_json(json_data)
+    except Exception:
+        # Fallback: return as list of dicts
+        return json.loads(json_data)
 
 
 def list_sessions(base_dir: Path) -> List[str]:
+    """List available JSON sessions."""
     if not base_dir.exists():
         return []
-    return sorted(path.stem for path in base_dir.glob("*.pkl"))
+    return sorted([p.stem for p in base_dir.glob("*.json")])
 
 
 def cleanup_sessions(base_dir: Path, max_sessions: int) -> List[str]:
-    if max_sessions <= 0:
-        return []
+    """Cleanup old sessions if count exceeds max_sessions.
 
-    if not base_dir.exists():
-        return []
-
-    candidate_paths = list(base_dir.glob("*.pkl"))
-    if len(candidate_paths) <= max_sessions:
-        return []
-
-    sorted_candidates = sorted(
-        ((path.stat().st_mtime, path) for path in candidate_paths),
-        key=lambda item: item[0],
-    )
-
-    stale_entries = sorted_candidates[:-max_sessions]
-    removed_sessions: List[str] = []
-    for _, pickle_path in stale_entries:
-        metadata_path = base_dir / f"{pickle_path.stem}_meta.json"
-        try:
-            pickle_path.unlink(missing_ok=True)
-            metadata_path.unlink(missing_ok=True)
-            removed_sessions.append(pickle_path.stem)
-        except OSError:
-            continue
-
-    return removed_sessions
-
-
-async def restore_autosave_interactively(base_dir: Path) -> None:
-    """Prompt the user to load an autosave session from base_dir, if any exist.
-
-    This helper is deliberately placed in session_storage to keep autosave
-    restoration close to the persistence layer. It uses the same public APIs
-    (list_sessions, load_session) and mirrors the interactive behaviours from
-    the command handler.
+    Returns list of removed session names.
     """
-    sessions = list_sessions(base_dir)
-    if not sessions:
-        return
-
-    # Import locally to avoid pulling the messaging layer into storage modules
-    from datetime import datetime
+    if not base_dir.exists() or max_sessions <= 0:
+        return []
 
-    from prompt_toolkit.formatted_text import FormattedText
+    sessions = sorted(base_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
 
-    from code_puppy.agents.agent_manager import get_current_agent
-    from code_puppy.command_line.prompt_toolkit_completion import (
-        get_input_with_combined_completion,
-    )
-    from code_puppy.messaging import emit_success, emit_system_message, emit_warning
-
-    entries = []
-    for name in sessions:
-        meta_path = base_dir / f"{name}_meta.json"
-        try:
-            with meta_path.open("r", encoding="utf-8") as meta_file:
-                data = json.load(meta_file)
-            timestamp = data.get("timestamp")
-            message_count = data.get("message_count")
-        except Exception:
-            timestamp = None
-            message_count = None
-        entries.append((name, timestamp, message_count))
-
-    def sort_key(entry):
-        _, timestamp, _ = entry
-        if timestamp:
+    removed = []
+    if len(sessions) > max_sessions:
+        to_remove = sessions[: len(sessions) - max_sessions]
+        for p in to_remove:
             try:
-                return datetime.fromisoformat(timestamp)
-            except ValueError:
-                return datetime.min
-        return datetime.min
-
-    entries.sort(key=sort_key, reverse=True)
-
-    PAGE_SIZE = 5
-    total = len(entries)
-    page = 0
-
-    def render_page() -> None:
-        start = page * PAGE_SIZE
-        end = min(start + PAGE_SIZE, total)
-        page_entries = entries[start:end]
-        emit_system_message("Autosave Sessions Available:")
-        for idx, (name, timestamp, message_count) in enumerate(page_entries, start=1):
-            timestamp_display = timestamp or "unknown time"
-            message_display = (
-                f"{message_count} messages"
-                if message_count is not None
-                else "unknown size"
-            )
-            emit_system_message(
-                f"  [{idx}] {name} ({message_display}, saved at {timestamp_display})"
-            )
-        # If there are more pages, offer next-page; show 'Return to first page' on last page
-        if total > PAGE_SIZE:
-            page_count = (total + PAGE_SIZE - 1) // PAGE_SIZE
-            is_last_page = (page + 1) >= page_count
-            remaining = total - (page * PAGE_SIZE + len(page_entries))
-            summary = (
-                f" and {remaining} more" if (remaining > 0 and not is_last_page) else ""
-            )
-            label = "Return to first page" if is_last_page else f"Next page{summary}"
-            emit_system_message(f"  [6] {label}")
-        emit_system_message("  [Enter] Skip loading autosave")
-
-    chosen_name: str | None = None
-
-    while True:
-        render_page()
-        try:
-            selection = await get_input_with_combined_completion(
-                FormattedText(
-                    [
-                        (
-                            "class:prompt",
-                            "Pick 1-5 to load, 6 for next, or name/Enter: ",
-                        )
-                    ]
-                )
-            )
-        except (KeyboardInterrupt, EOFError):
-            emit_warning("Autosave selection cancelled")
-            return
-
-        selection = (selection or "").strip()
-        if not selection:
-            return
-
-        # Numeric choice: 1-5 select within current page; 6 advances page
-        if selection.isdigit():
-            num = int(selection)
-            if num == 6 and total > PAGE_SIZE:
-                page = (page + 1) % ((total + PAGE_SIZE - 1) // PAGE_SIZE)
-                # loop and re-render next page
-                continue
-            if 1 <= num <= 5:
-                start = page * PAGE_SIZE
-                idx = start + (num - 1)
-                if 0 <= idx < total:
-                    chosen_name = entries[idx][0]
-                    break
-                else:
-                    emit_warning("Invalid selection for this page")
-                    continue
-            emit_warning("Invalid selection; choose 1-5 or 6 for next")
-            continue
-
-        # Allow direct typing by exact session name
-        for name, _ts, _mc in entries:
-            if name == selection:
-                chosen_name = name
-                break
-        if chosen_name:
-            break
-        emit_warning("No autosave loaded (invalid selection)")
-        # keep looping and allow another try
-
-    if not chosen_name:
-        return
+                p.unlink()
+                removed.append(p.stem)
+            except Exception:
+                pass
 
-    try:
-        history = load_session(chosen_name, base_dir)
-    except FileNotFoundError:
-        emit_warning(f"Autosave '{chosen_name}' could not be found")
-        return
-    except Exception as exc:
-        emit_warning(f"Failed to load autosave '{chosen_name}': {exc}")
-        return
-
-    agent = get_current_agent()
-    agent.set_message_history(history)
-
-    # Set current autosave session id so subsequent autosaves overwrite this session
-    try:
-        from code_puppy.config import set_current_autosave_from_session_name
+    return removed
 
-        set_current_autosave_from_session_name(chosen_name)
-    except Exception:
-        pass
-
-    total_tokens = sum(agent.estimate_tokens_for_message(msg) for msg in history)
 
-    session_path = base_dir / f"{chosen_name}.pkl"
-    emit_success(
-        f"✅ Autosave loaded: {len(history)} messages ({total_tokens} tokens)\n"
-        f"📁 From: {session_path}"
-    )
+async def restore_autosave_interactively(base_dir: Path) -> None:
+    """Deprecated: No-op."""
+    pass
 
-    # Display recent message history for context
-    try:
-        from code_puppy.command_line.autosave_menu import display_resumed_history
 
-        display_resumed_history(history)
-    except Exception:
-        pass  # Don't fail if display doesn't work in non-TTY environment
+def build_session_paths(base_dir: Path, session_name: str) -> Any:
+    """Deprecated: Returns None or raises."""
+    raise NotImplementedError("Session paths are no longer used.")
diff --git a/code_puppy/tools/command_runner.py b/code_puppy/tools/command_runner.py
index af67632c..ff03cd23 100644
--- a/code_puppy/tools/command_runner.py
+++ b/code_puppy/tools/command_runner.py
@@ -1,4 +1,5 @@
 import asyncio
+import contextvars
 import ctypes
 import os
 import select
@@ -11,6 +12,7 @@ import time
 import traceback
 from concurrent.futures import ThreadPoolExecutor
 from contextlib import contextmanager
+from contextvars import ContextVar
 from functools import partial
 from typing import Callable, List, Literal, Optional, Set
 
@@ -18,6 +20,12 @@ from pydantic import BaseModel
 from pydantic_ai import RunContext
 from rich.text import Text
 
+try:
+    from code_puppy.callbacks import on_run_shell_command_output
+except ImportError:
+    async def on_run_shell_command_output(*args, **kwargs):
+        return []
+from code_puppy.config import get_command_timeout_seconds
 from code_puppy.messaging import (  # Structured messaging types
     AgentReasoningMessage,
     ShellOutputMessage,
@@ -99,17 +107,104 @@ else:
 
 _AWAITING_USER_INPUT = threading.Event()
 
-# NOTE: The previous module-level ``_CONFIRMATION_LOCK`` was removed --
-# queueing of parallel approval prompts now lives inside
-# ``get_user_approval_async`` itself, so every caller (shell commands,
-# destructive-command guard, force-push guard, ...) benefits without
-# bolting on their own lock.
+_CONFIRMATION_LOCK = threading.Lock()
 
 # Track running shell processes so we can kill them on Ctrl-C from the UI
 _RUNNING_PROCESSES: Set[subprocess.Popen] = set()
 _RUNNING_PROCESSES_LOCK = threading.Lock()
 _USER_KILLED_PROCESSES = set()
 
+# Per-session process tracking via ContextVar
+_session_running_processes: ContextVar[Optional[Set[subprocess.Popen]]] = ContextVar(
+    "session_running_processes", default=None
+)
+_session_killed_processes: ContextVar[Optional[Set[int]]] = ContextVar(
+    "session_killed_processes", default=None
+)
+_session_awaiting_input: ContextVar[Optional[threading.Event]] = ContextVar(
+    "session_awaiting_input", default=None
+)
+
+
+def _get_running_processes() -> Set[subprocess.Popen]:
+    """Get the running processes set for the current session context."""
+    session_set = _session_running_processes.get(None)
+    if session_set is not None:
+        return session_set
+    return _RUNNING_PROCESSES
+
+
+def _get_killed_processes() -> Set[int]:
+    """Get the killed processes set for the current session context."""
+    session_set = _session_killed_processes.get(None)
+    if session_set is not None:
+        return session_set
+    return _USER_KILLED_PROCESSES
+
+
+def _get_awaiting_input_event() -> threading.Event:
+    """Get the awaiting-input event for the current session context."""
+    session_evt = _session_awaiting_input.get(None)
+    if session_evt is not None:
+        return session_evt
+    return _AWAITING_USER_INPUT
+
+
+def init_session_process_tracking() -> None:
+    """Initialize per-session process tracking. Call at WS session start."""
+    _session_running_processes.set(set())
+    _session_killed_processes.set(set())
+    _session_awaiting_input.set(threading.Event())
+    _session_active_stop_events.set(set())
+    _session_keyboard_refcount.set(0)
+    _session_ctrl_x_stop_event.set(None)
+    _session_ctrl_x_thread.set(None)
+
+
+def cleanup_session_process_tracking() -> None:
+    """Tear down per-session process tracking. Call at WS session end.
+
+    Kills any still-running session processes, then clears the per-session
+    process and killed-process sets to release any held Popen references.
+    """
+    # Kill any still-running session processes first
+    session_procs = _session_running_processes.get(None)
+    if session_procs is not None:
+        for p in list(session_procs):
+            try:
+                if p.poll() is None:
+                    _kill_process_group(p)
+            except Exception:
+                pass
+        session_procs.clear()
+    session_killed = _session_killed_processes.get(None)
+    if session_killed is not None:
+        session_killed.clear()
+    session_stop = _session_active_stop_events.get(None)
+    if session_stop is not None:
+        for evt in session_stop:
+            evt.set()  # Signal before discarding!
+        session_stop.clear()
+    # Clean up keyboard context
+    session_ctrl_x = _session_ctrl_x_stop_event.get(None)
+    if session_ctrl_x is not None:
+        session_ctrl_x.set()  # Signal stop
+    session_thread = _session_ctrl_x_thread.get(None)
+    if session_thread is not None and session_thread.is_alive():
+        try:
+            session_thread.join(timeout=0.2)
+        except Exception:
+            pass
+    _session_keyboard_refcount.set(None)
+    _session_ctrl_x_stop_event.set(None)
+    _session_ctrl_x_thread.set(None)
+    # Reset to None so subsequent calls fall back to global
+    _session_running_processes.set(None)
+    _session_killed_processes.set(None)
+    _session_awaiting_input.set(None)
+    _session_active_stop_events.set(None)
+
+
 # Global state for shell command keyboard handling
 _SHELL_CTRL_X_STOP_EVENT: Optional[threading.Event] = None
 _SHELL_CTRL_X_THREAD: Optional[threading.Thread] = None
@@ -119,23 +214,97 @@ _ORIGINAL_SIGINT_HANDLER = None
 _KEYBOARD_CONTEXT_REFCOUNT = 0
 _KEYBOARD_CONTEXT_LOCK = threading.Lock()
 
+# Per-session keyboard context refcount (ContextVar for WS session isolation)
+_session_keyboard_refcount: ContextVar[Optional[int]] = ContextVar(
+    "session_keyboard_refcount", default=None
+)
+_session_ctrl_x_stop_event: ContextVar[Optional[threading.Event]] = ContextVar(
+    "session_ctrl_x_stop_event", default=None
+)
+_session_ctrl_x_thread: ContextVar[Optional[threading.Thread]] = ContextVar(
+    "session_ctrl_x_thread", default=None
+)
+
 # Thread-safe registry of active stop events for concurrent shell commands
 _ACTIVE_STOP_EVENTS: Set[threading.Event] = set()
 _ACTIVE_STOP_EVENTS_LOCK = threading.Lock()
 
+# Per-session stop events (ContextVar for session isolation)
+_session_active_stop_events: ContextVar[Optional[Set[threading.Event]]] = ContextVar(
+    "session_active_stop_events", default=None
+)
+
+
+def _get_keyboard_refcount() -> int:
+    """Get keyboard context refcount for the current session."""
+    session_val = _session_keyboard_refcount.get(None)
+    if session_val is not None:
+        return session_val
+    return _KEYBOARD_CONTEXT_REFCOUNT
+
+
+def _set_keyboard_refcount(value: int) -> None:
+    """Set keyboard context refcount for the current session."""
+    if _session_keyboard_refcount.get(None) is not None:
+        _session_keyboard_refcount.set(value)
+    else:
+        global _KEYBOARD_CONTEXT_REFCOUNT
+        _KEYBOARD_CONTEXT_REFCOUNT = value
+
+
+def _get_ctrl_x_stop_event() -> Optional[threading.Event]:
+    """Get Ctrl+X stop event for the current session."""
+    session_evt = _session_ctrl_x_stop_event.get(None)
+    if session_evt is not None:
+        return session_evt
+    return _SHELL_CTRL_X_STOP_EVENT
+
+
+def _get_ctrl_x_thread() -> Optional[threading.Thread]:
+    """Get Ctrl+X thread for the current session."""
+    session_thread = _session_ctrl_x_thread.get(None)
+    if session_thread is not None:
+        return session_thread
+    return _SHELL_CTRL_X_THREAD
+
+
+def _get_active_stop_events() -> Set[threading.Event]:
+    """Get the active stop events set for the current session context."""
+    session_set = _session_active_stop_events.get(None)
+    if session_set is not None:
+        return session_set
+    return _ACTIVE_STOP_EVENTS
+
+
+@contextmanager
+def _guarded_set(collection, global_ref, lock):
+    """Acquire *lock* only when *collection* is the shared global *global_ref*.
+
+    Per-session sets (ContextVar-backed) are single-writer within their
+    asyncio task context and don't need locking.
+    """
+    if collection is global_ref:
+        with lock:
+            yield collection
+    else:
+        yield collection
+
+
 # Thread pool for running blocking shell commands without blocking the event loop
 # This allows multiple sub-agents to run shell commands in parallel
 _SHELL_EXECUTOR = ThreadPoolExecutor(max_workers=16, thread_name_prefix="shell_cmd_")
 
 
 def _register_process(proc: subprocess.Popen) -> None:
-    with _RUNNING_PROCESSES_LOCK:
-        _RUNNING_PROCESSES.add(proc)
+    procs = _get_running_processes()
+    with _guarded_set(procs, _RUNNING_PROCESSES, _RUNNING_PROCESSES_LOCK):
+        procs.add(proc)
 
 
 def _unregister_process(proc: subprocess.Popen) -> None:
-    with _RUNNING_PROCESSES_LOCK:
-        _RUNNING_PROCESSES.discard(proc)
+    procs = _get_running_processes()
+    with _guarded_set(procs, _RUNNING_PROCESSES, _RUNNING_PROCESSES_LOCK):
+        procs.discard(proc)
 
 
 def _kill_process_group(proc: subprocess.Popen) -> None:
@@ -211,13 +380,16 @@ def kill_all_running_shell_processes() -> int:
     Returns the number of processes signaled.
     """
     # Signal all active reader threads to stop
-    with _ACTIVE_STOP_EVENTS_LOCK:
-        for evt in _ACTIVE_STOP_EVENTS:
+    active_stop = _get_active_stop_events()
+    with _guarded_set(active_stop, _ACTIVE_STOP_EVENTS, _ACTIVE_STOP_EVENTS_LOCK):
+        for evt in active_stop:
             evt.set()
 
     procs: list[subprocess.Popen]
-    with _RUNNING_PROCESSES_LOCK:
-        procs = list(_RUNNING_PROCESSES)
+    running = _get_running_processes()
+    killed = _get_killed_processes()
+    with _guarded_set(running, _RUNNING_PROCESSES, _RUNNING_PROCESSES_LOCK):
+        procs = list(running)
     count = 0
     for p in procs:
         try:
@@ -235,7 +407,7 @@ def kill_all_running_shell_processes() -> int:
             if p.poll() is None:
                 _kill_process_group(p)
                 count += 1
-                _USER_KILLED_PROCESSES.add(p.pid)
+                killed.add(p.pid)
         finally:
             _unregister_process(p)
     return count
@@ -243,32 +415,33 @@ def kill_all_running_shell_processes() -> int:
 
 def get_running_shell_process_count() -> int:
     """Return the number of currently-active shell processes being tracked."""
-    with _RUNNING_PROCESSES_LOCK:
+    running = _get_running_processes()
+    with _guarded_set(running, _RUNNING_PROCESSES, _RUNNING_PROCESSES_LOCK):
         alive = 0
         stale: Set[subprocess.Popen] = set()
-        for proc in _RUNNING_PROCESSES:
+        for proc in running:
             if proc.poll() is None:
                 alive += 1
             else:
                 stale.add(proc)
         for proc in stale:
-            _RUNNING_PROCESSES.discard(proc)
+            running.discard(proc)
     return alive
 
 
 # Function to check if user input is awaited
 def is_awaiting_user_input():
     """Check if command_runner is waiting for user input."""
-    return _AWAITING_USER_INPUT.is_set()
+    return _get_awaiting_input_event().is_set()
 
 
 # Function to set user input flag
 def set_awaiting_user_input(awaiting=True):
     """Set the flag indicating if user input is awaited."""
     if awaiting:
-        _AWAITING_USER_INPUT.set()
+        _get_awaiting_input_event().set()
     else:
-        _AWAITING_USER_INPUT.clear()
+        _get_awaiting_input_event().clear()
 
     # When we're setting this flag, also pause/resume all active spinners
     if awaiting:
@@ -330,27 +503,11 @@ def _listen_for_ctrl_x_windows(
     stop_event: threading.Event,
     on_escape: Callable[[], None],
 ) -> None:
-    """Windows-specific Ctrl-X listener.
-
-    Pause-aware: while the agent is paused (Ctrl+T steering), we stop
-    draining ``msvcrt.kbhit()`` so the steering editor can read input
-    cleanly. See the POSIX sibling for the gory details.
-    """
+    """Windows-specific Ctrl-X listener."""
     import msvcrt
     import time
 
-    def _is_agent_paused() -> bool:
-        try:
-            from code_puppy.messaging.pause_controller import get_pause_controller
-
-            return get_pause_controller().is_paused()
-        except Exception:
-            return False
-
     while not stop_event.is_set():
-        if _is_agent_paused():
-            time.sleep(0.05)
-            continue
         try:
             if msvcrt.kbhit():
                 try:
@@ -384,19 +541,10 @@ def _listen_for_ctrl_x_posix(
     stop_event: threading.Event,
     on_escape: Callable[[], None],
 ) -> None:
-    """POSIX-specific Ctrl-X listener.
-
-    Pause-aware: while the ``PauseController`` is paused (Ctrl+T steering),
-    we drop cbreak mode and stop reading stdin so the steering prompt's
-    ``prompt_toolkit.Application`` can own the terminal cleanly. Without
-    this, every other keystroke typed into the steer editor gets eaten by
-    *this* listener's ``stdin.read(1)`` — the user sees half their input.
-    On resume we re-acquire cbreak and continue.
-    """
+    """POSIX-specific Ctrl-X listener."""
     import select
     import sys
     import termios
-    import time
     import tty
 
     stdin = sys.stdin
@@ -409,50 +557,9 @@ def _listen_for_ctrl_x_posix(
     except Exception:
         return
 
-    cbreak_active = False
-
-    def _enter_cbreak() -> None:
-        nonlocal cbreak_active
-        if not cbreak_active:
-            tty.setcbreak(fd)
-            cbreak_active = True
-
-    def _exit_cbreak() -> None:
-        nonlocal cbreak_active
-        if cbreak_active:
-            try:
-                termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)
-            except Exception:
-                pass
-            cbreak_active = False
-
-    def _is_agent_paused() -> bool:
-        """Lazy + exception-safe pause check — never crash the listener."""
-        try:
-            from code_puppy.messaging.pause_controller import get_pause_controller
-
-            return get_pause_controller().is_paused()
-        except Exception:
-            return False
-
     try:
-        _enter_cbreak()
+        tty.setcbreak(fd)
         while not stop_event.is_set():
-            # Pause hand-off: release stdin and park until the steer
-            # prompt finishes. Polling every 50ms keeps stop responsive.
-            if _is_agent_paused():
-                _exit_cbreak()
-                while _is_agent_paused() and not stop_event.is_set():
-                    time.sleep(0.05)
-                if stop_event.is_set():
-                    return
-                try:
-                    _enter_cbreak()
-                except Exception:
-                    # Couldn't re-acquire raw mode — bail rather than spin.
-                    return
-                continue
-
             try:
                 read_ready, _, _ = select.select([stdin], [], [], 0.05)
             except Exception:
@@ -470,11 +577,7 @@ def _listen_for_ctrl_x_posix(
                         "Ctrl+X handler raised unexpectedly; Ctrl+C still works."
                     )
     finally:
-        _exit_cbreak()
-        try:
-            termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)
-        except Exception:
-            pass
+        termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)
 
 
 def _spawn_ctrl_x_key_listener(
@@ -687,13 +790,15 @@ def run_shell_command_streaming(
     silent: bool = False,
 ):
     stop_event = threading.Event()
-    with _ACTIVE_STOP_EVENTS_LOCK:
-        _ACTIVE_STOP_EVENTS.add(stop_event)
+    active_stop = _get_active_stop_events()
+    with _guarded_set(active_stop, _ACTIVE_STOP_EVENTS, _ACTIVE_STOP_EVENTS_LOCK):
+        active_stop.add(stop_event)
 
     start_time = time.time()
     last_output_time = [start_time]
 
-    ABSOLUTE_TIMEOUT_SECONDS = 270
+    # Get the user-configured absolute timeout for shell commands
+    ABSOLUTE_TIMEOUT_SECONDS = get_command_timeout_seconds()
 
     stdout_lines = []
     stderr_lines = []
@@ -963,8 +1068,9 @@ def run_shell_command_streaming(
             )
             get_message_bus().emit(shell_output_msg)
 
-        with _ACTIVE_STOP_EVENTS_LOCK:
-            _ACTIVE_STOP_EVENTS.discard(stop_event)
+        active_stop = _get_active_stop_events()
+        with _guarded_set(active_stop, _ACTIVE_STOP_EVENTS, _ACTIVE_STOP_EVENTS_LOCK):
+            active_stop.discard(stop_event)
 
         if exit_code != 0:
             time.sleep(1)
@@ -978,7 +1084,7 @@ def run_shell_command_streaming(
                 exit_code=exit_code,
                 execution_time=execution_time,
                 timeout=False,
-                user_interrupted=process.pid in _USER_KILLED_PROCESSES,
+                user_interrupted=process.pid in _get_killed_processes(),
             )
 
         return ShellCommandOutput(
@@ -992,8 +1098,9 @@ def run_shell_command_streaming(
         )
 
     except Exception as e:
-        with _ACTIVE_STOP_EVENTS_LOCK:
-            _ACTIVE_STOP_EVENTS.discard(stop_event)
+        active_stop = _get_active_stop_events()
+        with _guarded_set(active_stop, _ACTIVE_STOP_EVENTS, _ACTIVE_STOP_EVENTS_LOCK):
+            active_stop.discard(stop_event)
         return ShellCommandOutput(
             success=False,
             command=command,
@@ -1012,6 +1119,20 @@ async def run_shell_command(
     timeout: int = 60,
     background: bool = False,
 ) -> ShellCommandOutput:
+    # Resolve CWD from the session ContextVar when not explicitly provided.
+    # This supports concurrent WebSocket sessions where each session has its own CWD
+    # without relying on the process-global os.chdir().
+    # Returns None for CLI sessions (subprocess inherits process CWD as normal).
+    if cwd is None:
+        try:
+            from code_puppy.plugins.walmart_specific.session_context import (
+                get_session_working_directory,
+            )
+
+            cwd = get_session_working_directory()
+        except ImportError:
+            pass
+
     # Generate unique group_id for this command execution
     group_id = generate_group_id("shell_command", command)
 
@@ -1140,12 +1261,32 @@ async def run_shell_command(
     # Check if we're running as a sub-agent (skip confirmation and run silently)
     running_as_subagent = is_subagent()
 
+    confirmation_lock_acquired = False
+
+    # Check if WebSocket mode is active (permission handled via WebSocket callbacks)
+    websocket_mode_active = False
+    try:
+        from code_puppy.api.permission_plugin import get_websocket_context
+
+        websocket_mode_active = get_websocket_context() is not None
+    except (ImportError, AttributeError):
+        pass
+
     # Only ask for confirmation if we're in an interactive TTY, not in yolo mode,
-    # and NOT running as a sub-agent (sub-agents run without user interaction)
-    if not yolo_mode and not running_as_subagent and sys.stdin.isatty():
-        # No local lock needed -- get_user_approval_async serializes
-        # parallel prompts internally so the 2nd, 3rd, 4th... destructive
-        # commands queue up cleanly instead of vanishing.
+    # NOT running as a sub-agent, and NOT in WebSocket mode (WebSocket has its own permission system)
+    if (
+        not yolo_mode
+        and not running_as_subagent
+        and not websocket_mode_active
+        and sys.stdin.isatty()
+    ):
+        confirmation_lock_acquired = _CONFIRMATION_LOCK.acquire(blocking=False)
+        if not confirmation_lock_acquired:
+            return ShellCommandOutput(
+                success=False,
+                command=command,
+                error="Another command is currently awaiting confirmation",
+            )
 
         # Get puppy name for personalized messages
         from code_puppy.config import get_puppy_name
@@ -1163,8 +1304,7 @@ async def run_shell_command(
             panel_content.append("📂 Working directory: ", style="dim")
             panel_content.append(cwd, style="dim cyan")
 
-        # Use the common approval function (async version).
-        # Internal queueing means parallel calls wait their turn here.
+        # Use the common approval function (async version)
         confirmed, user_feedback = await get_user_approval_async(
             title="Shell Command",
             content=panel_content,
@@ -1173,6 +1313,10 @@ async def run_shell_command(
             puppy_name=puppy_name,
         )
 
+        # Release lock after approval
+        if confirmation_lock_acquired:
+            _CONFIRMATION_LOCK.release()
+
         if not confirmed:
             if user_feedback:
                 result = ShellCommandOutput(
@@ -1313,9 +1457,13 @@ async def _run_command_inner(
     try:
         # Run the blocking shell command in a thread pool to avoid blocking the event loop
         # This allows multiple sub-agents to run shell commands in parallel
+        # Copy context so ContextVar-based session tracking propagates to the worker thread
+        ctx = contextvars.copy_context()
         return await loop.run_in_executor(
             _SHELL_EXECUTOR,
-            partial(_run_command_sync, command, cwd, timeout, group_id, silent),
+            partial(
+                ctx.run, _run_command_sync, command, cwd, timeout, group_id, silent
+            ),
         )
     except Exception as e:
         if not silent:
@@ -1392,7 +1540,9 @@ def register_agent_run_shell_command(agent):
 
         Supports streaming output, timeout handling, and background execution.
         """
-        return await run_shell_command(context, command, cwd, timeout, background)
+        result = await run_shell_command(context, command, cwd, timeout, background)
+        await on_run_shell_command_output(result)
+        return result
 
 
 def register_agent_share_your_reasoning(agent):
diff --git a/pyproject.toml b/pyproject.toml
index a41eef50..1c433bcc 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -9,6 +9,11 @@ description = "Code generation agent"
 readme = "README.md"
 requires-python = ">=3.11,<3.15"
 dependencies = [
+    "aiosqlite>=0.22.1",
+    "websockets>=12.0",
+    "uvicorn[standard]>=0.27.0",
+    "fastapi>=0.109.0",
+    "dbos>=2.11.0",
     "pydantic-ai-slim[openai,anthropic,mcp]==1.56.0",
     "typer>=0.12.0",
     "mcp>=1.9.4",
@@ -63,6 +68,7 @@ HomePage = "https://github.com/mpfaffenberger/code_puppy"
 [project.scripts]
 code-puppy = "code_puppy.main:main_entry"
 pup = "code_puppy.main:main_entry"
+code-puppy-api = "code_puppy.api.main:main"
 
 [tool.logfire]
 ignore_no_config = true
diff --git a/uv.lock b/uv.lock
index 3d7e28f8..e23624b4 100644
--- a/uv.lock
+++ b/uv.lock
@@ -2,6 +2,15 @@ version = 1
 revision = 3
 requires-python = ">=3.11, <3.15"
 
+[[package]]
+name = "aiosqlite"
+version = "0.22.1"
+source = { registry = "https://pypi.org/simple" }
+sdist = { url = "https://files.pythonhosted.org/packages/4e/8a/64761f4005f17809769d23e518d915db74e6310474e733e3593cfc854ef1/aiosqlite-0.22.1.tar.gz", hash = "sha256:043e0bd78d32888c0a9ca90fc788b38796843360c855a7262a532813133a0650", size = 14821, upload-time = "2025-12-23T19:25:43.997Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/00/b7/e3bf5133d697a08128598c8d0abc5e16377b51465a33756de24fa7dee953/aiosqlite-0.22.1-py3-none-any.whl", hash = "sha256:21c002eb13823fad740196c5a2e9d8e62f6243bd9e7e4a1f87fb5e44ecb4fceb", size = 17405, upload-time = "2025-12-23T19:25:42.139Z" },
+]
+
 [[package]]
 name = "annotated-doc"
 version = "0.0.4"
@@ -303,9 +312,12 @@ name = "code-puppy"
 version = "0.0.527"
 source = { editable = "." }
 dependencies = [
+    { name = "aiosqlite" },
     { name = "anthropic" },
     { name = "azure-identity" },
     { name = "boto3" },
+    { name = "dbos" },
+    { name = "fastapi" },
     { name = "httpx", extra = ["http2"] },
     { name = "json-repair" },
     { name = "mcp" },
@@ -323,6 +335,8 @@ dependencies = [
     { name = "ripgrep" },
     { name = "termflow-md" },
     { name = "typer" },
+    { name = "uvicorn", extra = ["standard"] },
+    { name = "websockets" },
 ]
 
 [package.optional-dependencies]
@@ -344,11 +358,14 @@ dev = [
 
 [package.metadata]
 requires-dist = [
+    { name = "aiosqlite", specifier = ">=0.22.1" },
     { name = "anthropic", specifier = "==0.79.0" },
     { name = "azure-identity", specifier = ">=1.15.0" },
     { name = "boto3", specifier = ">=1.43.9" },
     { name = "boto3", marker = "extra == 'bedrock'", specifier = ">=1.35.0" },
+    { name = "dbos", specifier = ">=2.11.0" },
     { name = "dbos", marker = "extra == 'durable'", specifier = ">=2.11.0" },
+    { name = "fastapi", specifier = ">=0.109.0" },
     { name = "httpx", extras = ["http2"], specifier = ">=0.24.1" },
     { name = "json-repair", specifier = ">=0.46.2" },
     { name = "mcp", specifier = ">=1.9.4" },
@@ -366,6 +383,8 @@ requires-dist = [
     { name = "ripgrep", specifier = "==14.1.0" },
     { name = "termflow-md", specifier = ">=0.1.11" },
     { name = "typer", specifier = ">=0.12.0" },
+    { name = "uvicorn", extras = ["standard"], specifier = ">=0.27.0" },
+    { name = "websockets", specifier = ">=12.0" },
 ]
 provides-extras = ["bedrock", "durable"]
 
@@ -585,6 +604,22 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/a7/5f/ed01f9a3cdffbd5a008556fc7b2a08ddb1cc6ace7effa7340604b1d16699/docstring_parser-0.18.0-py3-none-any.whl", hash = "sha256:b3fcbed555c47d8479be0796ef7e19c2670d428d72e96da63f3a40122860374b", size = 22484, upload-time = "2026-04-14T04:09:18.638Z" },
 ]
 
+[[package]]
+name = "fastapi"
+version = "0.136.3"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "annotated-doc" },
+    { name = "pydantic" },
+    { name = "starlette" },
+    { name = "typing-extensions" },
+    { name = "typing-inspection" },
+]
+sdist = { url = "https://files.pythonhosted.org/packages/81/2d/ff8d91d7b564d464629a0fd50a4489c97fcb836ac230bf3a7269232a9b1f/fastapi-0.136.3.tar.gz", hash = "sha256:e487fae93ad408e6f47641ee4dfe389864fd7bec92e547ea8498fc13f43e83ab", size = 396410, upload-time = "2026-05-23T18:53:15.192Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/e0/82/45359b62a067409bd929ae8a56b8ed13e5a8c8a61194b3c236920999ab83/fastapi-0.136.3-py3-none-any.whl", hash = "sha256:3d2a69bdf04b7e9f3afa292c3bc7a98816bbfafa10bc9b45f3f3700d2f761620", size = 117481, upload-time = "2026-05-23T18:53:16.924Z" },
+]
+
 [[package]]
 name = "genai-prices"
 version = "0.0.60"
@@ -734,6 +769,49 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/7e/f5/f66802a942d491edb555dd61e3a9961140fd64c90bce1eafd741609d334d/httpcore-1.0.9-py3-none-any.whl", hash = "sha256:2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55", size = 78784, upload-time = "2025-04-24T22:06:20.566Z" },
 ]
 
+[[package]]
+name = "httptools"
+version = "0.8.0"
+source = { registry = "https://pypi.org/simple" }
+sdist = { url = "https://files.pythonhosted.org/packages/43/e5/d471fcb0e14523fe1c3f4ba58ca52480e7bd70ad7109a3846bc75892f7fb/httptools-0.8.0.tar.gz", hash = "sha256:6b2a32f18d97e16e90827d7a819ffa8dbd8cc245fc4e1fa9d1095b54ef4bd999", size = 271342, upload-time = "2026-05-25T22:17:48.841Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/f8/d2/c3eedaef57de65c3cc5f8dc244cf12d09c84ad258a479055aad6db23206c/httptools-0.8.0-cp311-cp311-macosx_10_9_universal2.whl", hash = "sha256:ed377e64805bdba4943c82717333f8f8603a13b09aff9cead2717c6c817fb168", size = 208428, upload-time = "2026-05-25T22:16:59.717Z" },
+    { url = "https://files.pythonhosted.org/packages/f1/94/dfe435d90d0ef61ec0f2cc3d480eef78c59727c6c2ce039f433882f6131a/httptools-0.8.0-cp311-cp311-macosx_11_0_arm64.whl", hash = "sha256:9518c406d7b310f05adb1a37f80acabac40504a575d7c0da6d3e365c695ac20d", size = 113366, upload-time = "2026-05-25T22:17:00.795Z" },
+    { url = "https://files.pythonhosted.org/packages/cc/d4/13025f1a56e615dcb331e0bbe2d9a1143212b58c263385fc5d2e558f5bac/httptools-0.8.0-cp311-cp311-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", hash = "sha256:57278e6fa0424c42a8a3e454828ab4f0aff27b40cddf9679579b98c6dce6a376", size = 464676, upload-time = "2026-05-25T22:17:02.014Z" },
+    { url = "https://files.pythonhosted.org/packages/bf/95/4c1c26c0b985f8a3331682d802598f14e32dc41bf7509266eb2c04ad4801/httptools-0.8.0-cp311-cp311-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:bbb8caadb2b742d293169d2b458b5c001ef70e3158704aa3d3ef9597624c5d1d", size = 464235, upload-time = "2026-05-25T22:17:03.109Z" },
+    { url = "https://files.pythonhosted.org/packages/a2/82/6735be2b0ca527718c431cdb8e5f70c3862c0844a687df0f572c51e11497/httptools-0.8.0-cp311-cp311-musllinux_1_2_aarch64.whl", hash = "sha256:52dd695b865fe96d9d2b16b64a895f3f57bf3cb064e8383cd3b5713a069e8085", size = 449809, upload-time = "2026-05-25T22:17:04.443Z" },
+    { url = "https://files.pythonhosted.org/packages/b5/f9/5811c74f37a758c8a4aa3dc430375119d335947e883efc4664d8f3559a41/httptools-0.8.0-cp311-cp311-musllinux_1_2_x86_64.whl", hash = "sha256:20b4aac66ff65f7db06a375808b78f42a94970aa22e826b3cb2b43eb09174124", size = 452174, upload-time = "2026-05-25T22:17:05.476Z" },
+    { url = "https://files.pythonhosted.org/packages/cc/94/97b75870dea07b71e3ec535cebe525b08d723152e4c7d13fa887e51f4de2/httptools-0.8.0-cp311-cp311-win_amd64.whl", hash = "sha256:a1b4c8e7a489a0d750d91894e9a8cdc295838f1924c0ca903ae993456fddec07", size = 90991, upload-time = "2026-05-25T22:17:06.75Z" },
+    { url = "https://files.pythonhosted.org/packages/14/88/1d21a36da8f5cb0fa49eafd4b169eba5608d57e75bbcf61845cbc6243216/httptools-0.8.0-cp312-cp312-macosx_10_13_universal2.whl", hash = "sha256:880490234c10f70a9830743097e8958d6e4b9f5a0ffc24515023afeef984054d", size = 208247, upload-time = "2026-05-25T22:17:07.843Z" },
+    { url = "https://files.pythonhosted.org/packages/a5/42/cc4feea2945cb3051038f090c9b36bd5b8a9d7f5a894a506a8983e33fd1c/httptools-0.8.0-cp312-cp312-macosx_11_0_arm64.whl", hash = "sha256:5931891fb7b441b8a3853cf1b85c82c903defce084dd5f6771ca46e31bf862c5", size = 113064, upload-time = "2026-05-25T22:17:09.136Z" },
+    { url = "https://files.pythonhosted.org/packages/e3/a6/febbb8b8db0f58b38e44ad6cb946e6a255ae49b55f2e8543408fb7501ccd/httptools-0.8.0-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", hash = "sha256:b15fc622b0f869d19207c4089a501d9bcc63ca5e071ffdd2f03f922df882dcb2", size = 523851, upload-time = "2026-05-25T22:17:10.106Z" },
+    { url = "https://files.pythonhosted.org/packages/b7/e4/f90a0df0b83beff265b7e3b65f2a4cefd95792d4be0ac3e16049f2acd3c2/httptools-0.8.0-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:425f83884fd6343828d8c565f046cb72b6d19063f6924093e11bcd8e1548cd09", size = 518842, upload-time = "2026-05-25T22:17:11.218Z" },
+    { url = "https://files.pythonhosted.org/packages/9e/2d/0c9ac76dd2c893841fbf6498d6acec4f2442e1b7067f6e3e316a80e494e8/httptools-0.8.0-cp312-cp312-musllinux_1_2_aarch64.whl", hash = "sha256:ef7c3c97f4311c7be57e2986629df89d49cb434dbff78eafcd48c2bff986b15a", size = 501238, upload-time = "2026-05-25T22:17:12.728Z" },
+    { url = "https://files.pythonhosted.org/packages/ca/42/906adc91ae3a5fa9c59c0a2f21c139725bd7e5b41ae6acd485cd14123ebf/httptools-0.8.0-cp312-cp312-musllinux_1_2_x86_64.whl", hash = "sha256:a1afd7c9fbff0d9f5d489c4ce2768bd09c84a46ddefc7161e6aa82ae35c85745", size = 509567, upload-time = "2026-05-25T22:17:13.842Z" },
+    { url = "https://files.pythonhosted.org/packages/05/0b/4240efeb672751ee5b9b380cb0e3fdc050bc05f68adc7a8aefc4fcd9a69a/httptools-0.8.0-cp312-cp312-win_amd64.whl", hash = "sha256:cd96f29b4bab1d42fa6e3d008711c75e0f79e94e06827330160e3a304227f150", size = 90918, upload-time = "2026-05-25T22:17:15.155Z" },
+    { url = "https://files.pythonhosted.org/packages/5e/e5/8cfcabc5546e8022f168be28bcdaa128a240a0befdd03b59d558b4f18bd6/httptools-0.8.0-cp313-cp313-macosx_10_13_universal2.whl", hash = "sha256:614ceea8ea606848bece2338ac03b3ce5324bcb4be8dc7d377ed708012fa4db8", size = 205148, upload-time = "2026-05-25T22:17:16.333Z" },
+    { url = "https://files.pythonhosted.org/packages/2a/0e/0fb14848c19a686c8062ff9067c1a48793e3224b47bc5b201535b6036fce/httptools-0.8.0-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:2d689918c15a013c65ef52d9fd495d766893ab831a2c8d89f2ac5940a5df847c", size = 111368, upload-time = "2026-05-25T22:17:17.586Z" },
+    { url = "https://files.pythonhosted.org/packages/2e/1b/46f1cecf06b9bbde8e4b8c88034ac7908989e5ff7a3a388ef38392949c1f/httptools-0.8.0-cp313-cp313-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", hash = "sha256:eb3028cca2fc0a6d720e52ef61d8ebb62fcbfeb1de56874546d858d3f25a26b7", size = 486447, upload-time = "2026-05-25T22:17:18.564Z" },
+    { url = "https://files.pythonhosted.org/packages/77/00/258bfc0837221f81d9725c45f9b948a6a6b2994a147a4fb66e85100c668f/httptools-0.8.0-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:88bdd940f2b5d487b4d032c6afa5489a7dc4694410d43de3c38c4fb3af0dc45d", size = 482448, upload-time = "2026-05-25T22:17:19.912Z" },
+    { url = "https://files.pythonhosted.org/packages/04/ab/d1cef3b5523f4d272a70f42a776c3169a2dddfe3a54de4b2ce4a36341528/httptools-0.8.0-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:6a43c9dd399758ccc0531acb0a3c4a6c299ee893ee9400e9c893b7bdcfae0681", size = 464460, upload-time = "2026-05-25T22:17:20.882Z" },
+    { url = "https://files.pythonhosted.org/packages/ce/48/5d1d072442277bb2b3434e0e60690b8e8c23840ef7de8b6ea54040a536d3/httptools-0.8.0-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:0770728beb05094c809b98e814edff5fef69d26ad7d21185f2f6d5884a0ba683", size = 471312, upload-time = "2026-05-25T22:17:22.085Z" },
+    { url = "https://files.pythonhosted.org/packages/0d/66/b96623b27e51a68199ef4efdda0613cced9233fe3062ac74e50749c5ad37/httptools-0.8.0-cp313-cp313-win_amd64.whl", hash = "sha256:7685df791fad561384bfb139e77fde27a1ffd93134e016f95a0db424ffbf77b1", size = 90117, upload-time = "2026-05-25T22:17:23.074Z" },
+    { url = "https://files.pythonhosted.org/packages/1a/12/fa3fbf5f9517b273edea2dc982aa82a8c634091e67c590792b729017bc6f/httptools-0.8.0-cp314-cp314-macosx_10_13_universal2.whl", hash = "sha256:de242a49b5d18e0a8776e654e9f6bf6d89f3875a5c35b425a0e7ce940feb3fd6", size = 206183, upload-time = "2026-05-25T22:17:24.004Z" },
+    { url = "https://files.pythonhosted.org/packages/30/fc/5e7c4cb443370f2090a3aba0453a07384d29ff66b7435bb90e77e1037599/httptools-0.8.0-cp314-cp314-macosx_11_0_arm64.whl", hash = "sha256:159e9ab5f701ccd42e555a12f1ad8ff69702910fc1c996cf2bb66e5fcb7a231b", size = 112079, upload-time = "2026-05-25T22:17:25.216Z" },
+    { url = "https://files.pythonhosted.org/packages/ba/53/771bd891eb0f236f32145d6a1775777ec85745f3cc983a1f23d1a3b8ddfe/httptools-0.8.0-cp314-cp314-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", hash = "sha256:c4a9f1707e4823d54dfec6c33fa3697d302aed536ed352a7ebb5a061ddb869d0", size = 481596, upload-time = "2026-05-25T22:17:26.186Z" },
+    { url = "https://files.pythonhosted.org/packages/62/42/94e15bc68ce3d423243c45d7f1b0c7561f13844f97dc52ae23182fb65628/httptools-0.8.0-cp314-cp314-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:d76ad7b951387e3632c8716a9bb03ac5b45c5f16119aa409db0459520887944e", size = 480865, upload-time = "2026-05-25T22:17:27.542Z" },
+    { url = "https://files.pythonhosted.org/packages/1c/7c/fe2980fc03723272e30f135b62360b075f513dfe7cc73aef36c7f04012bd/httptools-0.8.0-cp314-cp314-musllinux_1_2_aarch64.whl", hash = "sha256:a3b7387147361c3fd47a0bde763c5c91b5b4cd4dc9989b8ece84ff436c99843b", size = 463189, upload-time = "2026-05-25T22:17:28.546Z" },
+    { url = "https://files.pythonhosted.org/packages/15/1b/47fc5fff68acd1bfa20b4734059c9a06cadb88119dcd5258b5b0d21d91c8/httptools-0.8.0-cp314-cp314-musllinux_1_2_x86_64.whl", hash = "sha256:f256d6ce930c52ca1cb2a960b7da03548c454e7d28b06059ad41bfe789036ce0", size = 466610, upload-time = "2026-05-25T22:17:29.816Z" },
+    { url = "https://files.pythonhosted.org/packages/60/bd/07b13c93ffd9bec9546e0d43f8e19378dd696dbd278511406bc07371ef1f/httptools-0.8.0-cp314-cp314-win_amd64.whl", hash = "sha256:19d1ee275bb59ba2643ba9a3a1e51cc0c788caf2b8df506368e03f56fdd08527", size = 92705, upload-time = "2026-05-25T22:17:31.133Z" },
+    { url = "https://files.pythonhosted.org/packages/fd/c4/121648f68ce066d7bd762d6b6d97e620847642d38d54f3d90ff11d947629/httptools-0.8.0-cp314-cp314t-macosx_10_13_universal2.whl", hash = "sha256:de1ed58a974e75d56560acc7e7fed01a454994429456f65209789992e41f2568", size = 215023, upload-time = "2026-05-25T22:17:32.401Z" },
+    { url = "https://files.pythonhosted.org/packages/b9/b0/312a062ae741ae3e8baa8c8bf20be81b2e67337b259ab4349bebc7b6142e/httptools-0.8.0-cp314-cp314t-macosx_11_0_arm64.whl", hash = "sha256:e93c227b595c6926c1acee96891dd9da4be338cfbe82e5cd3bb9d8dd7dc4ac0b", size = 117405, upload-time = "2026-05-25T22:17:33.742Z" },
+    { url = "https://files.pythonhosted.org/packages/fc/37/fccd705f795386bb05bf413012fecff2a33e5aa8c2f069096de3e9fd8702/httptools-0.8.0-cp314-cp314t-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", hash = "sha256:2a021c3a8e65cc125390d72f59b968afca3bdcaff25bd67965e0a055a14946ca", size = 558497, upload-time = "2026-05-25T22:17:34.732Z" },
+    { url = "https://files.pythonhosted.org/packages/bd/39/f172e8003576de35f5ba77ff417cf0e34429d35dc014deef15afa337a72c/httptools-0.8.0-cp314-cp314t-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:48774d39cbb70e2b1f71f88852a3087ae1d3a1eb80482bb48c13067ab080c14f", size = 571585, upload-time = "2026-05-25T22:17:35.813Z" },
+    { url = "https://files.pythonhosted.org/packages/3e/b9/f5564760af99f3dbbf3f9104dc00e5da27e96cf433c6bdcf77617f70bf3f/httptools-0.8.0-cp314-cp314t-musllinux_1_2_aarch64.whl", hash = "sha256:88eead8ec8680a9f146c655bc88445a325bd7921cfd8194c7337e9467282427d", size = 543297, upload-time = "2026-05-25T22:17:37.08Z" },
+    { url = "https://files.pythonhosted.org/packages/99/67/8d9f2c313618e161b82f3873188e7196126da1d6e29688df40eb3997c77a/httptools-0.8.0-cp314-cp314t-musllinux_1_2_x86_64.whl", hash = "sha256:2c032fa028f46871ec7e1fc59fc15e8023eab3e6bbe6ece786a1611719a5d081", size = 539535, upload-time = "2026-05-25T22:17:38.032Z" },
+    { url = "https://files.pythonhosted.org/packages/48/63/b906c01e53f50d432c0defe43ce52764a111dc1bdd028bafbeb54dcfd008/httptools-0.8.0-cp314-cp314t-win_amd64.whl", hash = "sha256:384c17174464c8e873398b7af24f0b1f44d992c820328413951a625323155d77", size = 108209, upload-time = "2026-05-25T22:17:39.473Z" },
+]
+
 [[package]]
 name = "httpx"
 version = "0.28.1"
@@ -2367,6 +2445,148 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/15/41/ac2dfdbc1f60c7af4f994c7a335cfa7040c01642b605d65f611cecc2a1e4/uvicorn-0.47.0-py3-none-any.whl", hash = "sha256:2c5715bc12d1892d84752049f400cd1c3cb018514967fdfeb97640443a6a9432", size = 71301, upload-time = "2026-05-14T18:16:51.762Z" },
 ]
 
+[package.optional-dependencies]
+standard = [
+    { name = "colorama", marker = "sys_platform == 'win32'" },
+    { name = "httptools" },
+    { name = "python-dotenv" },
+    { name = "pyyaml" },
+    { name = "uvloop", marker = "platform_python_implementation != 'PyPy' and sys_platform != 'cygwin' and sys_platform != 'win32'" },
+    { name = "watchfiles" },
+    { name = "websockets" },
+]
+
+[[package]]
+name = "uvloop"
+version = "0.22.1"
+source = { registry = "https://pypi.org/simple" }
+sdist = { url = "https://files.pythonhosted.org/packages/06/f0/18d39dbd1971d6d62c4629cc7fa67f74821b0dc1f5a77af43719de7936a7/uvloop-0.22.1.tar.gz", hash = "sha256:6c84bae345b9147082b17371e3dd5d42775bddce91f885499017f4607fdaf39f", size = 2443250, upload-time = "2025-10-16T22:17:19.342Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/c7/d5/69900f7883235562f1f50d8184bb7dd84a2fb61e9ec63f3782546fdbd057/uvloop-0.22.1-cp311-cp311-macosx_10_9_universal2.whl", hash = "sha256:c60ebcd36f7b240b30788554b6f0782454826a0ed765d8430652621b5de674b9", size = 1352420, upload-time = "2025-10-16T22:16:21.187Z" },
+    { url = "https://files.pythonhosted.org/packages/a8/73/c4e271b3bce59724e291465cc936c37758886a4868787da0278b3b56b905/uvloop-0.22.1-cp311-cp311-macosx_10_9_x86_64.whl", hash = "sha256:3b7f102bf3cb1995cfeaee9321105e8f5da76fdb104cdad8986f85461a1b7b77", size = 748677, upload-time = "2025-10-16T22:16:22.558Z" },
+    { url = "https://files.pythonhosted.org/packages/86/94/9fb7fad2f824d25f8ecac0d70b94d0d48107ad5ece03769a9c543444f78a/uvloop-0.22.1-cp311-cp311-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:53c85520781d84a4b8b230e24a5af5b0778efdb39142b424990ff1ef7c48ba21", size = 3753819, upload-time = "2025-10-16T22:16:23.903Z" },
+    { url = "https://files.pythonhosted.org/packages/74/4f/256aca690709e9b008b7108bc85fba619a2bc37c6d80743d18abad16ee09/uvloop-0.22.1-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:56a2d1fae65fd82197cb8c53c367310b3eabe1bbb9fb5a04d28e3e3520e4f702", size = 3804529, upload-time = "2025-10-16T22:16:25.246Z" },
+    { url = "https://files.pythonhosted.org/packages/7f/74/03c05ae4737e871923d21a76fe28b6aad57f5c03b6e6bfcfa5ad616013e4/uvloop-0.22.1-cp311-cp311-musllinux_1_2_aarch64.whl", hash = "sha256:40631b049d5972c6755b06d0bfe8233b1bd9a8a6392d9d1c45c10b6f9e9b2733", size = 3621267, upload-time = "2025-10-16T22:16:26.819Z" },
+    { url = "https://files.pythonhosted.org/packages/75/be/f8e590fe61d18b4a92070905497aec4c0e64ae1761498cad09023f3f4b3e/uvloop-0.22.1-cp311-cp311-musllinux_1_2_x86_64.whl", hash = "sha256:535cc37b3a04f6cd2c1ef65fa1d370c9a35b6695df735fcff5427323f2cd5473", size = 3723105, upload-time = "2025-10-16T22:16:28.252Z" },
+    { url = "https://files.pythonhosted.org/packages/3d/ff/7f72e8170be527b4977b033239a83a68d5c881cc4775fca255c677f7ac5d/uvloop-0.22.1-cp312-cp312-macosx_10_13_universal2.whl", hash = "sha256:fe94b4564e865d968414598eea1a6de60adba0c040ba4ed05ac1300de402cd42", size = 1359936, upload-time = "2025-10-16T22:16:29.436Z" },
+    { url = "https://files.pythonhosted.org/packages/c3/c6/e5d433f88fd54d81ef4be58b2b7b0cea13c442454a1db703a1eea0db1a59/uvloop-0.22.1-cp312-cp312-macosx_10_13_x86_64.whl", hash = "sha256:51eb9bd88391483410daad430813d982010f9c9c89512321f5b60e2cddbdddd6", size = 752769, upload-time = "2025-10-16T22:16:30.493Z" },
+    { url = "https://files.pythonhosted.org/packages/24/68/a6ac446820273e71aa762fa21cdcc09861edd3536ff47c5cd3b7afb10eeb/uvloop-0.22.1-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:700e674a166ca5778255e0e1dc4e9d79ab2acc57b9171b79e65feba7184b3370", size = 4317413, upload-time = "2025-10-16T22:16:31.644Z" },
+    { url = "https://files.pythonhosted.org/packages/5f/6f/e62b4dfc7ad6518e7eff2516f680d02a0f6eb62c0c212e152ca708a0085e/uvloop-0.22.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:7b5b1ac819a3f946d3b2ee07f09149578ae76066d70b44df3fa990add49a82e4", size = 4426307, upload-time = "2025-10-16T22:16:32.917Z" },
+    { url = "https://files.pythonhosted.org/packages/90/60/97362554ac21e20e81bcef1150cb2a7e4ffdaf8ea1e5b2e8bf7a053caa18/uvloop-0.22.1-cp312-cp312-musllinux_1_2_aarch64.whl", hash = "sha256:e047cc068570bac9866237739607d1313b9253c3051ad84738cbb095be0537b2", size = 4131970, upload-time = "2025-10-16T22:16:34.015Z" },
+    { url = "https://files.pythonhosted.org/packages/99/39/6b3f7d234ba3964c428a6e40006340f53ba37993f46ed6e111c6e9141d18/uvloop-0.22.1-cp312-cp312-musllinux_1_2_x86_64.whl", hash = "sha256:512fec6815e2dd45161054592441ef76c830eddaad55c8aa30952e6fe1ed07c0", size = 4296343, upload-time = "2025-10-16T22:16:35.149Z" },
+    { url = "https://files.pythonhosted.org/packages/89/8c/182a2a593195bfd39842ea68ebc084e20c850806117213f5a299dfc513d9/uvloop-0.22.1-cp313-cp313-macosx_10_13_universal2.whl", hash = "sha256:561577354eb94200d75aca23fbde86ee11be36b00e52a4eaf8f50fb0c86b7705", size = 1358611, upload-time = "2025-10-16T22:16:36.833Z" },
+    { url = "https://files.pythonhosted.org/packages/d2/14/e301ee96a6dc95224b6f1162cd3312f6d1217be3907b79173b06785f2fe7/uvloop-0.22.1-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:1cdf5192ab3e674ca26da2eada35b288d2fa49fdd0f357a19f0e7c4e7d5077c8", size = 751811, upload-time = "2025-10-16T22:16:38.275Z" },
+    { url = "https://files.pythonhosted.org/packages/b7/02/654426ce265ac19e2980bfd9ea6590ca96a56f10c76e63801a2df01c0486/uvloop-0.22.1-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:6e2ea3d6190a2968f4a14a23019d3b16870dd2190cd69c8180f7c632d21de68d", size = 4288562, upload-time = "2025-10-16T22:16:39.375Z" },
+    { url = "https://files.pythonhosted.org/packages/15/c0/0be24758891ef825f2065cd5db8741aaddabe3e248ee6acc5e8a80f04005/uvloop-0.22.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:0530a5fbad9c9e4ee3f2b33b148c6a64d47bbad8000ea63704fa8260f4cf728e", size = 4366890, upload-time = "2025-10-16T22:16:40.547Z" },
+    { url = "https://files.pythonhosted.org/packages/d2/53/8369e5219a5855869bcee5f4d317f6da0e2c669aecf0ef7d371e3d084449/uvloop-0.22.1-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:bc5ef13bbc10b5335792360623cc378d52d7e62c2de64660616478c32cd0598e", size = 4119472, upload-time = "2025-10-16T22:16:41.694Z" },
+    { url = "https://files.pythonhosted.org/packages/f8/ba/d69adbe699b768f6b29a5eec7b47dd610bd17a69de51b251126a801369ea/uvloop-0.22.1-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:1f38ec5e3f18c8a10ded09742f7fb8de0108796eb673f30ce7762ce1b8550cad", size = 4239051, upload-time = "2025-10-16T22:16:43.224Z" },
+    { url = "https://files.pythonhosted.org/packages/90/cd/b62bdeaa429758aee8de8b00ac0dd26593a9de93d302bff3d21439e9791d/uvloop-0.22.1-cp314-cp314-macosx_10_13_universal2.whl", hash = "sha256:3879b88423ec7e97cd4eba2a443aa26ed4e59b45e6b76aabf13fe2f27023a142", size = 1362067, upload-time = "2025-10-16T22:16:44.503Z" },
+    { url = "https://files.pythonhosted.org/packages/0d/f8/a132124dfda0777e489ca86732e85e69afcd1ff7686647000050ba670689/uvloop-0.22.1-cp314-cp314-macosx_10_13_x86_64.whl", hash = "sha256:4baa86acedf1d62115c1dc6ad1e17134476688f08c6efd8a2ab076e815665c74", size = 752423, upload-time = "2025-10-16T22:16:45.968Z" },
+    { url = "https://files.pythonhosted.org/packages/a3/94/94af78c156f88da4b3a733773ad5ba0b164393e357cc4bd0ab2e2677a7d6/uvloop-0.22.1-cp314-cp314-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:297c27d8003520596236bdb2335e6b3f649480bd09e00d1e3a99144b691d2a35", size = 4272437, upload-time = "2025-10-16T22:16:47.451Z" },
+    { url = "https://files.pythonhosted.org/packages/b5/35/60249e9fd07b32c665192cec7af29e06c7cd96fa1d08b84f012a56a0b38e/uvloop-0.22.1-cp314-cp314-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:c1955d5a1dd43198244d47664a5858082a3239766a839b2102a269aaff7a4e25", size = 4292101, upload-time = "2025-10-16T22:16:49.318Z" },
+    { url = "https://files.pythonhosted.org/packages/02/62/67d382dfcb25d0a98ce73c11ed1a6fba5037a1a1d533dcbb7cab033a2636/uvloop-0.22.1-cp314-cp314-musllinux_1_2_aarch64.whl", hash = "sha256:b31dc2fccbd42adc73bc4e7cdbae4fc5086cf378979e53ca5d0301838c5682c6", size = 4114158, upload-time = "2025-10-16T22:16:50.517Z" },
+    { url = "https://files.pythonhosted.org/packages/f0/7a/f1171b4a882a5d13c8b7576f348acfe6074d72eaf52cccef752f748d4a9f/uvloop-0.22.1-cp314-cp314-musllinux_1_2_x86_64.whl", hash = "sha256:93f617675b2d03af4e72a5333ef89450dfaa5321303ede6e67ba9c9d26878079", size = 4177360, upload-time = "2025-10-16T22:16:52.646Z" },
+    { url = "https://files.pythonhosted.org/packages/79/7b/b01414f31546caf0919da80ad57cbfe24c56b151d12af68cee1b04922ca8/uvloop-0.22.1-cp314-cp314t-macosx_10_13_universal2.whl", hash = "sha256:37554f70528f60cad66945b885eb01f1bb514f132d92b6eeed1c90fd54ed6289", size = 1454790, upload-time = "2025-10-16T22:16:54.355Z" },
+    { url = "https://files.pythonhosted.org/packages/d4/31/0bb232318dd838cad3fa8fb0c68c8b40e1145b32025581975e18b11fab40/uvloop-0.22.1-cp314-cp314t-macosx_10_13_x86_64.whl", hash = "sha256:b76324e2dc033a0b2f435f33eb88ff9913c156ef78e153fb210e03c13da746b3", size = 796783, upload-time = "2025-10-16T22:16:55.906Z" },
+    { url = "https://files.pythonhosted.org/packages/42/38/c9b09f3271a7a723a5de69f8e237ab8e7803183131bc57c890db0b6bb872/uvloop-0.22.1-cp314-cp314t-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:badb4d8e58ee08dad957002027830d5c3b06aea446a6a3744483c2b3b745345c", size = 4647548, upload-time = "2025-10-16T22:16:57.008Z" },
+    { url = "https://files.pythonhosted.org/packages/c1/37/945b4ca0ac27e3dc4952642d4c900edd030b3da6c9634875af6e13ae80e5/uvloop-0.22.1-cp314-cp314t-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:b91328c72635f6f9e0282e4a57da7470c7350ab1c9f48546c0f2866205349d21", size = 4467065, upload-time = "2025-10-16T22:16:58.206Z" },
+    { url = "https://files.pythonhosted.org/packages/97/cc/48d232f33d60e2e2e0b42f4e73455b146b76ebe216487e862700457fbf3c/uvloop-0.22.1-cp314-cp314t-musllinux_1_2_aarch64.whl", hash = "sha256:daf620c2995d193449393d6c62131b3fbd40a63bf7b307a1527856ace637fe88", size = 4328384, upload-time = "2025-10-16T22:16:59.36Z" },
+    { url = "https://files.pythonhosted.org/packages/e4/16/c1fd27e9549f3c4baf1dc9c20c456cd2f822dbf8de9f463824b0c0357e06/uvloop-0.22.1-cp314-cp314t-musllinux_1_2_x86_64.whl", hash = "sha256:6cde23eeda1a25c75b2e07d39970f3374105d5eafbaab2a4482be82f272d5a5e", size = 4296730, upload-time = "2025-10-16T22:17:00.744Z" },
+]
+
+[[package]]
+name = "watchfiles"
+version = "1.2.0"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "anyio" },
+]
+sdist = { url = "https://files.pythonhosted.org/packages/cd/41/5e1a4bb12aac5f1493fa1bdc11154eca3b258ca4eba65d39c473fe19d8e9/watchfiles-1.2.0.tar.gz", hash = "sha256:c995fba777f1ea992f090f9236e9284cf7a5d1a0130dd5a3d82c598cacd76838", size = 108252, upload-time = "2026-05-18T04:32:04.251Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/fc/3d/8024c801df84d1587740d0359e7fdd80afeae3d159011f3d5376dd82f18e/watchfiles-1.2.0-cp311-cp311-macosx_10_12_x86_64.whl", hash = "sha256:704fd259e332e01f9b9c178f4bce9e49027e5587cc2600eeeaf8e76e1c846201", size = 400242, upload-time = "2026-05-18T04:31:19.014Z" },
+    { url = "https://files.pythonhosted.org/packages/87/5b/f4dfd45323e949984a3a7f9dc31d1cbb049921e7d98253488dda72ccdaa9/watchfiles-1.2.0-cp311-cp311-macosx_11_0_arm64.whl", hash = "sha256:6543cf55d170003296d185c0af981f3e1311564907e1f4e08671fc7693a890a5", size = 394562, upload-time = "2026-05-18T04:30:08.46Z" },
+    { url = "https://files.pythonhosted.org/packages/98/d8/19483ef075d601c409bce8bcbb5c0f81a10876fff870400568f08ce484a1/watchfiles-1.2.0-cp311-cp311-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:89d8c2394a065ca86f5d2910ff263ae67c127e1376ccc4f9fc35c71db879f80a", size = 456611, upload-time = "2026-05-18T04:30:45.723Z" },
+    { url = "https://files.pythonhosted.org/packages/b1/6a/cc81fbe7ee42f2f22e661a6e12def7807e01b14b2f39e0ff83fd373fd307/watchfiles-1.2.0-cp311-cp311-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:772b80df316480d894a0e3165fdd19cf77f5d17f9a787f94029465ad0e3529d1", size = 461379, upload-time = "2026-05-18T04:31:29.292Z" },
+    { url = "https://files.pythonhosted.org/packages/b1/57/7e669002082c0a0f4fb5113bb70125f7110124b846b0a11bc5ae8e90eac1/watchfiles-1.2.0-cp311-cp311-manylinux_2_17_i686.manylinux2014_i686.whl", hash = "sha256:d158cd89df6053823533e06fb1d73c549133bff5f0396170c0e53d9559340717", size = 493556, upload-time = "2026-05-18T04:30:05.44Z" },
+    { url = "https://files.pythonhosted.org/packages/45/7d/f60a2b19807b21fe8281f3a8da4f59eef0d5f96825ac4680ba2d4f2ebf91/watchfiles-1.2.0-cp311-cp311-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:d516b3283a758e087841aedb8031549fb41ced08f3db10aa6d2bf32dc042525b", size = 575255, upload-time = "2026-05-18T04:30:40.568Z" },
+    { url = "https://files.pythonhosted.org/packages/bd/49/77f5b5e6efbcd57482f74948ebb1b97e5c0046d6b61475042d830c84b3ff/watchfiles-1.2.0-cp311-cp311-manylinux_2_17_s390x.manylinux2014_s390x.whl", hash = "sha256:53b2290c92e0506d102cd448fbc610d87079553f86caa39d67440856a8b8bba5", size = 467052, upload-time = "2026-05-18T04:31:17.942Z" },
+    { url = "https://files.pythonhosted.org/packages/ee/5a/73e2959af1b97fd5d556f9a8bdba017be23ceeef731869d5eaa0a753d5a3/watchfiles-1.2.0-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:a711b51aec4370d0dcda5b6c09463206f133a5759341d7744b953a7b62e1100e", size = 456858, upload-time = "2026-05-18T04:30:30.182Z" },
+    { url = "https://files.pythonhosted.org/packages/50/57/1bc8c27fad7e6c19bddee15d276dbb6ab72480ec01c127afff1673aee417/watchfiles-1.2.0-cp311-cp311-manylinux_2_31_riscv64.whl", hash = "sha256:e2ca07fa7d89195ec0865d3d285666286740bfa83d83e5cee204043a31ecc165", size = 467579, upload-time = "2026-05-18T04:32:15.897Z" },
+    { url = "https://files.pythonhosted.org/packages/09/6c/3c2e44edba3553c5e3c3b8c8a2a6dee6b9e12ae2cf4bd2378bebf9dc3038/watchfiles-1.2.0-cp311-cp311-musllinux_1_1_aarch64.whl", hash = "sha256:e0618518f282c4ebff60f5e5b1247b6d91bb8b9f4476947563a1e74acc66f3c6", size = 633253, upload-time = "2026-05-18T04:31:37.123Z" },
+    { url = "https://files.pythonhosted.org/packages/30/c2/d8c84a882ab39bbefcc4915ab3e91830b7a7e990c5570b0b69075aba3faf/watchfiles-1.2.0-cp311-cp311-musllinux_1_1_x86_64.whl", hash = "sha256:0d191c054d0715c3c95c99df9b8dbf6fd096d8c1e021e8f212e1bd8bc444ccb5", size = 660713, upload-time = "2026-05-18T04:31:24.62Z" },
+    { url = "https://files.pythonhosted.org/packages/a9/07/f97736a5fc605364fe67b25e9fa4a6965dfd4840d50c406ada507e9d735f/watchfiles-1.2.0-cp311-cp311-win32.whl", hash = "sha256:9342472aff9b093c5acd4f6d8f70ae0937964ab56542502bcf5579782da69ae8", size = 277222, upload-time = "2026-05-18T04:31:21.131Z" },
+    { url = "https://files.pythonhosted.org/packages/cf/99/2b04981977fc2608afd60360d928c6aecf6b950292ca221d98f4005f6694/watchfiles-1.2.0-cp311-cp311-win_amd64.whl", hash = "sha256:dbd6c97045dad81227c8d040173da044c1de08de64a5ea8b555da4aee1d5fa22", size = 290274, upload-time = "2026-05-18T04:31:45.966Z" },
+    { url = "https://files.pythonhosted.org/packages/3c/74/f7f58a7075ee9cf612b0cfcddb78b8cd8234f0742d6f0075cf0da2dde1c6/watchfiles-1.2.0-cp311-cp311-win_arm64.whl", hash = "sha256:57a2d9fa4fb4c2ecae57b13dfff2c7ab53e21a2ba674fe9f05506680fcdcc0d7", size = 283460, upload-time = "2026-05-18T04:31:39.126Z" },
+    { url = "https://files.pythonhosted.org/packages/b8/2f/e42c992d2afda3108ea1c02acecc991b9f31d05c14adc2a7cee9ee211fc4/watchfiles-1.2.0-cp312-cp312-macosx_10_12_x86_64.whl", hash = "sha256:bc13eb17538be00c874699dc0abe4ee2bc8d50bb1166a6b9e175ef3fd7eb8f26", size = 400115, upload-time = "2026-05-18T04:32:02.06Z" },
+    { url = "https://files.pythonhosted.org/packages/5f/8f/6af2ea19065c91d8b0ea3516fdfc8c0d349f407e8e9fbf4e5a17360de8ad/watchfiles-1.2.0-cp312-cp312-macosx_11_0_arm64.whl", hash = "sha256:2d95ddc1eb6914154253d239089900813f6a767e174b8e6a50e7fdacb7e4236c", size = 393659, upload-time = "2026-05-18T04:30:50.951Z" },
+    { url = "https://files.pythonhosted.org/packages/13/01/b32a967c56fb3e3e5be3db52c3d3b87fa4513aa367d8ed1ad96d42952e5f/watchfiles-1.2.0-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:8f70d8b291ef6e88d19b1f297a6905ddb978888d9272b0d05e6f53309856bcfc", size = 453207, upload-time = "2026-05-18T04:31:04.231Z" },
+    { url = "https://files.pythonhosted.org/packages/04/98/97557a812180338cb1abd32e1cffcc4588f59b5f23e0cb006b2ba95ba64a/watchfiles-1.2.0-cp312-cp312-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:56d8641cf834c2836922899105bd3ce3d0dfc69291d52edf0b4d0436829b34c0", size = 459273, upload-time = "2026-05-18T04:31:50.377Z" },
+    { url = "https://files.pythonhosted.org/packages/e8/a8/b4b08dcb7653b8087c6586f7ce649505900e866bbcfe40dc9587af02e686/watchfiles-1.2.0-cp312-cp312-manylinux_2_17_i686.manylinux2014_i686.whl", hash = "sha256:2581a94056e55d7d0a31a823ea92bf73749c489ca2285bfdc0fbe6b2bb49d50c", size = 489927, upload-time = "2026-05-18T04:31:42.485Z" },
+    { url = "https://files.pythonhosted.org/packages/50/94/3dceea03545d2e5ddfd839f0ddd5e1cecbf1697b5a428d5ba11cef6af95d/watchfiles-1.2.0-cp312-cp312-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:41bc1199f7523b3f82843c88cbb979180c949caef0342cf90968f178e5d49b01", size = 570476, upload-time = "2026-05-18T04:31:03.071Z" },
+    { url = "https://files.pythonhosted.org/packages/cc/f2/d39a5450c3532092b91f81d274360e613c2371bc874a89c7a1a3c5e8d138/watchfiles-1.2.0-cp312-cp312-manylinux_2_17_s390x.manylinux2014_s390x.whl", hash = "sha256:7571e4464cb6e434958f867f7f730b8ab0b75e3f8e5eac0499168486ab3c33a8", size = 465650, upload-time = "2026-05-18T04:30:12.701Z" },
+    { url = "https://files.pythonhosted.org/packages/22/24/ed72f68cbc1333ca9b9f2200aa048bb6658ae41709bc1caad4310f4bdffd/watchfiles-1.2.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:e53a384f76b631c3ae5334ce6a52f0baa3a911eb94a4eac7f160079868b716d5", size = 456398, upload-time = "2026-05-18T04:30:13.784Z" },
+    { url = "https://files.pythonhosted.org/packages/0d/64/982ef4a4e5bab5b6e5b6becc8cd5e732f6130a78b855f0abec6439a9a135/watchfiles-1.2.0-cp312-cp312-manylinux_2_31_riscv64.whl", hash = "sha256:d20029a60a71a052a24c4db7673bc4de39ab89adbaccbfb5d67987c5d73f424d", size = 465140, upload-time = "2026-05-18T04:31:52.111Z" },
+    { url = "https://files.pythonhosted.org/packages/a0/0c/95282abf4ed680b6096010bcfc30c5fa7a041fc5aa5a2ad17a2cc6c75bba/watchfiles-1.2.0-cp312-cp312-musllinux_1_1_aarch64.whl", hash = "sha256:2cb93af48550faf1cea04c303107c8b75833de7013e57ce27d3b8d21d8d0f58c", size = 630259, upload-time = "2026-05-18T04:31:25.676Z" },
+    { url = "https://files.pythonhosted.org/packages/30/45/607c1de1530c4bdcf2cf1d1ecc2505ddba5d96bd43ba9f2b0e79876f850f/watchfiles-1.2.0-cp312-cp312-musllinux_1_1_x86_64.whl", hash = "sha256:2995c176de7692b86a2e4c58d9ec718f753150a979cb4a754e2b4ffa38e70906", size = 659859, upload-time = "2026-05-18T04:30:24.333Z" },
+    { url = "https://files.pythonhosted.org/packages/fa/08/d9e2e0f9e8e6791d33aefc694ad7eefa7f901f63caff84a81ded38692f9c/watchfiles-1.2.0-cp312-cp312-win32.whl", hash = "sha256:7a2cffd17d27d2ecbb310c2b1d8174f222a5495b1a721894afa88ec11e25b898", size = 275480, upload-time = "2026-05-18T04:30:31.307Z" },
+    { url = "https://files.pythonhosted.org/packages/1c/e6/9d42569c0102645cc8cea5d8c7d8a1e9d4ada2cb7f05f75e554b8aa2202a/watchfiles-1.2.0-cp312-cp312-win_amd64.whl", hash = "sha256:f155b3a1b2a5fc89cdc70d47ee5d54e3b75e88efa34982028a35daef9ba00379", size = 288718, upload-time = "2026-05-18T04:32:10.745Z" },
+    { url = "https://files.pythonhosted.org/packages/0a/26/88e0dc6ee3898169d7fa22bb6a69cabf2502d2ee25cb8c876d1262d204f8/watchfiles-1.2.0-cp312-cp312-win_arm64.whl", hash = "sha256:8fa585ede612ee9f9e91b18bebf9ba11b9ae29a4e3a0d0cf6fca3e382133f0d5", size = 281026, upload-time = "2026-05-18T04:30:22.23Z" },
+    { url = "https://files.pythonhosted.org/packages/d1/4d/70a7feced9f87e2ff26dba42667290f41694fc64646c67261fbb8cab5d5c/watchfiles-1.2.0-cp313-cp313-macosx_10_12_x86_64.whl", hash = "sha256:01ea8d66f0693b9b60a6541c8d10263091ca9a9060d242f3c1f3143f9aad2c98", size = 399730, upload-time = "2026-05-18T04:31:38.162Z" },
+    { url = "https://files.pythonhosted.org/packages/31/3a/0da302f2307aee316922806ebd5726c542cbd787c938271cf14a074c7daf/watchfiles-1.2.0-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:7ba0480b9a74af058f43b337e937a451e109295c420916d68ad24e3dc02f5e44", size = 392842, upload-time = "2026-05-18T04:30:27.051Z" },
+    { url = "https://files.pythonhosted.org/packages/db/ef/d5bdb705c224dbc256aa0c1ec47bf4e61ec52558f2afb44a71a1fe4d7015/watchfiles-1.2.0-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:4f34e26a19f91f710c08e0183429f0d1d15df734e6bc78c31e77b9ea9c433658", size = 452989, upload-time = "2026-05-18T04:31:11.945Z" },
+    { url = "https://files.pythonhosted.org/packages/71/29/5495f2c1661949ef7a35e4d71111d129cfe7606414a26887a919d0a55406/watchfiles-1.2.0-cp313-cp313-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:b4e77f6a55f858504069abd35d336a637555c09bca453dde1ee1e5ada8a6a1fb", size = 458978, upload-time = "2026-05-18T04:30:52.606Z" },
+    { url = "https://files.pythonhosted.org/packages/d5/8c/7f9c07c433811c2fffd93e13fdfb7135de9aab5f2ae41be08960fa0047dc/watchfiles-1.2.0-cp313-cp313-manylinux_2_17_i686.manylinux2014_i686.whl", hash = "sha256:0cb4d80e212f116474a545c21c912b445f16bb0cef9e6a73a498164223e14e2f", size = 490248, upload-time = "2026-05-18T04:31:36.003Z" },
+    { url = "https://files.pythonhosted.org/packages/3c/11/d93632febc52fbc21be90231bb7c17fd5387f46c9076fd40a5f9c2ae6910/watchfiles-1.2.0-cp313-cp313-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:b974946a10af379d425e2eef5b62f5c6ebeaccf91d45eaad6f5b27ecd4f91aa0", size = 571847, upload-time = "2026-05-18T04:31:10.862Z" },
+    { url = "https://files.pythonhosted.org/packages/55/b4/383173e73aabb07ad1d9c7aa859d95437ac46a6d6a1e11005facda0c9d19/watchfiles-1.2.0-cp313-cp313-manylinux_2_17_s390x.manylinux2014_s390x.whl", hash = "sha256:86bc13c25a8d1fcd70b51d0ce7c9b65e90de5666fcbfd3e34957cc73ee19aeb5", size = 465974, upload-time = "2026-05-18T04:30:17.006Z" },
+    { url = "https://files.pythonhosted.org/packages/a7/6c/89b1a230a78f57c52dd8893adb1f92f94411721b6ec12596c56d98c74356/watchfiles-1.2.0-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:ca148d73dea36c9763aaa351e4d7a51780ec1584217c45276f4fe8239c768b71", size = 454782, upload-time = "2026-05-18T04:30:35.656Z" },
+    { url = "https://files.pythonhosted.org/packages/24/62/1732118367cfff0a9fce3bf62ff4bfded09ef5df21d9d446b858b3f70a96/watchfiles-1.2.0-cp313-cp313-manylinux_2_31_riscv64.whl", hash = "sha256:c525543d91961c6955b2636b308569e84a1d1c5f5f2932041ab9ef46422f43e3", size = 465182, upload-time = "2026-05-18T04:30:20.846Z" },
+    { url = "https://files.pythonhosted.org/packages/28/96/716f7e5f51339bf22963f3345f9f27d7f3b30e2eadc597e257c881dd3c53/watchfiles-1.2.0-cp313-cp313-musllinux_1_1_aarch64.whl", hash = "sha256:a204794696ffb8f9b10fba6f7cb5216d42f3b2b71860ccac6b6e42f5f10973b0", size = 629841, upload-time = "2026-05-18T04:31:05.397Z" },
+    { url = "https://files.pythonhosted.org/packages/4c/fe/c40783950fd771ccf66ab3ec2722d188a9af1c7f96c6e811f36e40c6e03f/watchfiles-1.2.0-cp313-cp313-musllinux_1_1_x86_64.whl", hash = "sha256:10d86db20695afe7997ac9e1717637d6714a8d0220458c33f3d2061f54cec427", size = 658028, upload-time = "2026-05-18T04:31:48.22Z" },
+    { url = "https://files.pythonhosted.org/packages/71/72/4508db1856d1d87fcbb3b63f4839bab1b5682cb0e8d224d122263c09654a/watchfiles-1.2.0-cp313-cp313-win32.whl", hash = "sha256:eb283ee99e21ad6443c8cdb06ac5b34b1308c329cbdf03fa02b445363714c799", size = 275183, upload-time = "2026-05-18T04:30:59.57Z" },
+    { url = "https://files.pythonhosted.org/packages/f9/36/14b76ca57652e5cc5fd1c11f32a261292c08a0d19a00351013c2549cbfb2/watchfiles-1.2.0-cp313-cp313-win_amd64.whl", hash = "sha256:a0f27f01bee51861392bb6b7c4fdb290b27d1eb194e9e28788d68102a0e898d9", size = 288059, upload-time = "2026-05-18T04:32:07.937Z" },
+    { url = "https://files.pythonhosted.org/packages/1b/8d/0a85e395398d8d20fadfe5c5d32c726eee17a519e78fb356f2cf7531bffe/watchfiles-1.2.0-cp313-cp313-win_arm64.whl", hash = "sha256:3651aa7058595e9cfb75d35dd5ada2bf9f48a5b8a0f3562821d3e210c507e077", size = 280186, upload-time = "2026-05-18T04:31:54.484Z" },
+    { url = "https://files.pythonhosted.org/packages/37/68/36db056f1fdcc5f07302f56e631774d6835bcd6fa3ace402304621d5f9e5/watchfiles-1.2.0-cp313-cp313t-macosx_10_12_x86_64.whl", hash = "sha256:faea288b6f0ab1902ef08f4ca6de005dccf856c4e0c4f21b8c5fce02d90a1b08", size = 399031, upload-time = "2026-05-18T04:30:44.576Z" },
+    { url = "https://files.pythonhosted.org/packages/c1/64/01a9d6f66a82a5c101ce939274106cc72759d62427e153f01edd2b9f87c2/watchfiles-1.2.0-cp313-cp313t-macosx_11_0_arm64.whl", hash = "sha256:01859b11fd9fbca670f4d5da00fbac282cfea9bd67a2125d8b2833a3b5617ea9", size = 391205, upload-time = "2026-05-18T04:30:25.413Z" },
+    { url = "https://files.pythonhosted.org/packages/84/2c/0a44fe058cb4bb7b8ede6b6670698bbb7c0400740e378d00022189b7b31d/watchfiles-1.2.0-cp313-cp313t-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:fff610d7bb2256a317bb1e96f0d7862c7aa8076733ee5df0fd41bbe76a24a4f4", size = 451892, upload-time = "2026-05-18T04:32:14.005Z" },
+    { url = "https://files.pythonhosted.org/packages/67/a1/351e0d56cd35e6488b5c8b4fb11a809a5bc923e8fe8fed9faf8920be0c89/watchfiles-1.2.0-cp313-cp313t-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:b141a4891c995a039cd89e9a49e62df1dc8a559a5d1a6e4c7106d16c12777a55", size = 458867, upload-time = "2026-05-18T04:31:22.279Z" },
+    { url = "https://files.pythonhosted.org/packages/d5/7d/9d09605187f1b838998624049fcf8bf47b73c1a3b76901fcac1782f62277/watchfiles-1.2.0-cp313-cp313t-manylinux_2_17_i686.manylinux2014_i686.whl", hash = "sha256:f22943b7770483f6ea0721c6b11d022947a98eb0acae14694de034f4d0d38925", size = 490217, upload-time = "2026-05-18T04:31:43.657Z" },
+    { url = "https://files.pythonhosted.org/packages/60/5d/a17a16eccb182f04188cd308ec24b1a71a9b5c4e7098269cf35d9fa56d02/watchfiles-1.2.0-cp313-cp313t-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:1bc6195825b7dcd217968bb1f801a60fd4c16e8eeab5bedc7fe917d7d5995ab4", size = 571458, upload-time = "2026-05-18T04:32:11.875Z" },
+    { url = "https://files.pythonhosted.org/packages/d3/3d/4dd457062083ab1938e5dfd45032eb425cee2ac817287ca8ff4356183e5d/watchfiles-1.2.0-cp313-cp313t-manylinux_2_17_s390x.manylinux2014_s390x.whl", hash = "sha256:d4a4b147f5dca2a5d325a06a832fb43f345751adfbc63204aec30e0d9ca965a2", size = 464707, upload-time = "2026-05-18T04:30:43.492Z" },
+    { url = "https://files.pythonhosted.org/packages/c6/71/ea8c57b128f5383de74d0c7d2d9c57ad7c9a65a930c451bd25d524b295b7/watchfiles-1.2.0-cp313-cp313t-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:4543579a9bdb0c9560039b4ffddbdb39545707659fbc430ce4c10f3f68d557f9", size = 454663, upload-time = "2026-05-18T04:30:16.061Z" },
+    { url = "https://files.pythonhosted.org/packages/53/fd/2e812bf938406d7db351f0703ddd3fc6c061cf30d96153a77bc79a943a44/watchfiles-1.2.0-cp313-cp313t-manylinux_2_31_riscv64.whl", hash = "sha256:20aa0e708b920bde876a4aa82dc7dd6ebea228a63a67cda6632c2fc87b787efa", size = 463537, upload-time = "2026-05-18T04:31:44.9Z" },
+    { url = "https://files.pythonhosted.org/packages/86/56/d17a7f1dd1bc3035f1072694a551301272f1739c2d8e319c927cb9e29b38/watchfiles-1.2.0-cp313-cp313t-musllinux_1_1_aarch64.whl", hash = "sha256:d413349d565dab74297f2a63e84a097936be69bf8f3b3801f27f380e32040f44", size = 629194, upload-time = "2026-05-18T04:31:14.141Z" },
+    { url = "https://files.pythonhosted.org/packages/be/06/f1ff66bf5cae50aa4062779a0ecd0bbaf15e466195719074078947d9a17d/watchfiles-1.2.0-cp313-cp313t-musllinux_1_1_x86_64.whl", hash = "sha256:f28b2725eb8cce327b9b3ab02415c853011dc55c95832fe90de6bc56f5315f72", size = 656194, upload-time = "2026-05-18T04:31:47.14Z" },
+    { url = "https://files.pythonhosted.org/packages/e7/54/a9c7ea9a82a4ac65e7004c0a03920b5cdd2f9c3b678757d9cd425aa51d53/watchfiles-1.2.0-cp314-cp314-macosx_10_12_x86_64.whl", hash = "sha256:b8c8358484d5fa12ef34f05b7f4168eaf1932f408725ff6d023c33ec17bd79d4", size = 400205, upload-time = "2026-05-18T04:32:05.153Z" },
+    { url = "https://files.pythonhosted.org/packages/aa/5d/c9ab3534374a4a67450696905d6ef16a04405448b8dc52bd752ae50423d4/watchfiles-1.2.0-cp314-cp314-macosx_11_0_arm64.whl", hash = "sha256:9f04b092229ad2c50126dd3c922c8822e51e605993764a33058d4a791ab42281", size = 392508, upload-time = "2026-05-18T04:30:54.849Z" },
+    { url = "https://files.pythonhosted.org/packages/26/ca/1ad30103535cf0cecd7b993e8d50edc5351b1820e38f2d22e3df58962feb/watchfiles-1.2.0-cp314-cp314-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:7a7ce236284f002a156f70add88efe5c70879cccbb658be0822c54b1306fc09d", size = 452448, upload-time = "2026-05-18T04:30:53.727Z" },
+    { url = "https://files.pythonhosted.org/packages/37/a1/ceee2cdf2afbd715fa07758d39c9859513eae411b23196f7fd039e5feedd/watchfiles-1.2.0-cp314-cp314-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:b9909cc2b48468b575eefa944919e1fe8a36c5849d5c7c168f80a8c1db69398e", size = 459605, upload-time = "2026-05-18T04:30:23.312Z" },
+    { url = "https://files.pythonhosted.org/packages/e8/f6/421e30fd1cb3907a84ed92ab3f1983e37ba2dca015e9a894a048418417a2/watchfiles-1.2.0-cp314-cp314-manylinux_2_17_i686.manylinux2014_i686.whl", hash = "sha256:0a37faaed405c67e28e6be45a1fa4f206ef5a2860f27c237db9fa30704c38242", size = 490757, upload-time = "2026-05-18T04:30:47.358Z" },
+    { url = "https://files.pythonhosted.org/packages/41/b0/55ed1b97ed08be7bba6f9a541cac15f2a858e1d74d2b07b6da70a82aab00/watchfiles-1.2.0-cp314-cp314-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:9649193aa27bd9ff2e80ff29bfaa93085496c7a3a377592823cc58b77ee88add", size = 568672, upload-time = "2026-05-18T04:30:38.915Z" },
+    { url = "https://files.pythonhosted.org/packages/d1/cf/d8ae8a80dd7bafab395ea7681c10237311bbf34d37704a8c744e7cf31fc7/watchfiles-1.2.0-cp314-cp314-manylinux_2_17_s390x.manylinux2014_s390x.whl", hash = "sha256:4e4ff8e37f99cf1da89e255e07c9c4b37c214038c4283707bdec308cb1b0ea1f", size = 464197, upload-time = "2026-05-18T04:30:09.914Z" },
+    { url = "https://files.pythonhosted.org/packages/7c/8a/3076c496ca8dafe0e8cd03fcebdfc47be4b1174b4e5b24ff6e396e6b3af2/watchfiles-1.2.0-cp314-cp314-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:054dc20fd2e3132b4c3883b4a00d72fd6e1f56fdaf89fccd12e8057d74cd74d7", size = 453181, upload-time = "2026-05-18T04:30:14.829Z" },
+    { url = "https://files.pythonhosted.org/packages/e5/10/9745e17c98e7b8a86454df0a3c7b5686bd650383f1e9f26e4ebcbd6cc0c0/watchfiles-1.2.0-cp314-cp314-manylinux_2_31_riscv64.whl", hash = "sha256:e140ed30ebde76796b686e67c182cff10ea2fbab186fafd1560f74bb5a473a6e", size = 465109, upload-time = "2026-05-18T04:30:28.123Z" },
+    { url = "https://files.pythonhosted.org/packages/8f/95/8ef4a95481d3e0cb52d62a06fa6e972e81424be2d9698b91a2fecca9904c/watchfiles-1.2.0-cp314-cp314-musllinux_1_1_aarch64.whl", hash = "sha256:bb7e52ecf68ba46d22df23467b87cffeb2146908aa523ebfe803019618cfda06", size = 630653, upload-time = "2026-05-18T04:31:49.304Z" },
+    { url = "https://files.pythonhosted.org/packages/fd/e4/3b3bf36b0f829b50c6ebcb8d031583863c59f923d6a6af3d485e470d0fac/watchfiles-1.2.0-cp314-cp314-musllinux_1_1_x86_64.whl", hash = "sha256:23282a321c8baf9b3a3c4afff673f9fe65eb7fdc2338d765ccad9d3d1916a5ba", size = 657838, upload-time = "2026-05-18T04:31:06.497Z" },
+    { url = "https://files.pythonhosted.org/packages/21/b1/6cbbb50c1f3002ab568777d44aa21206dfb8807a840990c4037523b51812/watchfiles-1.2.0-cp314-cp314-win32.whl", hash = "sha256:c0db965c5f79aa49fe672d297cf1febc5ad149b658594944f49a54a2b96270a7", size = 275108, upload-time = "2026-05-18T04:30:06.891Z" },
+    { url = "https://files.pythonhosted.org/packages/92/45/190ce6db8dcb4536682cf75d3889ff1a27182a58cb519d343cb6d9ea63d8/watchfiles-1.2.0-cp314-cp314-win_amd64.whl", hash = "sha256:71283b39fd17e5408eb123bd37aeecfd9d54c81fc184421943208aadb879d103", size = 288441, upload-time = "2026-05-18T04:32:12.901Z" },
+    { url = "https://files.pythonhosted.org/packages/74/0d/3eae1c2313ab08378431d907c3f8095ecca00f3eda33111cf4f0f2591799/watchfiles-1.2.0-cp314-cp314-win_arm64.whl", hash = "sha256:c5c19526f4e54a00f2666a6c0e9e40d582c09e865055ea7378bf0009aab857b3", size = 280684, upload-time = "2026-05-18T04:31:26.902Z" },
+    { url = "https://files.pythonhosted.org/packages/b1/75/fb64e6c25d6b5ca636d03df34ffb1c6e9873303e76d27967e045f8df088f/watchfiles-1.2.0-cp314-cp314t-macosx_10_12_x86_64.whl", hash = "sha256:d73a585accffa5ae39c17264c36ec3166d2fad7000c780f5ef83b2722afb9dd2", size = 398857, upload-time = "2026-05-18T04:32:17.108Z" },
+    { url = "https://files.pythonhosted.org/packages/73/4e/9f7adf01754cbf81843722ccfec169d8f26c69778281a302855cecd2ee08/watchfiles-1.2.0-cp314-cp314t-macosx_11_0_arm64.whl", hash = "sha256:ae99b14c5f21e026e0e9d96f40e07d8570ebee6cafd9d8fc318354606daa7a28", size = 392413, upload-time = "2026-05-18T04:31:07.911Z" },
+    { url = "https://files.pythonhosted.org/packages/47/c8/bec626bcc2d69f44b9acb24ce7d60ed7b16b73628eea747fcbd169d8edda/watchfiles-1.2.0-cp314-cp314t-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:4429f3b105524a10b72c3a819b091c495d2811d419c1e1e8df773a5a5974f831", size = 452409, upload-time = "2026-05-18T04:31:20.142Z" },
+    { url = "https://files.pythonhosted.org/packages/00/b7/b6362068e81e7c556d155a34c35d40ac3ef42d747b06d7f6e5bf58e359c2/watchfiles-1.2.0-cp314-cp314t-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:43d818978d06062d9b22c4fab2ebe44cf5213d42dc8e62bda8c2760cfa2eeb33", size = 458827, upload-time = "2026-05-18T04:32:06.219Z" },
+    { url = "https://files.pythonhosted.org/packages/67/f8/9a813fa42afb1e0b4625e75f0479826644d3ee8dc287e093799bc01f390c/watchfiles-1.2.0-cp314-cp314t-manylinux_2_17_i686.manylinux2014_i686.whl", hash = "sha256:b9f732dc58b2dbe69e464ccf8fff7a03b0dd0be439da4c0720d3558527d3d6b4", size = 490104, upload-time = "2026-05-18T04:31:56.034Z" },
+    { url = "https://files.pythonhosted.org/packages/2f/bf/27dfb6094ca4c9aad21298b5525b6c53cb36121ee454331d05161e58d130/watchfiles-1.2.0-cp314-cp314t-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:8f200104103feb097de4cab8fe4f5dd18a2026934c7dea98c55a2f5fd6d5a33b", size = 571360, upload-time = "2026-05-18T04:31:57.133Z" },
+    { url = "https://files.pythonhosted.org/packages/fb/39/44a096d67270ea93df91d33877dbe91fbda3aa4f8ec2edf799d93eda8736/watchfiles-1.2.0-cp314-cp314t-manylinux_2_17_s390x.manylinux2014_s390x.whl", hash = "sha256:63ac26eefbf4af1741247d6fb68b11c49a25b2f7413fbd318a83a12aaa9cf666", size = 464644, upload-time = "2026-05-18T04:30:57.33Z" },
+    { url = "https://files.pythonhosted.org/packages/0e/80/c7472203bad6268e3ef1ad260739704847898938ad7ea8b63a5131f46b50/watchfiles-1.2.0-cp314-cp314t-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:0c4997d4e4a55f0d02b6cde327322daf3a0400e5df6c6b15948994bf72497925", size = 454771, upload-time = "2026-05-18T04:30:48.736Z" },
+    { url = "https://files.pythonhosted.org/packages/51/cf/3b10b268b4b7f0fc26e9debb5eef1998b515887840f444cd3ec80c688755/watchfiles-1.2.0-cp314-cp314t-manylinux_2_31_riscv64.whl", hash = "sha256:4c887eba18b7945ac73067a8b4a66f21cd46c2539b2bc68588f7be6c7eb6d26b", size = 463494, upload-time = "2026-05-18T04:31:33.826Z" },
+    { url = "https://files.pythonhosted.org/packages/3d/3e/a4302545cd589262a0dc7d140e86f7688eba3f9c72776c27f7e23b8864c4/watchfiles-1.2.0-cp314-cp314t-musllinux_1_1_aarch64.whl", hash = "sha256:3416ff151bb6b5a8d8d11664974fbef4d9305b9b2957839ab5a270468fd8df30", size = 629383, upload-time = "2026-05-18T04:31:15.596Z" },
+    { url = "https://files.pythonhosted.org/packages/db/99/d5649df0a9a410d45b7c882304d0b790903ac9b6e8f2cfd12114e0c6b9f2/watchfiles-1.2.0-cp314-cp314t-musllinux_1_1_x86_64.whl", hash = "sha256:0e831a271c035d89789cffc386b6aa1375f39f1cd25eb7ca0997e4970d152fc5", size = 656093, upload-time = "2026-05-18T04:31:58.707Z" },
+    { url = "https://files.pythonhosted.org/packages/23/f4/7513ef1e85fc4c6331b59479d6d72661fc391fbe543678052ac72c8b6c19/watchfiles-1.2.0-pp311-pypy311_pp73-macosx_10_12_x86_64.whl", hash = "sha256:4674d49eb94706dfe666c069fc0a1b646ffcf920473492e209f6d5f60d3f0cc2", size = 403050, upload-time = "2026-05-18T04:30:36.753Z" },
+    { url = "https://files.pythonhosted.org/packages/27/0b/a54103cfd732bb703c7a749222011a0483ef3705948dae3b203158601119/watchfiles-1.2.0-pp311-pypy311_pp73-macosx_11_0_arm64.whl", hash = "sha256:094b9b70103d4e963499bdea001ee3c2697b144cd9ae6218a62c0f89ec9e31db", size = 396629, upload-time = "2026-05-18T04:32:03.268Z" },
+    { url = "https://files.pythonhosted.org/packages/5e/2c/73f31a3b893886206c3f54d73e8ad8dee58cdb2f69ad2622e0a8a9e07f4e/watchfiles-1.2.0-pp311-pypy311_pp73-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:b0ef001f8c25ad0fa9529f914c1600647ecd0f542d11c19b7894768c67b6acb7", size = 457318, upload-time = "2026-05-18T04:31:01.932Z" },
+    { url = "https://files.pythonhosted.org/packages/e9/f9/45d021e4a5cc7b9dd567f7cbb06d3b75f751a690063fb6cc7ec60f4e46b7/watchfiles-1.2.0-pp311-pypy311_pp73-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:a88fc94e647bc4eec523f1caa540258eb71d14278b9daf72fa1e2658a98df0f0", size = 457771, upload-time = "2026-05-18T04:30:56.331Z" },
+]
+
 [[package]]
 name = "wcwidth"
 version = "0.7.0"
```
