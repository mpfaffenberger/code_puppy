# Code Puppy on Android (Termux)

Android/Termux is a constrained target. Android uses bionic libc, so PyPI's
manylinux wheels do not apply, and several mandatory dependencies ship Rust/C
native extensions with no Termux-compatible wheels — they compile on-device.
As a result a first install can take materially longer than a normal
wheel-based desktop install.

The `code-puppy-bootstrap` planner provides an **environment-aware install
recommendation**: it exposes the Android/Termux prerequisites and platform
constraints *before* the expensive package installation begins. It runs without
the Code Puppy runtime/provider stack, so you can run it before a full install
exists.

## Running the planner

From a source checkout, before installing Code Puppy:

```bash
git clone https://github.com/mpfaffenberger/code_puppy.git
cd code_puppy
python -m code_puppy.bootstrap detect
python -m code_puppy.bootstrap plan
```

After Code Puppy is installed, the same planner is available as a console
script:

```bash
code-puppy-bootstrap detect
code-puppy-bootstrap plan --json
```

## System packages

Install the build toolchain from the Termux repositories first. On Termux the
following are **required** because mandatory dependencies compile on-device:

```bash
pkg install rust clang
```

- `rust` — mandatory dependencies such as `pydantic-core` and `cryptography`
  are Rust native extensions with no Termux-compatible wheels.
- `clang` — mandatory dependencies such as `cryptography` and `Pillow` build C
  native extensions on-device.

Optional (improves the experience, not required — Code Puppy degrades
gracefully without it; it is installed via `pip` automatically on non-Android
platforms):

```bash
pkg install ripgrep
```

## Installing Code Puppy

`uv` is available from the Termux package repository:

```bash
pkg install uv
uv tool install --refresh code-puppy
code-puppy -i
```

If you prefer not to use `uv`, the planner falls back to a `pip` command.

## Profiles

| Profile | Extras | When |
| --- | --- | --- |
| `lean` (default) | none | Minimal first install. Safe everywhere. |
| `full` | every extra applicable to the platform | Only on known-good hosts. |

Optional extras gated to another platform (for example a macOS-only
integration) are never prescribed on Android, because installing them there
would be a no-op.
