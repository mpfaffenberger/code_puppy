"""Theme picker plugin for Code Puppy - banner + content + inline + terminal theming."""

# Reapply persisted overrides at load: banner colors persist in puppy.cfg, while
# content styles, Rich remaps, and OSC palettes reset each process.
from . import content_styles as _cs
from . import osc_palette as _osc
from . import rich_themes as _rt

for _mod in (_cs, _rt, _osc):
    try:
        _mod.reapply_from_config()
    except Exception:
        # Never let theme persistence break Code Puppy startup.
        pass
