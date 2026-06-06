"""Theme picker plugin for Code Puppy - banner + content + inline + terminal theming."""

# Re-apply any persisted overrides as soon as the plugin loads so the user's
# saved theme survives Code Puppy restarts. Banner colors live in puppy.cfg
# (read lazily by the renderer), but content styles, Rich color remaps, and
# OSC terminal palettes live in mutable state that resets each process.
from . import content_styles as _cs
from . import osc_palette as _osc
from . import rich_themes as _rt

for _mod in (_cs, _rt, _osc):
    try:
        _mod.reapply_from_config()
    except Exception:
        # Never let theme persistence break Code Puppy startup.
        pass
