# Code Puppy 🐶

Code Puppy is a CLI-based AI code agent system with multiple specialized agents for different coding tasks!

## Code Style

- Clean & concise - keep files under 600 lines (Zen puppy approves!)
- Follow YAGNI, SRP, DRY, SOLID principles
- Type hints on everything (Python)
- Zen of Python applies even to non-Python code

## Testing

```bash
uv run pytest              # Run all tests
uv run pytest -x           # Stop on first failure
uv run pytest -k "test_name"  # Run specific test
```

## Git Workflow

- Run `ruff check --fix` to fix linting errors
- Run `ruff format .` to auto-format
- **NEVER** use `git push --force` on the main branch

---

## 🤖 Agent System

Code Puppy features a modular agent architecture. Each agent has its own system prompt, tool set, and specialization.

### Available Agents

| Agent | Name | Description |
|-------|------|-------------|
| 🐶 **Code-Puppy** | `code-puppy` | The default loyal digital puppy - full-stack code generation agent |
| 📋 **Planning Agent** | `planning-agent` | Breaks down complex tasks into actionable roadmaps |
| 🛡️ **Code Reviewer** | `code-reviewer` | Holistic reviewer for bugs, vulnerabilities, perf traps, design debt |
| 🛡️ **Security Auditor** | `security-auditor` | Risk-based security auditing with compliance focus |
| 🐍 **Python Reviewer** | `python-reviewer` | Python-specific code review with idiomatic guidance |
| 🐍 **Python Programmer** | `python-programmer` | Modern Python specialist (async, data science, web frameworks) |
| 🐾 **QA Expert** | `qa-expert` | Quality assurance strategist - test coverage, automation, risk |
| 🐱 **QA Kitten** | `qa-kitten` | Browser automation & QA testing using Playwright |
| 🏗️ **Agent Creator** | `agent-creator` | Interactive wizard for creating custom JSON agents |
| 📝 **Prompt Reviewer** | `prompt-reviewer` | Analyzes and improves prompt quality |
| **C Reviewer** | `c-reviewer` | C code review specialist |
| **C++ Reviewer** | `cpp-reviewer` | C++ code review specialist |
| **Go Reviewer** | `golang-reviewer` | Go code review specialist |
| **JS Reviewer** | `javascript-reviewer` | JavaScript code review specialist |
| **TS Reviewer** | `typescript-reviewer` | TypeScript code review specialist |

### Switching Agents

```bash
/agent code-puppy          # Switch to default agent
/agent planning-agent      # Switch to planning mode
/agent qa-kitten           # Switch to browser automation
```

---

## 📁 Package Structure

### `code_puppy/`

| File | Purpose |
|------|----------|
| `__init__.py` | Package version detection |
| `__main__.py` | Entry point for `python -m code_puppy` |
| `main.py` | CLI loop and main application logic |
| `config.py` | Global configuration manager |
| `model_factory.py` | Constructs LLM models from configuration |
| `models.json` | Available models and metadata registry |
| `callbacks.py` | Plugin callback system |
| `session_storage.py` | Session persistence |
| `summarization_agent.py` | Specialized agent for history summarization |
| `version_checker.py` | PyPI version checking |
| `http_utils.py` | HTTP utilities |
| `status_display.py` | Status bar and display utilities |
| `tui_state.py` | TUI state management |
| `round_robin_model.py` | Round-robin model rotation |
| `reopenable_async_client.py` | Resilient async HTTP client |
| `claude_cache_client.py` | Claude API caching client |

### `code_puppy/agents/`

| File | Purpose |
|------|----------|
| `__init__.py` | Agent system exports |
| `base_agent.py` | Abstract base class for all agents |
| `agent_manager.py` | Agent discovery, loading, switching |
| `json_agent.py` | JSON-based agent configuration system |
| `agent_code_puppy.py` | Default code generation agent |
| `agent_planning.py` | Planning & roadmapping agent |
| `agent_code_reviewer.py` | General code review agent |
| `agent_security_auditor.py` | Security audit agent |
| `agent_python_reviewer.py` | Python review agent |
| `agent_python_programmer.py` | Python programming agent |
| `agent_qa_expert.py` | QA strategy agent |
| `agent_qa_kitten.py` | Browser automation agent |
| `agent_creator_agent.py` | JSON agent creator wizard |
| `prompt_reviewer.py` | Prompt quality analyzer |
| `agent_c_reviewer.py` | C review agent |
| `agent_cpp_reviewer.py` | C++ review agent |
| `agent_golang_reviewer.py` | Go review agent |
| `agent_javascript_reviewer.py` | JavaScript review agent |
| `agent_typescript_reviewer.py` | TypeScript review agent |

### `code_puppy/tools/`

| File | Purpose |
|------|----------|
| `__init__.py` | Tool registration and exports |
| `common.py` | Shared console and ignore helpers |
| `command_runner.py` | Shell command execution with confirmations |
| `file_modifications.py` | File editing with diffs |
| `file_operations.py` | List, read, grep filesystem operations |
| `agent_tools.py` | Agent invocation and reasoning tools |
| `tools_content.py` | Content manipulation utilities |

### `code_puppy/tools/browser/`

| File | Purpose |
|------|----------|
| `browser_control.py` | Browser initialization and lifecycle |
| `browser_navigation.py` | Navigation (go, back, forward, reload) |
| `browser_interactions.py` | Click, type, select, check interactions |
| `browser_locators.py` | Semantic element location (role, text, label) |
| `browser_screenshot.py` | Screenshot capture and VQA |
| `browser_scripts.py` | JavaScript execution |
| `browser_workflows.py` | Workflow save/load |
| `camoufox_manager.py` | Camoufox browser management |
| `vqa_agent.py` | Visual question answering |

### `code_puppy/command_line/`

| File | Purpose |
|------|----------|
| `__init__.py` | Command line subpackage |
| `command_handler.py` | Command dispatch and routing |
| `command_registry.py` | Command registration system |
| `core_commands.py` | Core CLI commands |
| `config_commands.py` | Configuration commands |
| `session_commands.py` | Session management commands |
| `file_path_completion.py` | Path completion with @ trigger |
| `model_picker_completion.py` | Model selection completion |
| `prompt_toolkit_completion.py` | Interactive prompt with combined completers |
| `mcp_completion.py` | MCP command completion |
| `pin_command_completion.py` | Model pinning completion |
| `load_context_completion.py` | Context loading completion |
| `attachments.py` | File attachment handling |
| `autosave_menu.py` | Autosave configuration UI |
| `diff_menu.py` | Diff review interface |
| `add_model_menu.py` | Model addition wizard |
| `motd.py` | Message of the day |
| `utils.py` | Command line utilities |

### `code_puppy/command_line/mcp/`

| File | Purpose |
|------|----------|
| `handler.py` | MCP command dispatcher |
| `add_command.py` | Add MCP servers |
| `install_command.py` | Install MCP servers |
| `list_command.py` | List MCP servers |
| `search_command.py` | Search MCP registry |
| `start_command.py` | Start MCP servers |
| `stop_command.py` | Stop MCP servers |
| `start_all_command.py` | Start all servers |
| `stop_all_command.py` | Stop all servers |
| `restart_command.py` | Restart servers |
| `status_command.py` | Server status |
| `remove_command.py` | Remove servers |
| `test_command.py` | Test server connectivity |
| `logs_command.py` | View server logs |
| `help_command.py` | MCP help |
| `utils.py` | MCP utilities |
| `wizard_utils.py` | Interactive wizards |

### `code_puppy/mcp_/`

| File | Purpose |
|------|----------|
| `__init__.py` | MCP system exports |
| `manager.py` | MCP server lifecycle management |
| `registry.py` | Server registration |
| `server_registry_catalog.py` | MCP server catalog |
| `managed_server.py` | Individual server management |
| `health_monitor.py` | Server health monitoring |
| `status_tracker.py` | Status tracking |
| `async_lifecycle.py` | Async server lifecycle |
| `blocking_startup.py` | Blocking startup utilities |
| `circuit_breaker.py` | Circuit breaker pattern |
| `retry_manager.py` | Retry logic |
| `error_isolation.py` | Error isolation |
| `captured_stdio_server.py` | Stdio capture for servers |
| `config_wizard.py` | MCP configuration wizard |
| `dashboard.py` | MCP dashboard |
| `system_tools.py` | System-level MCP tools |

### `code_puppy/messaging/`

| File | Purpose |
|------|----------|
| `__init__.py` | Messaging system exports (emit_info, emit_warning, emit_error) |
| `message_queue.py` | Async message queue |
| `queue_console.py` | Console output queue |
| `renderers.py` | Message rendering (markdown, code, etc.) |

### `code_puppy/messaging/spinner/`

| File | Purpose |
|------|----------|
| `__init__.py` | Spinner exports |
| `spinner_base.py` | Abstract spinner base |
| `console_spinner.py` | Console spinner implementation |

### `code_puppy/plugins/`

| Plugin | Purpose |
|--------|----------|
| `chatgpt_oauth/` | ChatGPT OAuth authentication plugin |
| `claude_code_oauth/` | Claude OAuth authentication plugin |
| `customizable_commands/` | User-defined custom commands |
| `example_custom_command/` | Example plugin template |
| `file_permission_handler/` | File permission management |
| `shell_safety/` | Shell command safety checks |
| `oauth_puppy_html.py` | OAuth HTML templates |

---

## 🔧 Creating Custom Agents

You can create custom agents using JSON files! Place them in `~/.code_puppy/agents/`.

### JSON Agent Schema

```json
{
  "id": "unique-uuid-here",
  "name": "my-agent",
  "display_name": "My Agent 🤖",
  "description": "What this agent does",
  "system_prompt": "Your instructions here...",
  "tools": [
    "list_files",
    "read_file",
    "grep",
    "edit_file",
    "agent_share_your_reasoning"
  ],
  "user_prompt": "Optional custom greeting",
  "model": "optional-pinned-model-name"
}
```

### Available Tools

**File Operations:**
- `list_files` - List directory contents
- `read_file` - Read file contents
- `grep` - Search across files
- `edit_file` - Create/modify files
- `delete_file` - Delete files

**System Operations:**
- `agent_run_shell_command` - Execute shell commands

**Agent Operations:**
- `agent_share_your_reasoning` - Share thought process
- `list_agents` - List available agents
- `invoke_agent` - Invoke sub-agents

**Browser Tools (QA Kitten):**
- `browser_initialize`, `browser_close`, `browser_status`
- `browser_navigate`, `browser_go_back`, `browser_go_forward`
- `browser_click`, `browser_set_text`, `browser_get_text`
- `browser_find_by_role`, `browser_find_by_text`, `browser_find_by_label`
- `browser_screenshot_analyze`
- And many more...

### Creating an Agent via CLI

```bash
/agent agent-creator    # Switch to agent creator
# Then describe what you want your agent to do!
```

---

## 🔌 MCP (Model Context Protocol) Support

Code Puppy supports MCP servers for extended functionality:

```bash
/mcp list              # List configured servers
/mcp search <query>    # Search MCP registry
/mcp install <name>    # Install from registry
/mcp add               # Add custom server
/mcp start <name>      # Start a server
/mcp stop <name>       # Stop a server
/mcp status            # Check server status
```

---

## 📚 Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Main CLI Loop                        │
│                      (main.py)                          │
├─────────────────────────────────────────────────────────┤
│                   Agent Manager                          │
│    (Discovery, Loading, Switching, Session Tracking)     │
├──────────────┬──────────────┬──────────────┬────────────┤
│   BaseAgent  │  JSONAgent   │  Specialized │   Custom   │
│  (Abstract)  │ (From JSON)  │   Agents     │   Agents   │
├──────────────┴──────────────┴──────────────┴────────────┤
│                     Tool System                          │
│    (File Ops, Shell, Browser, Agent Invocation)         │
├─────────────────────────────────────────────────────────┤
│                   Model Factory                          │
│    (OpenAI, Anthropic, Google, Mistral, etc.)           │
├─────────────────────────────────────────────────────────┤
│                    MCP Manager                           │
│    (External Tool Integration via MCP Protocol)          │
└─────────────────────────────────────────────────────────┘
```

---

## 🐾 Quick Tips

- **Always use tools** - Don't just describe, actually do it!
- **Share your reasoning** - Use `agent_share_your_reasoning` liberally
- **Read before writing** - Always `read_file` before `edit_file`
- **Keep files small** - Under 600 lines, split if larger
- **Test your changes** - Run tests after modifications
