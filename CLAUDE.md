# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Testing and Quality Assurance
- **Run tests**: `pytest` (with coverage: `pytest --cov=code_puppy --cov-report=term-missing`)
- **Format code**: `ruff format .`
- **Lint code**: `ruff check .`
- **Install dependencies**: `uv sync`
- **Create virtual environment**: `uv venv && source .venv/bin/activate`

### Package Management
- Uses `uv` as the package manager (not pip or poetry)
- Python 3.10+ required
- Dependencies are managed in `pyproject.toml`

## Code Architecture

### Core Components

**Agent System (`code_puppy/agent.py`)**
- Main AI agent using `pydantic-ai` framework
- Dynamic model loading with singleton pattern (`get_code_generation_agent()`)
- Supports multiple model types: OpenAI, Gemini, Azure OpenAI, custom endpoints
- Session memory management for context persistence
- MCP (Model Context Protocol) server integration for external tools

**Tool System (`code_puppy/tools/`)**
- Modular tool registration system
- Four main tool categories:
  - `file_operations.py`: File read/write/search operations
  - `file_modifications.py`: Code editing and modification tools
  - `command_runner.py`: Shell command execution
  - `web_search.py`: Web search capabilities
- Tools are registered via `register_all_tools()` function

**Configuration (`code_puppy/config.py`)**
- Config stored in `~/.code_puppy/puppy.cfg`
- Model selection persists between sessions
- YOLO mode for bypassing safety confirmations
- MCP server configuration in `~/.code_puppy/mcp_servers.json`

**Model Factory (`code_puppy/model_factory.py`)**
- Handles different LLM providers and configurations
- Model definitions in `code_puppy/models.json`
- Supports custom endpoints, Azure, and Ollama setups

### Key Features

**Interactive CLI (`code_puppy/main.py`)**
- Two modes: single command execution and interactive mode
- Enhanced input with `prompt_toolkit` for tab completion
- Message history management with configurable limits
- Background HTTP server (ports 8090-9010)

**Puppy Rules System**
- Custom coding standards via `.puppy_rules` file
- Rules automatically injected into agent instructions
- Supports project-specific conventions

**Session Memory (`code_puppy/session_memory.py`)**
- Persistent context across agent interactions
- Task logging and history management

## Development Notes

### Testing
- 95%+ test coverage maintained
- Test files in `tests/` directory
- Uses pytest with asyncio support
- Coverage excludes `main.py` only

### Code Style
- Uses Ruff for formatting and linting
- Follows PEP 8 conventions
- Type hints encouraged (uses Pydantic models)

### Enterprise Features (Walmart Internal)
- Dual licensing model (MIT + Walmart proprietary)
- Internal PyPI registry configuration
- Enhanced security protocols
- MOTD (Message of the Day) system

### MCP Integration
- Supports external tool servers via MCP protocol
- Configuration-driven server registration
- SSE (Server-Sent Events) transport

## Important Files

- `pyproject.toml`: Package configuration and dependencies
- `code_puppy/models.json`: Model definitions and endpoints
- `code_puppy/agent_prompts.py`: System prompts and instructions
- `.puppy_rules`: Project-specific coding standards (if present)

## Entry Points
- CLI: `code-puppy` command (via `main.py:main_entry`)
- Interactive: `code-puppy --interactive`
- Single command: `code-puppy "your task here"`