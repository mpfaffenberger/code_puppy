import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_plugin_callbacks():
    """Dynamically load register_callbacks.py from all plugin submodules."""
    plugins_dir = Path(__file__).parent

    # Iterate through all subdirectories in the plugins folder
    for item in plugins_dir.iterdir():
        if item.is_dir() and not item.name.startswith("_"):
            plugin_name = item.name
            callbacks_file = item / "register_callbacks.py"

            if callbacks_file.exists():
                try:
                    # Import the register_callbacks module dynamically
                    module_name = f"code_puppy.plugins.{plugin_name}.register_callbacks"
                    logger.debug(f"Loading plugin callbacks from {module_name}")
                    importlib.import_module(module_name)
                    logger.info(
                        f"Successfully loaded callbacks from plugin: {plugin_name}"
                    )
                except ImportError as e:
                    logger.warning(
                        f"Failed to import callbacks from plugin {plugin_name}: {e}"
                    )
                except Exception as e:
                    logger.error(f"Unexpected error loading plugin {plugin_name}: {e}")
