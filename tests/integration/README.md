# CLI Integration Harness

## Overview
This folder contains the reusable pyexpect harness that powers Code Puppy's end-to-end CLI integration tests. The harness lives in `tests/integration/cli_expect/harness.py` and exposes pytest fixtures via `tests/conftest.py`. Each test run boots the real `code-puppy` executable inside a temporary HOME, writes a throwaway configuration (including `puppy.cfg` and `motd.txt`), and captures the entire session into a per-run `cli_output.log` file for debugging.

## Prerequisites
- The CLI must be installed locally via `uv sync` or equivalent so `uv run pytest …` launches the editable project binary.
- Set the environment you want to exercise; by default the fixtures read the active shell environment and only override a few keys for test hygiene.
- Export a **real** `CEREBRAS_API_KEY` when you intend to hit live Cerebras models. The harness falls back to `fake-key-for-ci` so tests can run offline, but that key will be rejected by the remote API.

## Required environment variables
| Variable | Purpose | Notes |
| --- | --- | --- |
| `CEREBRAS_API_KEY` | Primary provider for live integration coverage | Required for real LLM calls. Leave unset only when running offline smoke tests. |
| `CODE_PUPPY_TEST_FAST` | Puts the CLI into fast/lean mode | Defaults to `1` inside the fixtures so prompts skip nonessential animation. |
| `MODEL_NAME` | Optional override for the default model | Useful when pointing at alternate providers (OpenAI, Gemini, etc.). |
| Provider-specific keys | `OPENAI_API_KEY`, `GEMINI_API_KEY`, `SYN_API_KEY`, … | Set whichever keys you expect the CLI to fall back to. The harness deliberately preserves ambient environment variables so you can swap providers without code changes. |

To target a different default provider, export the appropriate key(s) plus `MODEL_NAME` before running pytest. The harness will inject your environment verbatim, so the CLI behaves exactly as it would in production.

## Running the tests
```bash
uv run pytest tests/integration/test_smoke.py
uv run pytest tests/integration/test_cli_harness_foundations.py
```

Future happy-path suites (see bd-2) will live alongside the existing smoke and foundation coverage. When those land, run the entire folder to exercise the interactive flows:

```bash
uv run pytest tests/integration
```

Each spawned CLI writes diagnostic logs to `tmp/.../cli_output.log`. When a test fails, open that file to inspect prompts, responses, and terminal control sequences. The `SpawnResult.read_log()` helper used inside the tests reads from the same file.

## Failure handling
- The harness retries prompt expectations with exponential backoff (see `RetryPolicy`) to smooth transient delays.
- Final cleanup terminates the child process and deletes the temporary HOME. If you need to keep artifacts for debugging, set `CODE_PUPPY_KEEP_TEMP_HOME=1` before running pytest; the fixtures honor that flag and skip deletion.
- Timeout errors surface the last 100 characters captured by pyexpect, making it easier to diagnose mismatched prompts.

## Customizing the fixtures
- Override `integration_env` by parametrizing tests or using `monkeypatch` to inject additional environment keys.
- Pass different CLI arguments by calling `cli_harness.spawn(args=[...], env=...)` inside your test.
- Use `spawned_cli.send("\r")` and `spawned_cli.sendline("command\r")` helpers whenever you need to interact with the prompt; both enforce the carriage-return quirks we observed during manual testing.

With the harness and documentation in place, bd-1 is considered complete; additional feature coverage can now focus on bd-2 and beyond.
