# Security & Trust Boundaries

This document describes the safety mechanisms built into Code Puppy. It is meant to help users understand what the tool can read, write, execute, and trust.

---

## Session Persistence

### JSON sessions (default)
- Sessions are saved as **JSON** files with a schema wrapper (`code_puppy.session.v1`).
- Messages are serialized via Pydantic AI's `ModelMessagesTypeAdapter`, not Python `pickle`.

### Legacy pickle danger
- **`.pkl` session files are rejected by default.**
- If you need to migrate an old pickle session, use the explicit `--import-legacy-pickle-session` flag. A warning is emitted because pickle can execute arbitrary code during deserialization (RCE risk).
- Subagent history also uses JSON with atomic private writes.

---

## Secrets & Logging

### Private token files
- OAuth tokens and API keys are stored with **file mode `0o600`** (owner-only read/write).
- Token directories are created with **mode `0o700`**.
- If an existing token file has overly broad permissions, Code Puppy warns and repairs the mode automatically.

### No-token URLs
- OAuth callbacks **never** place `access_token`, `refresh_token`, `id_token`, `api_key`, or `code` in redirect URLs.
- The callback validates the `state` parameter before exchanging the authorization code.

### Redacted logs
- Logs redact known sensitive keys recursively: `access_token`, `refresh_token`, `api_key`, `client_secret`, `password`, `token`, `secret`, `authorization`, `bearer`, etc.
- URL query parameters with sensitive names are replaced with `<redacted>`.
- `Authorization: Bearer ...` headers are scrubbed.
- **Token length is never logged.**

---

## Shell Execution

### Default approval (safe mode)
- Shell commands require **user approval by default** (`yolo_mode = off`).
- The `yolo_mode` config key can be set to `true` to auto-approve, but this is discouraged for unattended use.

### Background command lifecycle
- Background commands require **approval before the process starts** (`Popen`).
- Denied background commands never spawn a process.
- Output is retained as a bounded tail (`deque(maxlen=256)`) to prevent unbounded memory growth.

---

## Workspace & Filesystem Boundaries

### Workspace root
- The current working directory is treated as the **workspace root**.
- File tools enforce containment before reading or writing.

### Sensitive-file policy
- Reads/listings of sensitive paths (`.env`, `.ssh`, `id_rsa`, `.aws`, `credentials`, etc.) are **denied by default**.
- Explicit user approval can override the denial for a specific file.
- Denial messages **never include the full file content**.

### Path traversal & symlink escape
- `Path.resolve()` is used to canonicalize paths.
- Symlinks that escape the workspace are detected and blocked for write/delete operations.

### File-size caps
- `MAX_READ_FILE_BYTES` (128 KB): huge files are rejected before full read; use chunked line ranges instead.
- `MAX_EDIT_FILE_BYTES` (1 MB): edits on files larger than the cap are rejected.
- `MAX_DIFF_BYTES` (512 KB): diff output is capped with a truncation marker.

---

## Grep Safety

- The search pattern is passed **after `--`** to ripgrep so it is treated as data, not CLI flags.
- Patterns starting with `-` are handled safely (e.g., `-help` is literal text).
- Matches are capped; ripgrep is killed once the cap is reached.

---

## Hook Trust

### Project hooks require explicit trust
- Hooks defined in `.claude/settings.json` (project-level) are **blocked by default**.
- Trust is keyed by `(project_root, hooks_file_path, content_hash)`.
- If the hooks file changes, trust is invalidated and re-approval is required.

### Stripped environment
- Project hooks receive a **minimal environment**: `PATH`, `HOME`, `SHELL`, `PWD`, `TERM`, `LANG`, `USER`, `LOGNAME`, plus a few Claude-specific vars.
- Secret-like environment variables are stripped before hook execution.

### Output capping
- Hook stdout/stderr is capped (max ~4096 chars / 256 lines) to prevent unbounded model-context blowup.

---

## Universal Constructor (UC)

### User code with approval
- UC tools are **user-generated Python code** executed in a subprocess worker.
- Tool names and namespaces are validated: no `..`, `/`, `\`, hidden names, dunder, or reserved module names.
- Code must stay inside `USER_UC_DIR`; symlink escapes are blocked.

### Dangerous pattern blocking
- `eval`, `exec`, `subprocess`, `os.system`, `pickle`, write-mode `open`, and network libraries trigger blocking or require approval.
- Approval is stored with a **code hash** and invalidated when the code changes.

### Process isolation & timeout
- Tools run in a **subprocess/multiprocessing worker** with a wall-clock timeout.
- On timeout, the worker process is killed.
- Args and results are serialized via **JSON only** (no pickle).
- stdout/stderr from generated tools is capped.

---

## Plugin & Skill Trust

### Built-in plugins
- Built-in plugins under `code_puppy/plugins/` are loaded automatically.

### User plugins
- User plugins in `~/.code_puppy/plugins/` are loaded but should not shadow built-in imports.

### Skill source/trust
- Skills record their source URL/path, install timestamp, and `SKILL.md` hash.
- Unexpected executable files in skill directories are ignored by default.

---

## MCP Configuration

### Canonical disable key
- Use `disable_mcp = true` in `puppy.cfg` to skip loading MCP servers.
- The deprecated alias `disable_mcp_servers` still works but emits a **one-time `DeprecationWarning`**.

### Key & header redaction
- MCP server status (`get_status()`) **redacts** sensitive header and environment variable values before returning them.
- Keys matching known sensitive names (e.g. `Authorization`, `api_key`, `OPENAI_API_KEY`) are replaced with `<redacted>`.
- Use environment variable references (`$VAR` / `${VAR}`) in MCP config headers and env dicts to keep secrets out of config files.

### Hardcoded secret detection
- At server creation, MCP configs are scanned for **hardcoded secrets** in header values.
- Known prefixes (`sk-`, `ghp_`, `xoxb-`, `AKIA`, `AIza`, etc.) trigger a warning recommending `$VAR` references instead.
- This is a **warning**, not a block — the server still starts, but the user is notified.

---

## HTTP Safety

### TLS / retry independence
- `CODE_PUPPY_DISABLE_RETRY_TRANSPORT` disables retry transport **without** disabling TLS verification.
- To explicitly disable TLS verification, use `CODE_PUPPY_DISABLE_TLS_VERIFY`.
- Proxy detection sets `trust_env=True` but does not affect SSL verification.

---

## Quick Command Reference

| Command | Purpose |
|---------|---------|
| `/safety` or `/status` | Show current safety posture (yolo, shell safety, workspace, hook trust, UC, MCP) |
| `/set yolo_mode true` | Enable auto-approval (dangerous) |
| `/set disable_mcp true` | Disable MCP servers |
