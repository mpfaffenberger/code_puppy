# Post-Release Cleanup Tracker (pydantic-ai v2 migration)

Status snapshot after the Phase D.1 dead-code sweep. Everything that was
unambiguously dead has already been deleted. What remains is intentionally
deferred and gated — do NOT delete these early.

## (a) Gated on `code-puppy-plugins` 0.0.7 shipping

Delete these only after plugins 0.0.7 is published and adopted:

| Item | Location | Notes |
| --- | --- | --- |
| `patch_anthropic_client_messages` no-op shim | `code_puppy/claude_cache_client.py:62` | Inert compat boundary for pre-native-caching plugins. |
| `cache_ttl` kwarg on that shim | `code_puppy/claude_cache_client.py:63` | Intentionally ignored; dies with the shim. |
| `CACHE_TTL_1H` constant | `code_puppy/claude_cache_client.py:37` | Only consumed by the shim's callers in old plugins. |
| `allow_legacy` kwarg | `code_puppy/session_storage.py:254` | Accepted-and-ignored for old plugin call sites. |
| `WRITE_LEGACY_PICKLE` flag + dual-write branch | `code_puppy/session_storage.py:43` and `:223` | See module docstring for the removal plan. |
| Temporary `[tool.uv]` blocks | `pyproject.toml:105` (`override-dependencies` at `:111`, `[tool.uv.sources]` at `:119`) | Pins/overrides only needed until plugins 0.0.7 declares correct deps. |

## (b) Deferred — needs an owner decision (potential public plugin API)

Do not remove without deciding whether these are part of the supported
plugin surface:

- `code_puppy/callbacks.py` thin wrappers: `on_create_file` (:457),
  `on_replace_in_file` (:461), `on_delete_snippet` (:465),
  `on_post_autosave` (:485), `on_message` (:1344).
- `BaseAgent.append_to_message_history` — `code_puppy/agents/base_agent.py:190`.
- Sync token-refresh twins in `code_puppy/claude_cache_client.py`:
  `_should_refresh_token` (:179), `_check_stored_token_expiry` (:196),
  `_refresh_claude_oauth_token` (:574) — each has an `_async` counterpart
  that is the live path.
- `stream_event` callback timing (flagged by the plugins repo during the
  emoji_filter migration): core schedules `stream_event` callbacks via
  `asyncio.create_task` (fire-and-forget) in
  `code_puppy/agents/event_stream_handler.py:_fire_stream_event`, so the
  callback is NOT a guaranteed synchronous pre-render transform — the
  renderer may consume a delta before the callback mutates it. Plugins
  needing deterministic output filtering (e.g. emoji_filter) must pair the
  callback with a terminal-side writer wrapper. Decide whether the seam
  should offer a synchronous pre-render hook, or document fire-and-forget
  as the supported contract.

## (c) Release-ordering checklist

1. Publish `code-puppy-plugins` 0.0.7.
2. In core: delete the `[tool.uv]` `override-dependencies` and
   `[tool.uv.sources]` blocks from `pyproject.toml`.
3. Re-lock (`uv lock`).
4. Bump version and release core.
5. Then (and only then) sweep the table in section (a).

## (d) Pending manual verification

- **Ctrl+C matrix**: mid-stream, mid-tool-execution, and during MCP server
  startup.
- **Live cache verification**: confirm `cache_read_input_tokens` is non-zero
  on both the API-key path and the OAuth path.
- **Full smoke matrix** across supported providers/models.
