# Linters & Git Hooks

This repo uses Lefthook to run fast, low-drama git hooks.

## What runs

- pre-commit
  - isort on staged `*.py` (black profile), restages fixes
  - ruff format on staged `*.py`
  - ruff check --fix on staged `*.py`
  - pnpm check (only if pnpm is installed)
- pre-push
  - pytest (via `uv run` if available, fallback to `pytest`)

## Smart fallbacks

- If `isort` isn’t available, we fall back to Ruff’s import sorter: `ruff check --select I --fix`.
- All commands prefer `uv run` when present; otherwise run the binary directly.
- Hooks operate only on `{staged_files}` for speed and DRY.

## Install hooks locally

```bash
# one-time install
lefthook install

# run manually
lefthook run pre-commit
lefthook run pre-push
```

If `lefthook` isn’t installed, commits still work — but hooks won’t run. Enforcement should also exist in CI.

## Files changed

- `lefthook.yml`: hook definitions
- `tests/test_model_factory.py`: fixed import location for E402 and added missing import

## Notes

- Keep hooks fast and non-annoying. Use `{staged_files}` and `stage_fixed: true`.
- Prefer ruff + isort for Python. If you don’t have `isort`, no problem — Ruff’s I-rules will handle import ordering.
- CI should run the same checks on all files (not just staged).
