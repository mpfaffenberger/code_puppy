"""Model switcher plugin — theme-style split-panel /model picker."""

# No eager work at import time: everything (including the prompt_toolkit
# picker) is deferred to the register_callbacks handler to keep startup lean.
