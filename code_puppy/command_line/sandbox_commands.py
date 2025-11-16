"""Command handlers for sandbox management.

This module contains @register_command decorated handlers for managing
the sandboxing system.
"""

import uuid

from code_puppy.command_line.command_registry import register_command
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning


@register_command(
    name="sandbox",
    description="Manage code execution sandboxing",
    usage="/sandbox <enable|disable|status|allow-domain|allow-path>",
    category="security",
)
def handle_sandbox_command(command: str) -> bool:
    """Manage sandbox settings."""
    try:
        from code_puppy.sandbox import SandboxConfig
    except ImportError:
        emit_error("Sandboxing is not available in this installation")
        return True

    tokens = command.split()

    # Show help if no subcommand
    if len(tokens) == 1:
        help_text = """
# 🔒 Sandbox Management

The sandbox provides filesystem and network isolation for shell commands.

## Commands

- `/sandbox enable` - Enable sandboxing (opt-in)
- `/sandbox disable` - Disable sandboxing
- `/sandbox status` - Show current sandbox status
- `/sandbox allow-domain <domain>` - Add domain to network allowlist
- `/sandbox allow-path <path>` - Add path to filesystem allowlist
- `/sandbox allow-read-path <path>` - Add read-only path to allowlist
- `/sandbox test` - Test if sandboxing is available on this system

## Features

**Filesystem Isolation:**
- Restricts file access to current working directory
- Blocks access to sensitive paths (~/.ssh, ~/.aws, etc.)
- Uses bubblewrap (Linux) or sandbox-exec (macOS)

**Network Isolation:**
- Routes traffic through monitored proxy
- Domain allowlist with user approval
- Pre-approved: package registries, git hosts, AI APIs

## Example Usage

```bash
/sandbox enable
/sandbox allow-domain example.com
/sandbox allow-path /tmp
/sandbox status
```
"""
        emit_info(help_text)
        return True

    subcommand = tokens[1].lower()

    # Enable sandboxing
    if subcommand == "enable":
        try:
            from code_puppy.config import set_sandbox_enabled

            set_sandbox_enabled(True)
            config = SandboxConfig()
            config.enabled = True
            emit_success("✅ Sandbox enabled! Shell commands will run in isolated environment.")
        except Exception as e:
            emit_error(f"Failed to enable sandbox: {e}")
        return True

    # Disable sandboxing
    elif subcommand == "disable":
        try:
            from code_puppy.config import set_sandbox_enabled

            set_sandbox_enabled(False)
            config = SandboxConfig()
            config.enabled = False
            emit_warning("⚠️  Sandbox disabled. Commands will run without isolation.")
        except Exception as e:
            emit_error(f"Failed to disable sandbox: {e}")
        return True

    # Show status
    elif subcommand == "status":
        try:
            from code_puppy.sandbox import SandboxCommandWrapper

            config = SandboxConfig()
            wrapper = SandboxCommandWrapper(config)
            status = wrapper.get_status()

            status_text = f"""
# Sandbox Status

**Enabled:** {"✅ Yes" if status['enabled'] else "❌ No"}
**Filesystem Isolation:** {"✅ Enabled" if status['filesystem_isolation'] else "❌ Disabled"}
**Network Isolation:** {"✅ Enabled" if status['network_isolation'] else "❌ Disabled"}

**Platform:** {status['isolator_platform']}
**Isolator:** {status['isolator']}
**Available:** {"✅ Yes" if status['isolator_available'] else "❌ No"}
**Proxy Running:** {"✅ Yes" if status['proxy_running'] else "❌ No"}

**Allowed Domains:** {status['allowed_domains_count']} domains
**Allowed Read Paths:** {len(status['allowed_read_paths'])} paths
**Allowed Write Paths:** {len(status['allowed_write_paths'])} paths
"""
            if status['allowed_read_paths']:
                status_text += "\n**Read Paths:**\n"
                for path in status['allowed_read_paths']:
                    status_text += f"  - {path}\n"

            if status['allowed_write_paths']:
                status_text += "\n**Write Paths:**\n"
                for path in status['allowed_write_paths']:
                    status_text += f"  - {path}\n"

            emit_info(status_text)
        except Exception as e:
            emit_error(f"Failed to get sandbox status: {e}")
        return True

    # Test availability
    elif subcommand == "test":
        try:
            from code_puppy.sandbox import SandboxCommandWrapper

            wrapper = SandboxCommandWrapper()
            available = wrapper.is_sandboxing_available()

            if available:
                emit_success(
                    "✅ Sandboxing is available on this system! "
                    "Use `/sandbox enable` to activate it."
                )
            else:
                emit_warning(
                    "⚠️  Sandboxing is not available on this system.\n\n"
                    "**Linux:** Install bubblewrap: `apt install bubblewrap` or `yum install bubblewrap`\n"
                    "**macOS:** sandbox-exec is built-in but may require specific configurations.\n"
                    "**Windows:** Sandboxing is not yet supported."
                )
        except Exception as e:
            emit_error(f"Failed to test sandbox availability: {e}")
        return True

    # Allow domain
    elif subcommand == "allow-domain":
        if len(tokens) < 3:
            emit_error("Usage: /sandbox allow-domain <domain>")
            return True

        domain = tokens[2]
        try:
            config = SandboxConfig()
            config.add_allowed_domain(domain)
            emit_success(f"✅ Added '{domain}' to network allowlist")
        except Exception as e:
            emit_error(f"Failed to add domain: {e}")
        return True

    # Allow write path
    elif subcommand == "allow-path":
        if len(tokens) < 3:
            emit_error("Usage: /sandbox allow-path <path>")
            return True

        path = " ".join(tokens[2:])  # Support paths with spaces
        try:
            config = SandboxConfig()
            config.add_allowed_write_path(path)
            emit_success(f"✅ Added '{path}' to write allowlist")
        except Exception as e:
            emit_error(f"Failed to add path: {e}")
        return True

    # Allow read path
    elif subcommand == "allow-read-path":
        if len(tokens) < 3:
            emit_error("Usage: /sandbox allow-read-path <path>")
            return True

        path = " ".join(tokens[2:])  # Support paths with spaces
        try:
            config = SandboxConfig()
            config.add_allowed_read_path(path)
            emit_success(f"✅ Added '{path}' to read allowlist")
        except Exception as e:
            emit_error(f"Failed to add read path: {e}")
        return True

    else:
        emit_error(f"Unknown subcommand: {subcommand}")
        emit_info("Use `/sandbox` to see available commands")

    return True
