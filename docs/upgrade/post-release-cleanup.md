# Post-Release Cleanup Tracker (pydantic-ai v2 migration)

Status snapshot after the Phase D.1 dead-code sweep. Everything that was
unambiguously dead has already been deleted. What remains needs an owner
decision or manual verification.

## (a) DONE — swept after `code-puppy-core-plugins` 0.0.8 shipped to PyPI

Verified first that the published 0.0.8 wheel imports none of these
(runtime code only touches `ClaudeCacheAsyncClient` and
`session_storage.save_session/load_session/build_session_paths`).
Note: the plugins repo's own *tests* still `mock.patch`
`code_puppy.claude_cache_client.patch_anthropic_client_messages` — those
mocks need updating in the plugins repo, but they do not affect runtime.

| Item | Status |
| --- | --- |
| `patch_anthropic_client_messages` no-op shim | deleted |
| `cache_ttl` kwarg (shim + `ClaudeCacheAsyncClient.__init__`) | deleted |
| `CACHE_TTL_1H` constant | deleted |
| `allow_legacy` kwarg on `load_session` | deleted |
| `WRITE_LEGACY_PICKLE` flag + dual-write branch | flipped off and deleted (ACP plugin reads JSON since 0.0.7) |
| Temporary `[tool.uv.sources]` git pin | deleted; dependency floor is now `code-puppy-core-plugins>=0.0.8` from PyPI |

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

## (c) Release-ordering checklist — DONE

`code-puppy-core-plugins` 0.0.8 is on PyPI; core depends on `>=0.0.8`,
the git-source pin is gone, the lockfile resolves from PyPI, and the
section (a) sweep is complete.

## (d) Pending manual verification

- **Ctrl+C matrix**: mid-stream, mid-tool-execution, and during MCP server
  startup.
- **Live cache verification**: confirm `cache_read_input_tokens` is non-zero
  on both the API-key path and the OAuth path.
- **Full smoke matrix** across supported providers/models.
