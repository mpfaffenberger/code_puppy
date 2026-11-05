# Early startup hook

Some setup has to happen **before** Code Puppy imports its heavy dependencies
(pydantic-ai, prompt_toolkit, rich, ...). The classic case is sanitising a broken
`HTTP_PROXY` / `SSL_CERT_FILE` so those imports do not fail. Regular plugins cannot do
this: they load after the heavy imports, through the callback system.

`code_puppy/main.py` therefore gives in-tree plugins one early turn:

```
splash starts -> error hooks -> plugin early_startup hooks -> heavy cli_runner import -> splash stops
```

The hooks run inside the splash window, so the user is already looking at the neon paw
while they work.

## Writing one

Add `code_puppy/plugins/<name>/early_startup.py` with a zero-argument `run()`:

```python
# code_puppy/plugins/my_plugin/early_startup.py
import os


def run() -> None:
    if os.environ.get("MY_PLUGIN_SKIP_EARLY"):  # your own kill switch, see below
        return
    os.environ.pop("SOME_BROKEN_VARIABLE", None)
```

## Rules

- **Keep it light.** Stdlib-only is the goal, for the hook and for the plugin package's
  `__init__.py` (importing `code_puppy.plugins.<name>.early_startup` imports that package
  first). Anything heavy imported here delays the first prompt and defeats the purpose.
- **In-tree plugins only.** `code_puppy/plugins/*/early_startup.py` is scanned; user
  (`~/.code_puppy/plugins`) and project (`.code_puppy/plugins`) plugins are untrusted code that
  load later through the trust-gated loader, never from here. Directories starting with `_`
  or `.` are skipped.
- **No enable/disable list.** Configuration is not loaded yet, so the plugin disable list is not
  consulted. If your hook needs an opt-out, read your own environment variable.
- **Failures are contained.** A hook that raises is recorded in `errors.log` and skipped; the
  remaining hooks and startup carry on. `KeyboardInterrupt` and `SystemExit` still propagate.
- **Order** is alphabetical by plugin directory name. Do not depend on another plugin's hook.

The discovery code is `code_puppy/early_startup.py` (stdlib-only, like `code_puppy/splash.py`).
