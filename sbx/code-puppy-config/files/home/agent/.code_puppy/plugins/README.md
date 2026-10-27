# User plugins

Plugins are Python code that runs inside Code Puppy at import time.
Only add plugins here that you wrote or have reviewed — treat this
directory like `~/.code_puppy/plugins/` on your own machine, because
that is exactly where the kit installs it.

Layout: one subdirectory per plugin containing `register_callbacks.py`
that calls `code_puppy.callbacks.register_callback(...)` at module
scope. Keep runtime state outside the plugin directory.

`hello_sandbox/` is a minimal, inert example. Delete it freely.
