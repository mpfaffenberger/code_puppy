# CLI Integration Harness

## Overview
This folder contains the reusable pyexpect harness that powers Code Puppy's end-to-end CLI integration tests. The harness lives in `tests/integration/cli_expect/harness.py` and exposes pytest fixtures via `tests/conftest.py`. Each test run boots the real `code-puppy` executable inside a temporary HOME, writes a throwaway configuration (including `puppy.cfg` and `motd.txt`), and captures the entire session into a per-run `cli_output.log` file for debugging.

## Prerequisites
- The CLI must be installed locally via `uv sync` or equivalent so `uv run pytest …` launches the editable project binary.
- Set the environment you want to exercise; by default the fixtures read the active shell environment and only override a few keys for test hygiene.
- Export a **real** `CEREBRAS_API_KEY` when you intend to hit live Cerebras models. The harness falls back to `fake-key-for-ci` so tests can run offline, but that key will be rejected by the remote API.

## Required environment variables

**⚠️ MANDATORY:** The integration tests will refuse to run unless both `CI` and `CODE_PUPPY_TEST_FAST` are set. This prevents tests from hanging due to Rich's `Live()` display in pexpect PTY environments.

| Variable | Purpose | Required | Notes |
| --- | --- | --- | --- |
| `CI` | Disables Rich Live() display | **Yes** | Set to `1` or `true`. Prevents streaming handler from using interactive display. |
| `CODE_PUPPY_TEST_FAST` | Puts the CLI into fast/lean mode | **Yes** | Set to `1` or `true`. Skips nonessential animations. |
| `SYN_API_KEY` | Primary provider for live integration coverage | For LLM tests | Required for real LLM calls with synthetic-GLM-4.7 model. |
| `MODEL_NAME` | Optional override for the default model | No | Useful when pointing at alternate providers (OpenAI, Gemini, etc.). |
| Provider-specific keys | `OPENAI_API_KEY`, `GEMINI_API_KEY`, `CEREBRAS_API_KEY`, … | No | Set whichever keys you expect the CLI to fall back to. |

To target a different default provider, export the appropriate key(s) plus `MODEL_NAME` before running pytest. The harness will inject your environment verbatim, so the CLI behaves exactly as it would in production.

## Running the tests

**Always set the required environment variables:**

```bash
# Run specific test files
CI=1 CODE_PUPPY_TEST_FAST=1 uv run pytest tests/integration/test_smoke.py
CI=1 CODE_PUPPY_TEST_FAST=1 uv run pytest tests/integration/test_cli_harness_foundations.py

# Run all integration tests
CI=1 CODE_PUPPY_TEST_FAST=1 uv run pytest tests/integration/

# Or export them for your session
export CI=1
export CODE_PUPPY_TEST_FAST=1
uv run pytest tests/integration/
```

If you forget to set the environment variables, you'll see a helpful error message explaining what's needed.

Each spawned CLI writes diagnostic logs to `tmp/.../cli_output.log`. When a test fails, open that file to inspect prompts, responses, and terminal control sequences. The `SpawnResult.read_log()` helper used inside the tests reads from the same file.

## Failure handling
- The harness retries prompt expectations with exponential backoff (see `RetryPolicy`) to smooth transient delays.
- Final cleanup terminates the child process and selectively deletes files created during the test run. By default, only test-created files are removed, preserving any pre-existing files in reused HOME directories. If you need to keep artifacts for debugging, set `CODE_PUPPY_KEEP_TEMP_HOME=1` before running pytest; the fixtures honor that flag and skip deletion entirely.
- To use the original "delete everything" cleanup behavior, set `CODE_PUPPY_SELECTIVE_CLEANUP=false`.
- Timeout errors surface the last 100 characters captured by pyexpect, making it easier to diagnose mismatched prompts.

## Customizing the fixtures
- Override `integration_env` by parametrizing tests or using `monkeypatch` to inject additional environment keys.
- Pass different CLI arguments by calling `cli_harness.spawn(args=[...], env=...)` inside your test.
- Use `spawned_cli.send("\r")` and `spawned_cli.sendline("command\r")` helpers whenever you need to interact with the prompt; both enforce the carriage-return quirks we observed during manual testing.

With the harness and documentation in place, bd-1 is considered complete; additional feature coverage can now focus on bd-2 and beyond.
