# Code Puppy Onboarding Docs

## Overview

**Code Puppy** is an AI-powered code generation agent built specifically for **Walmart Global Tech**. It's a Walmart internal fork of an open-source project, enhanced with enterprise-grade features for Walmart's technology ecosystem.

## What Code Puppy Does (Simple Explanation)

Code Puppy is an AI coding assistant that helps Walmart developers write, edit, and manage code through conversations. Think of it like having an AI pair programmer that you can chat with in your terminal or web browser.

### How it Works
1. **You ask it to do coding tasks** in plain English (e.g., "Write a Python function to calculate tax")
2. **It uses AI models** (GPT, Claude, Gemini) to understand your request and generate code
3. **It can actually modify your files** - doesn't just show code, but writes, edits, and organizes actual project files

### Three Usage Modes
1. **CLI Interactive** (`--interactive`) - Like chatting with AI in terminal
2. **TUI** (`--tui`) - Fancy terminal interface with chat history, sidebar, and better visuals
3. **Web Interface** (`--web`) - Opens the terminal UI in web browser

## Architecture & Key Components

### 1. **Core Architecture Patterns**
- **Modular Design**: Well-organized into distinct modules (agent, TUI, messaging, tools, config)
- **Multi-Interface Support**: Three interaction modes with shared backend
- **Plugin Architecture**: Extensible tool system and MCP (Model Context Protocol) server support
- **Enterprise Security**: JWT-based authentication with Walmart's internal infrastructure
- **Message Queue Architecture**: Asynchronous messaging system for UI updates

### 2. **Agent System** (`code_puppy/agent.py`)
- **Pydantic AI-based**: Uses pydantic-ai framework for LLM interactions
- **Dynamic Model Loading**: Supports multiple AI models with runtime switching
- **Session Memory**: Persistent context management across conversations
- **Tool Integration**: Extensible tool registration system
- **MCP Server Support**: Can connect to external Model Context Protocol servers

### 3. **User Interfaces**

#### TUI (Terminal User Interface) - `/code_puppy/tui/`
- **Textual-based**: Modern terminal UI using Python Textual framework
- **Components**: Chat view, input area, sidebar, status bar, settings screens
- **Rich Rendering**: Code syntax highlighting, markdown support
- **History Management**: Command history with navigation and search
- **Web Mode**: Can be served in browser via textual serve

#### Interactive CLI Mode
- **Prompt Toolkit**: Enhanced input with tab completion and history
- **File Path Completion**: Smart autocomplete for file operations
- **Command System**: Slash commands for model switching, help, etc.

### 4. **Messaging System** (`/code_puppy/messaging/`)
- **Queue-based Architecture**: Asynchronous message queue for UI updates
- **Multiple Renderers**: Different renderers for TUI vs CLI modes
- **Message Types**: System, info, warning, error, agent response, tool output
- **Buffering**: Startup message buffering for smooth UI initialization

### 5. **Tools System** (`/code_puppy/tools/`)
- **File Operations**: Read, write, create, delete files and directories
- **File Modifications**: Advanced editing, search/replace, code refactoring
- **Command Runner**: Execute shell commands with safety checks
- **Web Search**: Integration with web search capabilities
- **TypeScript Code Mapping**: Advanced code analysis using tree-sitter

### 6. **Configuration Management** (`/code_puppy/config.py`)
- **User Config**: `~/.code_puppy/puppy.cfg` for personal settings
- **Model Configuration**: Dynamic model fetching from Walmart endpoints
- **MCP Server Config**: `mcp_servers.json` for external tool configuration
- **Environment Variables**: Support for various API keys and settings

## Technologies Used

### Core Framework
- **Python 3.10+**: Modern Python with type hints
- **Pydantic AI**: Primary AI agent framework
- **Textual**: Modern terminal UI framework
- **FastAPI**: HTTP server for token handling
- **Rich**: Advanced terminal formatting and rendering

### AI/ML Integration
- **Multiple Providers**: OpenAI, Anthropic (Claude), Google (Gemini)
- **Custom Endpoints**: Support for Walmart's internal AI gateways
- **MCP Protocol**: Model Context Protocol for external tool integration
- **Usage Limits**: Rate limiting and quota management

### Development Tools
- **Pytest**: Comprehensive testing framework with 95% coverage
- **Ruff**: Modern Python linting and formatting
- **UV**: Fast Python package manager
- **Pre-commit**: Code quality hooks

## Enterprise & Security Features

### Walmart-Specific Enhancements
1. **Internal PyPI Registry**: Uses Walmart's internal package repository
2. **Enterprise Authentication**: JWT-based auth with Walmart identity system
3. **Certificate Management**: Walmart CA bundle for internal TLS connections
4. **Internal Endpoints**: Custom AI model endpoints routing through Walmart infrastructure
5. **Compliance Framework**: Built-in adherence to Walmart coding standards
6. **Data Usage Disclaimer**: Prominent warnings about data sensitivity and monitoring

### Security Measures
- **Token-based Auth**: Secure JWT token management
- **Environment-based Config**: Secure credential management
- **CORS Configuration**: Proper cross-origin handling
- **Certificate Validation**: Enterprise certificate bundle validation

## Comparison to Claude Code

### Similarities
- AI-powered coding assistant that can read, write, and modify files
- Conversational interface - describe what you want in natural language
- Multi-language support for various programming languages
- File operations - can create, edit, and manage your codebase
- Context awareness - understands project structure and code

### Key Differences
1. **Enterprise vs. General Use**: Code Puppy built for Walmart internal teams vs. Claude Code for any developer
2. **AI Model Flexibility**: Code Puppy supports multiple providers vs. Claude Code using Anthropic models specifically
3. **Interface Options**: Code Puppy has 3 interfaces (CLI, TUI, web) vs. Claude Code primarily CLI
4. **Deployment**: Code Puppy is self-hosted Python app vs. Claude Code as official Anthropic CLI
5. **Customization**: Code Puppy highly customizable with "puppy rules", MCP servers, custom endpoints
6. **Enterprise Features**: Built-in authentication, compliance warnings, internal tool integration

## Interface Differences: CLI vs TUI

### CLI Mode (`--interactive`)
- **Linear conversation** - like chatting in messaging app
- **Simple text input/output**
- **Prompt-based** - type, it responds, repeat
- **Scrolling history** - older messages scroll up and disappear
- **Basic formatting** with Rich library

### TUI Mode (`--tui`)
- **Visual interface** with panels, menus, navigation
- **Persistent chat history** in dedicated panel
- **Sidebar navigation** - browse previous conversations
- **Rich formatting** - syntax highlighting, better code display
- **Mouse support** (in some terminals)
- **Status bar** showing current model, connection status
- **Multiple screens** - settings, help, tools view

## Development Setup & Workflow

### Environment Setup
```bash
# Clone and setup
git clone git@gecgithub01.walmart.com:genaica/code-puppy.git
cd code-puppy

# Setup virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv sync

# Set up environment variables
export UV_INDEX_URL=https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple
export NO_VERSION_UPDATE=1
```

### Key Development Tools
- **`./code-puppy-dev`** - Quick testing with live reload
- **`./scripts/run_pre_commit.sh`** - Code quality checks
- **`./scripts/pretty_print_path.sh`** - Debug environment issues
- **`pytest`** - Run tests (maintains 95%+ coverage)
- **`ruff`** - Code formatting and linting

### Feature Development Types

#### A) New Console Command (like `/mycommand`)
- **Location**: `code_puppy/command_line/command_handler.py`
- **Examples**: `/cd`, `/show`, `/codemap`, `/set`

#### B) New AI Tool (for the agent to use)
- **Location**: `code_puppy/tools/` directory
- **Examples**: file operations, web search, command runner

#### C) New TUI Component (for terminal interface)
- **Location**: `code_puppy/tui/components/`
- **Examples**: chat view, sidebar, status bar

#### D) New Configuration Option
- **Location**: `code_puppy/config.py`
- **Examples**: model settings, user preferences

## Testing Structure

### Comprehensive Test Suite
- **95% Code Coverage**: Extensive unit and integration tests
- **Multiple Test Types**: Unit tests, integration tests, TUI component tests
- **Async Testing**: Proper async/await test patterns
- **Mocking**: Extensive use of mocks for external dependencies

### Test Organization
- `/tests/` - Main test suite for core functionality
- `/code_puppy/tui/tests/` - TUI-specific component tests
- Test files follow `test_*.py` naming convention

## Configuration Mechanisms

### User Configuration (`~/.code_puppy/`)
- `puppy.cfg` - Personal settings (name, model preferences)
- `models.json` - Cached model configurations
- `mcp_servers.json` - External tool server configurations
- `command_history.txt` - Persistent command history

### Model Configuration
- **Dynamic Fetching**: Models config fetched from Walmart endpoints
- **Fallback Strategy**: Local cache when remote unavailable
- **Environment Variables**: Secure API key management
- **Custom Endpoints**: Support for internal Walmart AI gateways

## Extension Points

1. **Tool System**: Easy to add new AI tools via the tools registry
2. **MCP Servers**: External tool integration via standardized protocol
3. **Model Providers**: Support for new AI providers and custom endpoints
4. **UI Components**: Modular TUI components for feature extensions
5. **Authentication**: Pluggable auth system for different environments

## Key Developer Insights

### Architecture Strengths
1. **Modular Design**: Easy to extend with new tools and features
2. **Multi-Modal Interface**: Supports different user preferences (CLI, TUI, web)
3. **Enterprise Ready**: Built-in security and compliance features
4. **Dynamic Configuration**: Runtime model switching and configuration updates
5. **Robust Error Handling**: Graceful degradation and fallback mechanisms

This codebase represents a sophisticated, enterprise-grade AI coding assistant with strong architectural patterns, comprehensive testing, and robust security features specifically tailored for Walmart's technology ecosystem.
