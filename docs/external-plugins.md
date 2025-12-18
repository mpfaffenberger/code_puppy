# External Plugins for Code Puppy

Code Puppy supports **external plugins** that can live anywhere on your filesystem.
This enables plugins to be developed and distributed as separate git repositories,
making it easy to share plugins across teams or the community.

## Overview

Code Puppy loads plugins from three sources:

1. **Built-in plugins**: Shipped with Code Puppy in `code_puppy/plugins/`
2. **User plugins**: Installed in `~/.code_puppy/plugins/`
3. **External plugins**: Registered in `~/.code_puppy/external_plugins.json`

External plugins are the most flexible option. They can live in any directory
(like a git repo you've cloned) and register themselves in the central registry.

## Quick Start

### Installing an External Plugin

```bash
# Clone the plugin repository
git clone https://github.com/example/my-awesome-plugin.git ~/repos/my-awesome-plugin

# Run the setup script
cd ~/repos/my-awesome-plugin
./setup.sh
```

The `setup.sh` script registers the plugin in Code Puppy's registry.
Restart Code Puppy to load the new plugin.

### Uninstalling an External Plugin

```bash
cd ~/repos/my-awesome-plugin
./uninstall.sh
```

This removes the plugin from the registry. The files remain on disk.

## Creating an External Plugin

### Directory Structure

```
my-plugin/
├── plugin.json              # Plugin metadata
├── register_callbacks.py    # Entry point (REQUIRED)
├── setup.sh                 # Installation script
├── uninstall.sh             # Uninstallation script
├── agents/                  # Optional: JSON agent definitions
│   └── my-agent.json
├── tools/                   # Optional: Custom tools
│   └── my_tools.py
└── README.md
```

### plugin.json

Optional metadata file describing your plugin:

```json
{
    "name": "my-awesome-plugin",
    "version": "1.0.0",
    "description": "A plugin that does awesome things",
    "author": "Your Name",
    "repository": "https://github.com/you/my-awesome-plugin"
}
```

### register_callbacks.py

The entry point for your plugin. This file is executed when Code Puppy loads:

```python
"""My Awesome Plugin for Code Puppy.

This plugin adds custom functionality to Code Puppy.
"""

from code_puppy.callbacks import register_callback


def my_startup_hook() -> None:
    """Called when Code Puppy starts."""
    print("My Awesome Plugin loaded!")


def my_custom_command(command: str, name: str) -> bool | str | None:
    """Handle custom slash commands.

    Args:
        command: The full command string (e.g., "/mycommand arg1 arg2").
        name: The command name without slash (e.g., "mycommand").

    Returns:
        True if handled, string to process as input, or None if not handled.
    """
    if name == "mycommand":
        print("Executing my custom command!")
        return True
    return None


def my_command_help() -> list[tuple[str, str]]:
    """Return help entries for custom commands.

    Returns:
        List of (command_name, description) tuples.
    """
    return [("mycommand", "Does something awesome")]


# Register callbacks
register_callback("startup", my_startup_hook)
register_callback("custom_command", my_custom_command)
register_callback("custom_command_help", my_command_help)
```

### setup.sh

Installation script that registers the plugin:

```bash
#!/bin/bash
# Setup script for My Awesome Plugin

set -e

PLUGIN_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_NAME="my-awesome-plugin"
DESCRIPTION="A plugin that does awesome things"

echo "Installing $PLUGIN_NAME..."

# Register using Python
python3 << EOF
from code_puppy.plugins import register_external_plugin

success = register_external_plugin(
    name="$PLUGIN_NAME",
    path="$PLUGIN_DIR",
    description="$DESCRIPTION",
)

if success:
    print("✅ Successfully installed $PLUGIN_NAME")
    print("   Restart Code Puppy to load the plugin.")
else:
    print("❌ Failed to install $PLUGIN_NAME")
    exit(1)
EOF
```

### uninstall.sh

Uninstallation script that removes the plugin from the registry:

```bash
#!/bin/bash
# Uninstall script for My Awesome Plugin

set -e

PLUGIN_NAME="my-awesome-plugin"

echo "Uninstalling $PLUGIN_NAME..."

python3 << EOF
from code_puppy.plugins import unregister_external_plugin

success = unregister_external_plugin("$PLUGIN_NAME")

if success:
    print("✅ Successfully uninstalled $PLUGIN_NAME")
    print("   Restart Code Puppy for changes to take effect.")
else:
    print("❌ Plugin not found in registry")
EOF
```

## Available Callback Phases

Plugins can hook into various phases of Code Puppy's lifecycle:

| Phase | Type | Description |
|-------|------|-------------|
| `startup` | async | Called when Code Puppy starts |
| `shutdown` | sync | Called when Code Puppy exits |
| `invoke_agent` | async | Called when the agent is invoked |
| `agent_exception` | async | Called when the agent throws an exception |
| `version_check` | async | Called during version checking |
| `edit_file` | sync | Called before file edits |
| `delete_file` | sync | Called before file deletions |
| `run_shell_command` | async | Called before shell commands |
| `run_shell_command_output` | async | Called after shell command output |
| `load_model_config` | sync | Called to load model configuration |
| `load_prompt` | sync | Called to load system prompt |
| `agent_reload` | sync | Called when agent is reloaded |
| `custom_command` | sync | Handle custom slash commands |
| `custom_command_help` | sync | Provide help for custom commands |
| `file_permission` | sync | Check file operation permissions |

## The Registry File

External plugins are tracked in `~/.code_puppy/external_plugins.json`:

```json
{
    "version": 1,
    "plugins": [
        {
            "name": "my-awesome-plugin",
            "path": "/Users/you/repos/my-awesome-plugin",
            "enabled": true,
            "installed_at": "2025-12-17T12:00:00",
            "description": "A plugin that does awesome things"
        }
    ]
}
```

### Disabling a Plugin

To temporarily disable a plugin without uninstalling, set `"enabled": false`:

```json
{
    "name": "my-awesome-plugin",
    "path": "/Users/you/repos/my-awesome-plugin",
    "enabled": false
}
```

## Programmatic API

You can manage external plugins programmatically:

```python
from code_puppy.plugins import (
    register_external_plugin,
    unregister_external_plugin,
    list_external_plugins,
    get_external_plugins_registry_path,
)

# Register a plugin
register_external_plugin(
    name="my-plugin",
    path="/path/to/plugin",
    description="My awesome plugin",
    enabled=True,
)

# List all external plugins
for plugin in list_external_plugins():
    print(f"{plugin['name']}: {plugin['path']}")

# Unregister a plugin
unregister_external_plugin("my-plugin")

# Get the registry file path
print(get_external_plugins_registry_path())
```

## Best Practices

1. **Use unique plugin names**: Avoid conflicts with other plugins.

2. **Handle import errors gracefully**: Your plugin should not crash Code Puppy.

3. **Log appropriately**: Use Python's `logging` module for debug output.

4. **Document your plugin**: Include a README with installation and usage instructions.

5. **Version your plugin**: Use semantic versioning in `plugin.json`.

6. **Test your callbacks**: Ensure your callbacks don't throw unexpected exceptions.

## Troubleshooting

### Plugin not loading

1. Check the registry file exists: `cat ~/.code_puppy/external_plugins.json`
2. Verify the path is correct and the directory exists
3. Ensure `register_callbacks.py` exists in the plugin directory
4. Check for import errors in your plugin code

### Viewing loaded plugins

Code Puppy logs which plugins were loaded on startup. Check the logs or add
logging to your plugin's startup callback.

### Conflicts with other plugins

If multiple plugins register the same custom command, the first one loaded wins.
Use unique command names to avoid conflicts.
