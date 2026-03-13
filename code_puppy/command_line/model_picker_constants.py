"""Shared constants for model picker formatting.

These constants are used by both the interactive model picker (core_commands.py)
and the model completion system (model_picker_completion.py) to ensure
consistent formatting and parsing of model choices.
"""

# Prefixes for model choices in the picker
CURRENT_MODEL_PREFIX = "✓ "
OTHER_MODEL_PREFIX = "  "

# Suffix for the currently active model
CURRENT_MODEL_SUFFIX = " (current)"
