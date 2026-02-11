# How to Use MCP Servers

## What You'll Learn
By the end of this guide, you'll be able to discover, install, configure, and manage MCP (Model Context Protocol) servers that extend Code Puppy's capabilities with external tools and integrations.

## Prerequisites
- Code Puppy installed and running
- Completed the [Quick Start Tutorial](../Getting-Started/QuickStart)

## What Are MCP Servers?

MCP servers are plugins that give Code Puppy access to external tools and data sources — things like databases, file systems, APIs, and more. When you install an MCP server, Code Puppy gains new abilities it can use to help you with tasks.

For example, installing a PostgreSQL MCP server lets Code Puppy query your database directly. A filesystem server lets it access directories outside the current project.

## Quick Version

```
/mcp search database          # Find servers related to databases
/mcp install postgres          # Install a server from the catalog
/mcp start postgres            # Start the server
/mcp                           # View status dashboard
```

## Detailed Steps

### 1. Browse Available Servers

Code Puppy includes a catalog of 30+ pre-configured MCP servers. You can search the catalog or browse popular servers.

**Search for servers by keyword:**
```
/mcp search database
```

You'll see a table with matching servers:
```
  ID                  Name               Category     Description                Tags
  postgres            PostgreSQL ✓ ⭐     Database     Query PostgreSQL databases  sql, database...
  sqlite              SQLite ✓           Database     Work with SQLite files      sql, local...
```

> [!TIP]
> Run `/mcp search` with no keyword to see the most popular servers.

**Legend:**
- ✓ = Verified server
- ⭐ = Popular / widely used

### 2. Install a Server from the Catalog

**Install directly by ID:**
```
/mcp install postgres
```

You'll be guided through the setup:
1. **Name** — Accept the default name or enter a custom one
2. **Environment variables** — Provide any required API keys or credentials
3. **Command line arguments** — Configure paths, ports, or other settings

> [!NOTE]
> If an environment variable is already set in your shell, Code Puppy detects it automatically and shows "Already set."

**Browse and install interactively:**
```
/mcp install
```

This opens an interactive browser where you can:
- Browse servers by category
- Preview server details before installing
- Add a custom server configuration

Use the arrow keys to navigate, Enter to select, and Escape to go back.

### 3. Install a Custom Server

If the server you need isn't in the catalog, you can add a custom one.

Run `/mcp install` and select **➕ Custom Server** from the category list, or use the interactive form.

Code Puppy supports three server types:

| Type | Use For | Example |
|------|---------|----------|
| `stdio` | Local command-line tools | `npx @modelcontextprotocol/server-filesystem /path` |
| `http` | Remote HTTP-based servers | `http://localhost:8080/mcp` |
| `sse` | Server-Sent Events servers | `http://localhost:8080/sse` |

**Example stdio configuration:**
```json
{
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
  "env": {
    "NODE_ENV": "production"
  },
  "timeout": 30
}
```

**Example HTTP configuration:**
```json
{
  "type": "http",
  "url": "http://localhost:8080/mcp",
  "headers": {
    "Authorization": "Bearer $MY_API_KEY",
    "Content-Type": "application/json"
  },
  "timeout": 30
}
```

### 4. Start and Stop Servers

**Start a specific server:**
```
/mcp start filesystem
```

**Start all configured servers:**
```
/mcp start-all
```

**Stop a specific server:**
```
/mcp stop filesystem
```

**Stop all running servers:**
```
/mcp stop-all
```

**Restart a server** (useful after editing config):
```
/mcp restart filesystem
```

### 5. Check Server Status

**View the status dashboard:**
```
/mcp
```

This displays a table showing all servers with their status:
```
🔌 MCP Server Status Dashboard
  Name         Type    State   Enabled   Uptime      Status
  filesystem   STDIO   ✓       ✓         2h 15m      OK
  postgres     STDIO   ✗       ✓         —           Stopped
```

**Status indicators:**
| Icon | Meaning |
|------|---------|
| ✓ | Running |
| ✗ | Stopped |
| ⚠ | Error |
| ⏸ | Quarantined (temporarily disabled due to errors) |

**Get detailed status for one server:**
```
/mcp status filesystem
```

### 6. Test Server Connectivity

Verify a server is working properly:
```
/mcp test filesystem
```

You'll see:
```
🔍 Testing connectivity to server: filesystem
✓ Server instance created successfully
  • Server type: stdio
  • Server enabled: True
  • Server quarantined: False
✓ Connectivity test passed for: filesystem
```

### 7. View Server Logs

**List servers with available logs:**
```
/mcp logs
```

**View recent logs for a server (last 50 lines):**
```
/mcp logs filesystem
```

**View a specific number of lines:**
```
/mcp logs filesystem 100
```

**View all logs:**
```
/mcp logs filesystem all
```

**Clear logs for a server:**
```
/mcp logs filesystem --clear
```

### 8. Edit a Server Configuration

Modify an existing server's settings:
```
/mcp edit filesystem
```

This opens the same interactive form used during installation, pre-populated with the server's current configuration. Make your changes and save.

> [!TIP]
> After editing a server, restart it with `/mcp restart <name>` to apply the changes.

### 9. Remove a Server

Remove a server you no longer need:
```
/mcp remove filesystem
```

This stops the server and removes it from your configuration.

## Command Reference

| Command | Description |
|---------|-------------|
| `/mcp` | Show the status dashboard |
| `/mcp list` | List all registered servers |
| `/mcp search [query]` | Search the server catalog |
| `/mcp install [id]` | Install a server (interactive if no ID given) |
| `/mcp start <name>` | Start a specific server |
| `/mcp start-all` | Start all servers |
| `/mcp stop <name>` | Stop a specific server |
| `/mcp stop-all` | Stop all running servers |
| `/mcp restart <name>` | Restart a specific server |
| `/mcp status [name]` | Show detailed status (all or specific) |
| `/mcp test <name>` | Test server connectivity |
| `/mcp logs [name] [lines]` | View server logs |
| `/mcp edit <name>` | Edit a server's configuration |
| `/mcp remove <name>` | Remove a server |
| `/mcp help` | Show help for all MCP commands |

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Server shows ⚠ Error | Server crashed or misconfigured | Check logs with `/mcp logs <name>`, fix config with `/mcp edit <name>` |
| Server shows ⏸ Quarantined | Too many recent errors | Fix the underlying issue, then restart with `/mcp restart <name>` |
| "Server not found" | Name doesn't match | Run `/mcp list` to see exact server names |
| Server won't start | Missing dependencies or credentials | Check that required tools (e.g., `npx`, `node`) are installed and API keys are set |
| Multiple search results | Ambiguous name during install | Use the exact server ID shown in search results |

> [!WARNING]
> Environment variables referenced in server configs (like `$MY_API_KEY`) must be set in your shell before starting Code Puppy. They are not stored in the configuration file.

## Related Guides
- [How to Use Agent Skills](AgentSkills) — Another way to extend Code Puppy
- [How to Create Custom Commands](CustomCommands) — Add your own slash commands
- [Configuration Reference](../Reference/ConfigReference) — All configuration options
