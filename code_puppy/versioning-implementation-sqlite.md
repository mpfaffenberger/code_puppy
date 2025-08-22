# Implementation Plan for Versioning in a Pydantic AI CLI Agent

## Overview

This document outlines a step-by-step implementation plan for integrating versioning, redo capabilities, modifications, Git-like full repository snapshot checkout, and optional cascading changes into an existing Python CLI agent built with the Pydantic AI library. In this codebase, the agent returns plain strings (`output_type=str`); where older plans reference a Pydantic output model, adapt to string outputs.

Key features:
- Versioning of prompt responses using SQLite for persistence.
- Redo: Re-run the same prompt to create a new version.
- Edit: Modify an existing response as a new branched version.
- Cascading: Optionally re-run dependent prompts when changes occur.
- Git-like [full repository snapshot checkout]: Reconstruct the entire tracked codebase to the state as-of a specific saved version/response ID.
- **Interactive Mode integration**: The REPL already exists in `code_puppy/main.py` (`interactive_mode()`). We will integrate versioning commands and persistence into this REPL so users can run prompts, redo, and inspect versions in-session.

Assumptions:
- Existing codebase uses argparse for CLI commands.
- Pydantic AI agent is set up with asynchronous execution (e.g., `agent.run()`).
- Estimated total time: 3-5 hours, including testing.

## Prerequisites

- Review existing codebase: Identify the `Agent` instance and entrypoints. In this repo they are `get_code_generation_agent()` in `code_puppy/agent.py` and the CLI/REPL in `code_puppy/main.py` (`argparse`-based, not Typer).
- Install/confirm dependencies: `pydantic-ai`, `pydantic`, LLM provider (e.g., `openai`). SQLite is built-in. Rich/prompt_toolkit are already used by the REPL.
- Backup your codebase.

## Step 1: Add SQLite Database Initialization (Code Puppy specifics)

Create a new module `code_puppy/version_store.py` for database-related functions. Store the DB under the existing config directory (`~/.code_puppy`). The agent in this repo returns `str` (`output_type=str`), so persist plain text instead of JSON.

- Define DB connection and schema:
  ```python
  # code_puppy/version_store.py
  import os
  import sqlite3
  from datetime import datetime
  from typing import Optional
  
  from code_puppy.config import CONFIG_DIR
  
  DB_FILE = os.path.join(CONFIG_DIR, "version_store.db")
  
  def get_db_connection():
      os.makedirs(CONFIG_DIR, exist_ok=True)
      conn = sqlite3.connect(DB_FILE)
      conn.execute("PRAGMA foreign_keys = ON")
      return conn
  
  def initialize_db():
      with get_db_connection() as conn:
          cursor = conn.cursor()
          cursor.execute(
              """
              CREATE TABLE IF NOT EXISTS prompts (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  text TEXT UNIQUE NOT NULL
              )
              """
          )
          cursor.execute(
              """
              CREATE TABLE IF NOT EXISTS responses (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  prompt_id INTEGER NOT NULL,
                  version INTEGER NOT NULL,
                  output_text TEXT NOT NULL,
                  timestamp TEXT NOT NULL,
                  parent_response_id INTEGER,
                  FOREIGN KEY (prompt_id) REFERENCES prompts(id) ON DELETE CASCADE,
                  FOREIGN KEY (parent_response_id) REFERENCES responses(id),
                  UNIQUE (prompt_id, version)
              )
              """
          )
          # Track per-run file changes (captured by our file modification tools)
          cursor.execute(
              """
              CREATE TABLE IF NOT EXISTS changes (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  response_id INTEGER NOT NULL,
                  file_path TEXT NOT NULL,
                  change_type TEXT NOT NULL,          -- 'create' | 'modify' | 'delete'
                  diff TEXT NOT NULL,                 -- unified diff for display
                  before_content BLOB,                -- nullable; before full text
                  after_content BLOB,                 -- nullable; after full text
                  before_hash TEXT,                   -- optional integrity checks
                  after_hash TEXT,
                  timestamp TEXT NOT NULL,
                  FOREIGN KEY (response_id) REFERENCES responses(id) ON DELETE CASCADE
              )
              """
          )
          # Add dependencies table if planning for cascading (see Step 7)
          conn.commit()
  ```
- Call `initialize_db()` once during startup, e.g., in `code_puppy/main.py` inside `main()` after `ensure_config_exists()` and before handling commands.
- **Testing**: Run the CLI once; verify `~/.code_puppy/version_store.db` is created and tables exist.
- **Time Estimate**: 15-20 minutes.

## Step 2: Implement Core Versioning Functions

In `code_puppy/version_store.py`, add helpers for prompts and responses. Persist the agent's plain-text output.

- Add:
  ```python
  from typing import Optional, Tuple, Iterable, Dict
  
  def get_or_create_prompt_id(prompt_text: str) -> int:
      ...
  
  def get_next_version(prompt_id: int) -> int:
      ...
  
  def add_version(prompt_text: str, output_text: str, parent_response_id: Optional[int] = None) -> tuple[int, int]:
      """Returns (version, response_id)."""
      ...
  
  def list_versions(prompt_text: str) -> Iterable[tuple[int, int, str]]:
      """Yield (response_id, version, timestamp)."""
      ...
  
  def get_response_by_version(prompt_text: str, version: int) -> Optional[Dict[str, str]]:
      """Return dict with keys: id, version, output_text, timestamp."""
      ...

  # In-memory change capture per run (no Git). Wrappers will call record_change();
  # we persist them after we know the response_id.
  def start_change_capture() -> None:
      ...

  def record_change(
      file_path: str,
      change_type: str,  # 'create' | 'modify' | 'delete'
      before_content: Optional[str],
      after_content: Optional[str],
      diff: str,
  ) -> None:
      ...

  def finalize_changes(response_id: int) -> None:
      ...

  def get_changes_for_version(
      prompt_text: str, version: int
  ) -> Iterable[Dict[str, str]]:
      """Yield rows with keys: file_path, change_type, diff, before_content, after_content, timestamp."""
      ...
  ```
- **Integration**: Import in `code_puppy/main.py` where results are printed, and in meta-command handlers (next step).
- **Testing**: Test `add_version` with dummy data; confirm version increments and retrieval.
- **Time Estimate**: 20-30 minutes.

## Step 3: Integrate Versioning with Current CLI and REPL (argparse + async)

Code Puppy uses `argparse` and an async REPL in `code_puppy/main.py`.

- Single-command path (already supported in `main()`): Start change capture, then after printing `agent_response`, persist the version and finalize captured changes.
  ```python
  # inside main(), around a single command
  from code_puppy.version_store import (
      initialize_db,
      start_change_capture,
      finalize_changes,
      add_version,
  )
  initialize_db()
  start_change_capture()
  response = await agent.run(command)
  agent_response = response.output
  console.print(agent_response)
  version, response_id = add_version(command, agent_response)
  finalize_changes(response_id)
  ```

- Interactive REPL (`interactive_mode()`): On successful result, persist the version, keep track of the last prompt for redo, and finalize captured changes.
  ```python
  # inside interactive_mode(), where result.output is printed
  from code_puppy.version_store import start_change_capture, add_version, finalize_changes
  start_change_capture()
  if result is not None and hasattr(result, "output"):
      agent_response = result.output
      console.print(agent_response)
      version, response_id = add_version(task, agent_response)
      finalize_changes(response_id)
      last_prompt = task  # define last_prompt in the surrounding scope
  ```

- Redo in REPL: Implement a lightweight `~redo` handling directly in `interactive_mode()` before calling the agent
  (keep as an input transform so meta-handler doesn’t need to run the agent).
  ```python
  # near where task is read inside the REPL loop
  last_prompt = None  # declare near loop start
  ...
  if task.strip().lower() == "~redo":
      if last_prompt:
          task = last_prompt
          console.print("[dim]Redoing last prompt...[/dim]")
      else:
          console.print("[yellow]No previous prompt to redo[/yellow]")
          continue
  ```

- Notes:
  - The agent is async (`await agent.run(...)`) and returns `result.output` as `str`. Persist that string.
  - Call `initialize_db()` once during startup to create tables.
  - Keep DB operations fast and synchronous; they’re lightweight for this use.
  - Hook change capture into file modification wrappers so all agent-driven edits are recorded:
    - In `code_puppy/tools/file_modifications.py`, after producing the unified diff and before returning, call `record_change(...)` with `before_content`, `after_content`, and `diff`.
    - Examples (pseudocode):
      ```python
      try:
          from code_puppy.version_store import record_change
          # _replace_in_file has `original` and `modified` in-scope
          record_change(file_path, "modify", original, modified, diff_text)
      except Exception:
          pass  # never break core behavior
      ```
      ```python
      # _write_to_file: read original if exists
      orig = None
      if exists:
          with open(file_path, "r", encoding="utf-8") as f:
              orig = f.read()
      # after write, call record_change(...)
      record_change(file_path, "create" if not exists else "modify", orig, content, diff_text)
      ```
      ```python
      # _delete_file has `original` in-scope
      record_change(file_path, "delete", original, None, diff_text)
      ```

- **Testing**: Run a single command and an interactive session; confirm rows are created.
- **Time Estimate**: 20-30 minutes.

## Step 4: (Optional) Edit/Branching Support

Outputs are plain text in this repo. If you want to support “edit as new version,” provide utilities that duplicate
an older output and store it as a new version with `parent_response_id` set.

- Suggested helpers in `version_store.py`:
  ```python
  def add_edited_version(prompt_text: str, base_version: int, edited_output_text: str) -> tuple[int, int]:
      existing = get_response_by_version(prompt_text, base_version)
      if not existing:
          return (-1, -1)
      return add_version(prompt_text, edited_output_text, parent_response_id=existing["id"])
  ```
- Surface this via a simple REPL workflow (e.g., user copies output, edits it, then calls a small helper command to save).
- **Testing**: Create an edited version and verify `parent_response_id` is set.
- **Time Estimate**: 15-20 minutes.

## Step 5: Meta Commands for Versioning (fit existing REPL)

Extend `code_puppy/command_line/meta_command_handler.py` with read-only meta commands for version queries.

- Update `META_COMMANDS_HELP` with:
  ```
  ~versions <prompt>      List versions for a specific prompt
  ~show-version <prompt> <version>
                          Show a previous output for a prompt/version
  ~redo                   Re-run last prompt (handled inside interactive_mode)
  ~changes <prompt> <version>
                          List files changed in that version (use --patch to print diffs)
  ~checkout-version <prompt> <version>
                          Restore files touched in that version to their saved state (asks for confirmation)
  ~undo-last              Revert files touched in the most recent version for the same prompt
  ```

- Inside `handle_meta_command(...)`, add handlers that only read/print from SQLite:
  ```python
  if command.startswith("~versions"):
      tokens = command.split(maxsplit=1)
      target = tokens[1] if len(tokens) > 1 else None
      from code_puppy.version_store import list_versions
      if not target:
          console.print("[yellow]Provide a prompt to list its versions[/yellow]")
          return True
      try:
          rows = list(list_versions(target))
          if not rows:
              console.print("[dim]No versions yet[/dim]")
              return True
          console.print(f"[bold]Versions for:[/bold] {target}")
          for rid, ver, ts in rows:
              console.print(f" - v{ver} ({ts}) [id={rid}]")
      except Exception as e:
          console.print(f"[red]Error:[/red] {e}")
      return True

  if command.startswith("~show-version"):
      tokens = command.split()
      if len(tokens) != 3:
          console.print("[yellow]Usage:[/yellow] ~show-version <prompt> <version>")
          return True
      prompt_text, version_str = tokens[1], tokens[2]
      try:
          version = int(version_str)
      except ValueError:
          console.print("[red]Version must be an integer[/red]")
          return True
      from code_puppy.version_store import get_response_by_version
      row = get_response_by_version(prompt_text, version)
      if not row:
          console.print("[dim]Not found[/dim]")
          return True
      console.print(f"[bold]v{row['version']} ({row['timestamp']}):[/bold]\n{row['output_text']}")
      return True
  ```

  ```python
  if command.startswith("~changes"):
      tokens = command.split()
      if len(tokens) < 3:
          console.print("[yellow]Usage:[/yellow] ~changes <prompt> <version> [--patch]")
          return True
      prompt_text, version_str, *flags = tokens[1], tokens[2], tokens[3:]
      show_patch = "--patch" in flags
      from code_puppy.version_store import get_changes_for_version
      try:
          version = int(version_str)
      except ValueError:
          console.print("[red]Version must be an integer[/red]")
          return True
      rows = list(get_changes_for_version(prompt_text, version))
      if not rows:
          console.print("[dim]No changes recorded[/dim]")
          return True
      console.print(f"[bold]Changes for:[/bold] {prompt_text} v{version}")
      for r in rows:
          console.print(f" - {r['file_path']} [{r['change_type']}]")
          if show_patch:
              console.print(r.get('diff') or "[dim]-- no diff --[/dim]", highlight=False)
      return True
  ```

  ```python
  if command.startswith("~checkout-version"):
      tokens = command.split()
      if len(tokens) != 3:
          console.print("[yellow]Usage:[/yellow] ~checkout-version <prompt> <version>")
          return True
      prompt_text, version_str = tokens[1], tokens[2]
      try:
          version = int(version_str)
      except ValueError:
          console.print("[red]Version must be an integer[/red]")
          return True
      from code_puppy.version_store import get_changes_for_version
      from difflib import unified_diff
      rows = list(get_changes_for_version(prompt_text, version))
      if not rows:
          console.print("[dim]No recorded changes for that version[/dim]")
          return True
      console.print(f"[bold yellow]About to restore {len(rows)} file(s). Continue? (y/n)[/bold yellow]")
      try:
          confirmed = input().strip().lower() in {"y", "yes"}
      except (KeyboardInterrupt, EOFError):
          confirmed = False
      if not confirmed:
          console.print("[dim]Cancelled[/dim]")
          return True
      # Apply writes/deletes directly with Python I/O
      import os
      for r in rows:
          path = os.path.abspath(r["file_path"])
          if r["change_type"] == "delete":
              if os.path.exists(path):
                  with open(path, "r", encoding="utf-8") as f:
                      current = f.read()
                  before = current.splitlines(keepends=True)
                  after = []
                  diff = "".join(unified_diff(before, after, fromfile=f"a/{os.path.basename(path)}", tofile=f"b/{os.path.basename(path)}"))
                  console.print(diff or "[dim]-- no diff --[/dim]", highlight=False)
                  os.remove(path)
              continue
          # write or create
          content = r.get("after_content") or ""
          os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
          existing = None
          if os.path.exists(path):
              with open(path, "r", encoding="utf-8") as f:
                  existing = f.read()
          with open(path, "w", encoding="utf-8") as f:
              f.write(content)
          from_lines = (existing or "").splitlines(keepends=True)
          to_lines = content.splitlines(keepends=True)
          diff = "".join(unified_diff(from_lines, to_lines, fromfile=f"a/{os.path.basename(path)}", tofile=f"b/{os.path.basename(path)}"))
          console.print(diff or "[dim]-- no diff --[/dim]", highlight=False)
      console.print("[green]Restore complete[/green]")
      return True
  ```

  ```python
  if command == "~undo-last":
      # Revert the files touched by the most recent version for the same prompt
      console.print("[dim]Undoing last version for current prompt is not yet wired to current REPL state.[/dim]")
      console.print("Use ~changes and ~checkout-version to restore a specific version explicitly.")
      return True
  ```

- Keep `~redo` as a convenience handled directly in `interactive_mode()` so the meta handler doesn’t need to run the agent.
- **Testing**: In the REPL, run a task, then `~versions <that prompt>` and `~show-version <prompt> <1>`.
- **Time Estimate**: 20-30 minutes.

## Step 6: Checkout/Undo to Codebase State (no Git)

- Scope: Applies only to file edits made via `code_puppy/tools/file_modifications.py` wrappers. Shell-command side effects are not captured.
- Provide helpers in `version_store.py`:
  - `get_changes_for_version(prompt_text, version)` (already defined above)
  - Optional convenience: `compute_checkout_operations(prompt_text, version)` that returns a list of operations to apply (write/delete with content)
- Behavior:
  - Checkout to a version writes each file’s saved `after_content` (or deletes if `change_type == 'delete'`).
  - Undo of a version writes each file’s saved `before_content` (or creates file with `before_content` when needed).
  - You may chain checkouts to switch between runs. Unaffected files remain unchanged.
- REPL:
  - `~changes <prompt> <version>` to inspect what would be applied.
  - `~checkout-version <prompt> <version>` to apply. Always prompt for confirmation.
- Testing:
  - Run a prompt that edits several files; confirm `~changes` lists them and `~checkout-version` restores them.
  - Edge cases: file moved/renamed outside Code Puppy, or binary files.
- Time Estimate: 30-45 minutes.

## Step 6b: Full Repository Snapshot Checkout (Git-like)

In addition to per-version file checkout/undo, provide a Git-like ability to restore the entire tracked repository to its state as-of a given response. This operation considers all files that have ever been tracked and reconstructs their last known contents as of the cutoff.

- Semantics:
  - The snapshot includes every path that has appeared in the `changes` table ("tracked files").
  - For each tracked path, find the last change at or before the cutoff response ID and use its `after_content` as the desired content.
  - Paths whose first recorded change occurs after the cutoff will be absent at the snapshot point; treat them as deletions (desired content = None).
  - Non-tracked files (never recorded in `changes`) are left untouched by snapshot checkout.

- Core APIs in `code_puppy/version_store.py`:
  - `compute_snapshot_as_of_response_id(response_id) -> Iterable[Dict[str, Optional[str]]]`
    - Yields `{ 'file_path': str, 'content': Optional[str] }` for every tracked path.
    - If `content is None`, the file should not exist at the snapshot point (delete if present). Otherwise, write the exact `content`.
  - `get_response_id_for_prompt_version(prompt_text, version) -> Optional[int]`
    - Convenience to resolve a response ID from prompt text and version.

- CLI/REPL meta commands in `code_puppy/command_line/meta_command_handler.py`:
  - `~checkout-snapshot-id <response_id> [--patch]`
    - Computes the snapshot as-of `<response_id>`, previews optional unified diffs (`--patch`), asks for confirmation, then writes files and deletes paths as needed to match the snapshot.
  - `~checkout-snapshot-version <prompt> <version> [--patch]`
    - Resolves the response ID via `get_response_id_for_prompt_version()` and performs the same operation as `~checkout-snapshot-id`.

- Behavior notes:
  - This differs from `~checkout-version` and `~undo-last`, which only affect files touched by a specific version.
  - Snapshot checkout rebuilds the full tracked codebase state as-of a point in history, similar to `git checkout <commit>`.
  - A confirmation prompt is always shown; `--patch` shows planned unified diffs before applying changes.

- Usage examples:
  ```
  # Restore entire tracked repository to the state as-of response id=42
  ~checkout-snapshot-id 42 --patch

  # Restore using prompt/version to find the response id
  ~checkout-snapshot-version "add search endpoint" 3 --patch
  ```

- Caveats:
  - Only files modified via Code Puppy wrappers are tracked; external side-effects (e.g., shell commands) are not captured.
  - Binary files are stored as text blobs; diffs may not be meaningful.
  - Non-tracked files are not changed by snapshot checkout.

## Step 7: (Optional) Add Cascading Changes via Dependencies

- Extend schema with `dependencies` table.
- Add functions: `add_dependency`, `get_dependent_prompts`.
- Update `prompt` to accept `--depends-on` and add dependency.
- Add `handle_cascade` function; call after `redo`/`edit`.
- In interactive mode, cascading prompts will appear inline for user confirmation.
- **Testing**: Test dependencies and cascading in interactive session.
- **Time Estimate**: 30-45 minutes (skip if unnecessary).

## Step 8: Final Polish, Error Handling, and Deployment

- Add try-except around DB ops and agent calls.
- Enhance output: Use Rich formatting (tables/colors) for lists.
- Persist additional state (e.g., last_prompt to DB for cross-session redo).
- Documentation: Update README with new commands and interactive mode usage.
- **Interactive-Specific**: Ensure loop handles interruptions (e.g., Ctrl+C).
- **Full Testing**: End-to-end in interactive mode (prompt, redo, edit, list).
- **Best Practices**: Keep DB backups; consider SQLAlchemy for future scalability.
- **Time Estimate**: 20-30 minutes.