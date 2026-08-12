from pathlib import Path
from code_puppy.config import CONFIG_DIR


def get_claude_plugins_dir() -> Path:
    """Get the directory where Claude plugins are installed."""
    return Path(CONFIG_DIR) / "claude_plugins"


def get_installed_plugins() -> list[str]:
    """Get a list of installed Claude plugin names."""
    plugins_dir = get_claude_plugins_dir()
    if not plugins_dir.exists():
        return []

    return [
        item.name
        for item in plugins_dir.iterdir()
        if item.is_dir() and not item.name.startswith(".")
    ]
