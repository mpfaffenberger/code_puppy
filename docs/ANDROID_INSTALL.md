# Code Puppy on Android / Termux

This guide is for a **fresh Termux install on Android**. Code Puppy works on
Android, but it is not a normal desktop Python install: several dependencies use
native code, and Android does not receive the same PyPI wheels as Linux/macOS.

The installer path below is intentionally conservative: install the Termux build
toolchain first, keep optional heavyweight features detached, then install the
lean Code Puppy runtime.

## 0. Use the real Termux

Install Termux from F-Droid or GitHub releases. The Play Store build is stale and
will cause weird package failures. Weird as in "why is my phone haunted?" weird.

## 1. Recommended: run the bootstrap wizard

After installing Termux, run:

```bash
pkg update
pkg install python git uv rust clang
uvx --from code-puppy code-puppy-bootstrap wizard
```

Install `uv` from Termux (`pkg install uv`) instead of PyPI. On Android, PyPI may
fall back to building `uv` from source, which needs Rust before you even have the
installer. That is a very silly bootstrapping sandwich, so we skip it.

The wizard detects your device, explains each step, asks before changing state,
and finishes by verifying `code-puppy --help`.

For scripted installs:

```bash
uvx --from code-puppy code-puppy-bootstrap wizard --yes
```

To preview only:

```bash
uvx --from code-puppy code-puppy-bootstrap wizard --dry-run
```

## 2. Manual install path

If you prefer to drive the meat wagon yourself:

```bash
pkg update
pkg install python git uv rust clang ripgrep proot
uv tool install --refresh code-puppy
code-puppy -i
```

### Why `rust clang` are required

`pydantic-core` is a required dependency of `pydantic`, which Code Puppy uses
through `pydantic-ai`. PyPI does not currently publish Android/Termux wheels for
`pydantic-core`, and Termux does not ship a prebuilt `python-pydantic` package in
the default repo. A fresh Android user therefore needs the Termux Rust/C build
toolchain so pip/uv can build that dependency locally. Install it before running
`uvx --from code-puppy ...`, because `uvx` must install Code Puppy before the
wizard code can execute.

The base install deliberately avoids other native-heavy optional packages:

- Playwright is in the `[browser]` extra.
- PyPI's bundled `ripgrep` package is in the `[search]` extra; the Android path
  uses Termux's system `rg` from `pkg install ripgrep` instead.
- Pillow is in the `[images]` extra.
- `pydantic-ai-slim[openai]` is intentionally avoided in base because it pulls
  `tiktoken` and `regex`, which require additional native builds on Android.

Android support does not remove search support; it only prevents the PyPI
`ripgrep` package from being installed on Android/Termux, where it is known to
fail. Desktop and CI installs using `[search]` remain unchanged.

## 3. Optional features

Install these only after the lean runtime is working.

```bash
# Image loading / resizing tools
uv tool install --refresh 'code-puppy[images]'

# From a source checkout / editable install on Android, keep search desktop-only.
# Plain `uv sync` installs dev tools such as Ruff and may try to build them
# from source on Android; use --no-dev for runtime validation.
uv sync --no-dev --python "$(command -v python)"

# Or, from an activated lean venv:
uv pip install -e '.[images]'

# Desktop/browser automation environments only; not recommended on native Android
uv tool install --refresh 'code-puppy[browser]'

# Desktop/CI only: PyPI ripgrep bundle for non-Termux systems.
# Android/Termux should prefer: pkg install ripgrep
uv tool install --refresh 'code-puppy[search]'

# DBOS-backed durable execution
uv tool install --refresh 'code-puppy[durable]'
```

## 4. Verify the install

```bash
code-puppy --help
code-puppy-bootstrap detect
code-puppy-bootstrap plan --profile auto
```

On Android/Termux, the plan should select `android-termux-lean`.

## Troubleshooting

### `aarch64-linux-android-clang: No such file or directory`

Install the compiler:

```bash
pkg install clang
```

### `Rust not found` or `maturin` fails building `pydantic-core`

Install Rust:

```bash
pkg install rust
```

Then retry:

```bash
uv tool install --refresh code-puppy
```

### `rg` / search tools are unavailable

Install Termux ripgrep:

```bash
pkg install ripgrep
```

### Image tools say Pillow is missing

That is expected on the lean Android install. Reattach the optional image extra:

```bash
uv tool install --refresh 'code-puppy[images]'
```

### The install is slow

Compiling Rust/C dependencies on a phone can take a while. Keep Termux in the
foreground, keep the screen awake if needed, and avoid running it while Android
is aggressively saving battery.
