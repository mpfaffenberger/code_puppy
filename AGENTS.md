# Contributing to Code Puppy

> **Golden rule:** nearly all new functionality should be a **plugin** under `code_puppy/plugins/`
> that hooks into core via `code_puppy/callbacks.py`. Don't edit `code_puppy/command_line/`.

## How Plugins Work

Create `code_puppy/plugins/my_feature/register_callbacks.py` (builtin) or `~/.code_puppy/plugins/my_feature/register_callbacks.py` (user):

```python
from code_puppy.callbacks import register_callback

def _on_startup():
    print("my_feature loaded!")

register_callback("startup", _on_startup)
```

That's it. The plugin loader auto-discovers `register_callbacks.py` in subdirs.

## Available Hooks

`register_callback("<hook>", func)` — deduplicated, async hooks accept sync or async functions.

| Hook | When | Signature |
|------|------|-----------|
| `startup` | App boot | `() -> None` |
| `shutdown` | Graceful exit | `() -> None` |
| `invoke_agent` | Sub-agent invoked | `(*args, **kwargs) -> None` |
| `agent_exception` | Unhandled agent error | `(exception, *args, **kwargs) -> None` |
| `agent_run_start` | Before agent task | `(agent_name, model_name, session_id=None) -> None` |
| `agent_run_end` | After agent run | `(agent_name, model_name, session_id=None, success=True, error=None, response_text=None, metadata=None) -> None` |
| `load_prompt` | System prompt assembly | `() -> str \| None` |
| `run_shell_command` | Before shell exec | `(context, command, cwd=None, timeout=60) -> dict \| None` (return `{"blocked": True}` to block) |
| `file_permission` | Before file op | `(context, file_path, operation, ...) -> bool` |
| `pre_tool_call` | Before tool executes | `(tool_name, tool_args, context=None) -> Any` |
| `post_tool_call` | After tool finishes | `(tool_name, tool_args, result, duration_ms, context=None) -> Any` |
| `custom_command` | Unknown `/slash` cmd | `(command, name) -> True \| str \| None` |
| `custom_command_help` | `/help` menu | `() -> list[tuple[str, str]]` |
| `register_tools` | Tool registration | `() -> list[dict]` with `{"name": str, "register_func": callable}` |
| `register_agents` | Agent catalogue | `() -> list[dict]` with `{"name": str, "class": type}` |
| `register_model_type` | Custom model type | `() -> list[dict]` with `{"type": str, "handler": callable}` |
| `load_model_config` | Patch model config | `(*args, **kwargs) -> Any` |
| `load_models_config` | Inject models | `() -> dict` |
| `get_model_system_prompt` | Per-model prompt | `(model_name, default_prompt, user_prompt) -> dict \| None` |
| `stream_event` | Response streaming | `(event_type, event_data, agent_session_id=None) -> None` |

Full list + rarely-used hooks: see `code_puppy/callbacks.py` source.

## Rules

1. **Plugins over core** — if a hook exists for it, use it
2. **One `register_callbacks.py` per plugin** — register at module scope
3. **600-line hard cap** — split into submodules
4. **Fail gracefully** — never crash the app
5. **Return `None` from commands you don't own**

## CI: Portable Venv Distribution

The `manual_release` flow in `.looper.yml` does more than publish a wheel —
it also produces fully portable, relocatable virtualenvs for **macOS arm64**
and **Windows x86_64**, then uploads them to the shared `puppy-pages` GCS
bucket. The puppy-backend service serves these zips back to clients via
endpoints, so users can grab a pre-built code-puppy environment without
running `uv` or hitting Artifactory directly.

### What gets published

On a successful `manual_release` run, three GCS objects are written (the
`latest/version.txt` pointer is only flipped after **both** platform
uploads succeed):

```
gs://puppy-pages/code-puppy-venv/<VERSION>/code-puppy-venv-mac.zip
gs://puppy-pages/code-puppy-venv/<VERSION>/code-puppy-venv-windows.zip
gs://puppy-pages/code-puppy-venv/latest/version.txt   # contents: just <VERSION>, no \n
```

`<VERSION>` is whatever `import code_puppy; print(code_puppy.__version__)`
resolves to during the release (i.e. the post-bump version).

### puppy-backend endpoints (separate repo, already shipped)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/code-puppy-venv/version` | Returns the current `latest` version string |
| GET | `/code-puppy-venv/download/{mac\|windows}` | Streams the latest zip for that platform |
| GET | `/code-puppy-venv/download/{mac\|windows}/{version}` | Streams a pinned version |

### Pipeline scripts

| Script | Purpose |
|--------|---------|
| `scripts/build_portable_venv.sh` | macOS: `uv venv --relocatable` + install wheel + zip |
| `scripts/build_portable_venv.ps1` | Windows: same, in PowerShell |
| `scripts/upload_venv_to_gcs.sh` | macOS uploader (Python heredoc + google-auth + REST) |
| `scripts/upload_venv_to_gcs.ps1` | Windows uploader (JWT/RSA-SHA256 + REST, no gcloud) |

### One-time setup (operator)

1. **Encrypt the GCS service account key** and replace the
   `<ENCRYPTED>` placeholder for `GCS_SA_KEY_B64` at the top of `.looper.yml`:

   ```bash
   looper encrypt -r AI-INNOVATION-LAB/code-puppy -s "$(base64 < sa-key.json)"
   ```

   Use the same `wmt-ww-gg-gi-dev` (or equivalent) service account that
   puppy-frontend / puppy-launcher use for the `puppy-pages` bucket.

2. **Onboard the Looper job for the `mac` agent type.** The `macos_arm64`
   label (note the underscore — it is _not_ `mac-arm64`) requires the job
   to be onboarded first. See:
   <https://confluence.walmart.com/display/DXDOCS/14.+Agent+Types+and+Labels>

Until both steps are done, the `manual_release` flow will fail at the
platform-specific build steps. The Artifactory wheel publish + Slack
notification will still complete because they happen earlier in the flow.
