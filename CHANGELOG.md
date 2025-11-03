# Changelog

All notable changes to Code Puppy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),

## [0.0.234 -> 0.0.249] - 2025-01-28

### 🎉 Major Features

- **Advanced Agent Cancellation System**
  - Escape key support for cancelling running shell commands (cross-platform)
  - Separate escape key behavior: input cancellation vs shell interruption
  - Extended agent cancellation to handle active sub-agent tasks
  - Track active sub-agent tasks to enable proper cleanup during nested agent calls
  - Prevent agent cancellation while shell processes are actively running
  - Warning messages to notify users about cancelled operations

- **Configurable Default Agent and Model Selection**
  - Set default agent at startup via configuration
  - Set default model at startup via configuration
  - Reduces repetitive configuration on each startup

- **Comprehensive TUI Enhancements** ([@janfeddersen-wq](https://github.com/janfeddersen-wq) in #82, #83)
  - Implemented Nord theme as default with configurable theme options
  - Added right sidebar with live updating Rich Text display
  - Enhanced settings modal with API key management for multiple providers
  - Added quit confirmation dialog with improved focus handling
  - Implemented message suppression settings and improved copy mode functionality
  - Added periodic context updates during agent execution
  - Support for .env file configuration with priority over puppy.cfg
  - API key validation integrated into settings screen
  - Replaced hardcoded colors with Textual CSS variables for better theming


### 🐛 Bug Fixes

- **Agent Invocation**
  - Converted agent invocation to async with improved error handling
  - Fixed race conditions in sub-agent task management

- **Planning Agent**
  - Made execute plan trigger less strict for more flexible planning workflows (#75)

### 🔧 Technical Improvements

- **DBOS Integration** ([@Qian Li](https://github.com/Qian Li) in #84)
  - Upgrades to durable execution using DBOS

- **Memory Management**
  - Adjusted compaction threshold minimum from 0.8 to 0.5 for more flexible memory management

- **QA Agent**
  - Updated prompt for QA agent for improved testing capabilities (#79)

### 🎨 UI/UX Enhancements

- **Interactive Mode Improvements**
  - Improved command line status display showing default agent information
  - Enhanced spacing in interactive mode prompts
  - Better visual feedback for running operations

- **TUI Theming**
  - Nord theme with calming blue/gray palette
  - Consistent styling across chat view, input area, sidebar, and status bar
---

## [0.0.210 -> 0.0.233] - 2025-10-27

### 🎉 Major Features

- **Auto Updating** 
  - Significantly faster Updates
  - Code Puppy will no longer load slowly the first time you run it after updating
  - Update failures no longer cause Code Puppy to require a re-install
  - Windows updates should be significantly more stable

- **Planning Agent** (#66) ([@cgycorey](https://github.com/cgycorey))
  - New dedicated planning agent for project organization
  - Enhanced prompt design for better planning outcomes
  - Improved Code Puppy agent coordination

- **Customizable Commands**
  - You can now implement your own `/commands`!
  - Create a markdown file with the prompt to run, place it in one of three places within your project
    - `.claude/commands/` <--- Meant for compatibility with Claude Code
    - `.github/prompts/` <--- Meant for compatibility with Github Copilot
    - `.agents/commands/` <--- For Code Puppy and other agents (RECOMMENDED)
    - You can use all 3 of these and if you have duplicates, they'll appear in the /help list with numbered suffixes

- **Edit File Permissions System** ([@cgycorey](https://github.com/cgycorey) in #45)
  - Fine-grained control over file editing permissions
  - Allows users to approve/deny file modifications
  - Enhanced security for automated file operations
  - Enable with `/set yolo_mode = false`

- **Configurable Diff Highlighting**
  - Intelligent color pair system for diff display
  - Customizable diff command configuration hints
  - Beautiful, readable code change visualization
  - Configurable context diff lines
  - Try out `/diff` to play with these options
    - `/diff style <text|highlighted>`
    - `/diff additions <color>` 
    - `/diff deletions <color>` <--- `type this with no color to show options`
    - `/diff show` 

- **Interactive Model Picker TUI** ([@jackdevs000](https://github.com/jackdevs000) in #52)
  - Full-featured interactive model selection interface
  - Border fix for improved UI consistency
  - Real-time model switching from the command line
  - Only relevant to `code-puppy -t` users 

- **Manual Autosave Session Loading**
  - Load any previously saved session on demand
  - No longer automatically prompts on load, you need to run `/autosave_load`
  - Auto-save session configuration option with display
  - By popular demand...

- **Enhanced Dependency Management**
  - Pinned ripgrep to exact version 14.1.0 for stability
  - Added pexpect for advanced CLI testing
  - UV Python version management with UV_MANAGED_PYTHON=1
  - Configured UV to use only managed Python installations

- **Open Source Committers**
  - [@jackdevs000](https://github.com/jackdevs000) - Interactive TUI Model Picker!
  - [@cdakotabrown](https://github.com/cdakotabrown) - Unit test coverage!
  - [@cgycorey](https://github.com/cgycorey) - New permissions in non-YOLO mode, planning agent
  - [@diegonix](https://github.com/diegonix) - Numerous bug fixes and tweaks
  - [@IgriegaL](https://github.com/IgriegaL) - Camoufox manager bug fix

### 🧪 Testing & Quality Assurance

- **Comprehensive Integration Test Suite**
  - Rebuilt robust pexpect CLI test harness
  - Round-robin model distribution testing
  - File operation tools integration tests
  - Autosave and session rotation test coverage
  - CLI happy-path testing with shared fixtures
  - MCP Context7 end-to-end integration tests
  - DBOS initialization and database verification tests
  - Real LLM call testing infrastructure
  - Smoke tests for core functionality

- **Unit Test Expansion** ([@Dakota Brown](https://github.com/DakotaBrown) in #55)
  - Extensive new unit test coverage across modules
  - Improved test fixture extraction and reusability
  - Better test isolation and consistency
  - Agent tools testing with yolo mode mocking
  - Updated tests for tuple returns from run_prompt_with_attachments

- **CI/CD Pipeline Improvements**
  - Cross-platform matrix builds (Windows/macOS/Linux)
  - Consolidated test steps with environment variables
  - Gated PyPI publishing with comprehensive test suite
  - Streamlined builds: Ubuntu/macOS with Python 3.13 only
  - Inline pexpect installation for integration test compatibility
  - Re-enabled integration tests with enhanced PR workflow
  - Removed pre-push pytest hook from lefthook

- **Test Infrastructure Improvements**
  - Fixed autosave integration tests with explicit triggers
  - Ubuntu CI filesystem timing issue resolution
  - Removed CI skip flags and fixed timeout issues
  - Selective file cleanup in test harness
  - Hardened sync mechanisms for async operations
  - SQLite report dumping for debugging
  - Handled race conditions between auto-summarization and pending tool calls (#60)
  - Skipped flaky tests in CI environment (later resolved)
  - Added pre-commit isort+ruff hooks


### 🐛 Bug Fixes

- **Browser Support**
  - Fixed Camoufox loading issues (multiple iterations)
  - Deferred Camoufox imports and added Playwright fallback
  - Resolved browser initialization problems
  - Improved profile persistence
  - Avoided browserforge downloads at import-time
  - Ensured Camoufox availability checks

- **Autosave & Session Management**
  - Restored autosave functionality by moving calls outside broad exception handlers
  - Fixed race condition between automatic summarization and pending tool calls (#60)
  - Proper session rotation and picker bypass

- **CI & Testing**
  - Resolved MCP tool name conflicts during agent reload
  - Fixed Ubuntu CI filesystem timing races
  - Eliminated flaky integration test timeouts
  - Context7 tool execution visibility improvements
  - Resolved integration test timeout issues in CI
  - Windows pexpect compatibility (multiple attempts, later reverted)

- **Python Version Management**
  - Fixed UV Python version management to always use latest compatible Python
  - Simplified UV installation with UV_MANAGED_PYTHON=1 export
  - Updated requires-python to exclude versions > 3.13
  - Configured UV to use only managed Python installations

- **Agent Task Cancellation**
  - Implemented clean task cancellation for agent operations
  - Prevented zombie tasks and resource leaks

### ♻️ Refactoring & Code Quality

- **Code Formatting & Cleanup**
  - Applied automated linting and code formatting across codebase
  - Consistent whitespace formatting and removed unused imports
  - Improved code formatting and consistency across multiple modules
  - Ran comprehensive linters and checks

- **File Operations Refactoring**
  - Simplified file listing by delegating non-recursive mode to fallback
  - Separated directory and file ignore patterns for tool-specific filtering
  - Better organization of file operation utilities

- **Error Handling Improvements**
  - Replaced fatal errors with warnings in model processing
  - Graceful handling for missing ZAI_API_KEY
  - Better error messages for attachment processing
  - Restart notifications for DBOS configuration changes

- **DBOS Configuration**
  - Made DBOS enablement runtime-configurable via CLI
  - Dynamic configuration without restart requirements
  - Better integration with CLI workflow

- **OAuth Flow Simplification**
  - Consolidated HTML templates for OAuth success/failure pages
  - Simplified ChatGPT OAuth flow implementation
  - Cleaner callback handling and state management

### 📚 Documentation

- **Updated Documentation**
  - Added `bd` (issue tracker) usage to AGENTS.md
  - Documented lefthook linters and hooks setup (LEFTHOOK.md)
  - Closed documentation gaps (bd-21)
  - Enhanced contributing guidelines and onboarding docs

### 🔧 Technical Improvements

- **Agent System Enhancements**
  - **Agent Permissions Standardization** ([@Diego](https://github.com/Diego) in #59)
    - Removed edit_file from code-reviewer for safety
    - Added invoke_agent and list_agent collaboration to all reviewers
    - Consistent permission model across agent types
  - Enhanced Claude Code agent handling with dedicated prompt
  - Improved planning agent prompt and Code Puppy integration (#67)

- **Integration Test Harness Evolution**
  - Pexpect flows made \r-explicit
  - Autosave-friendly CLI interactions
  - Robust synchronization mechanisms
  - Bypassed session pickers for automation
  - CLI harness foundations with stability improvements

- **Build & Dependency Management**
  - Pinned ripgrep dependency to exact version 14.1.0
  - Updated requires-python constraints
  - Configured UV for managed Python installations
  - Improved dependency resolution and version compatibility

- **Context Diff Configuration**
  - Added configurable context diff line settings (#65)
  - User-adjustable diff context for better code review

### 🎨 UI/UX Enhancements

- **Diff Display**
  - Configuration hints for diff commands
  - Intelligent color pair selection
  - Enhanced readability of code changes
  - Configurable context lines for diffs

- **Model Selection**
  - Interactive TUI with improved borders
  - Real-time feedback and selection
  - Streamlined model switching workflow

### 🔄 Reverted Changes

- **Windows Integration Test Support** (multiple attempts)
  - Attempted to enable integration tests on Windows
  - Added pywinpty dependency for Windows pexpect support
  - Guarded Windows pexpect backend availability
  - Made test harness Windows-compatible
  - **Reverted**: Due to compatibility issues, rolled back to Unix-only integration tests

- **Pre-push Testing Hook**
  - Temporarily removed pre-push pytest hook from lefthook for performance reasons
  - Pre-commit hooks (isort, ruff) remain active

### 🔧 Maintenance & Chores

- Automated version bumps (multiple releases)
- Merged upstream changes from main branch
- Applied automated linting and formatting
- Cleaned up CI workflows and removed redundant steps
- Added secret debugging for integration tests (development)
- Environment variable management improvements

---

## [0.0.206] - 2025-10-14

### Added
- **HTTP/2 support** configuration option for httpx clients ([@sumukh14](https://github.com/sumukh14) in #48)
  - New `http2` config key to enable/disable HTTP/2 protocol
  - Dependencies: `httpx[http2]`, `h2`, `hpack`, `hyperframe` packages
  - Updated client creation functions to utilize HTTP/2 when enabled
- Pytest fixture in `conftest.py` to automatically clear model cache between tests
- Support for Claude 4.1 Opus model in models.json

### Changed
- Improved attachment path handling with better token detection
- Enhanced browser persistence for Camoufox profiles
- Updated iOS reviewer agent tests to be more flexible with prompt content validation
- Made config tests more resilient by checking for any valid model instead of hardcoding expectations

### Fixed
- **Test Suite**: Fixed 14 failing tests across multiple test files
  - Safety validator tests now correctly mock `create_client` instead of `create_requests_session`
  - iOS reviewer agent test assertions made more flexible
  - Prompt toolkit completion tests updated for `InMemoryHistory` (replaced `FileHistory`)
  - Alt+M keybinding test now checks for multiline toggle instead of newline insertion
  - Link attachment placeholder test updated to reflect disabled link parsing
  - Auto save session test cleaned up by removing non-existent `mock_cleanup` fixture
  - Config test cache pollution resolved with autouse fixture
- Windows-specific bug in agent manager
- Import path issues in browser initialization
- Browser profile storage and persistence issues for Camoufox

### Technical Improvements
- Better test isolation with automatic cache clearing between tests
- More robust mock patching in test suite
- Improved httpx client configuration with HTTP/2 support

## [0.0.205] - 2025-10-13

### Added
- Persistent browser profile storage for Camoufox

### Changed
- Disabled URL parsing in prompt attachments
- Implemented pagination for autosave session selection interface
- Simplified attachment handling to support images only

### Fixed
- Browser initialization and import path issues
- Windows compatibility bugs
- Agent history mutation issues
- Backslash preservation in Windows file paths during tokenization

## [0.0.204] - 2025-10-13

### Added
- Support for drag-and-drop file paths with escaped spaces
- Message of the Day (MOTD) updates

### Changed
- Reverted Pydantic AI version bump temporarily

## [0.0.203] - 2025-10-12

### Added
- **File attachments and URLs in prompts** - Full support for attaching files and URLs to messages
- Basic image input functionality
- String representation for BinaryContent in message formatting

### Changed
- Honor per-agent pinned models in context length calculation and model switching

## [0.0.202] - 2025-10-11

### Added
- **Auto-save context functionality** ([@cgycorey](https://github.com/cgycorey) in #46)
  - Automatic session saving and rotation on agent switch
  - Autosave session management with TUI picker
  - Stable session IDs replacing rolling deletion
- Session persistence extracted into dedicated storage module
- Multiline input improvements in TUI

### Changed
- Updated Pydantic AI to version 1.0.6
- Refactored pydantic-ai imports for renamed model classes
- Cleaned up agent prompts to remove redundant creative/cooked phrases

## [0.0.201] - 2025-10-10

### Added
- **CLI agent selection** - `--agent` option for startup agent selection ([@wkramme](https://github.com/wkramme) in #33)
- Configurable OpenAI reasoning effort for GPT-5 models

### Changed
- Switched from FileHistory to InMemoryHistory for prompt toolkit completion
- Simplified enter key handling in prompt completion

### Fixed
- OpenAI reasoning configuration quick fixes

## [0.0.200] - 2025-10-09

### Added
- **iOS/Swift Code Reviewer Agent** ([@m0m0wzt](https://gecgithub01.walmart.com//m0m0wzt) in #110)
  - Comprehensive iOS/Swift code review capabilities
  - SwiftUI/UIKit expertise
- **Plugin system for custom slash commands**
  - Spinner context display
  - Custom command plugin example

### Changed
- Removed tree-sitter language pack dependencies

## [0.0.199] - 2025-10-04

### Added
- **Friendly fallback for missing model configs** ([@Diego](https://github.com/Diego) in #44)

### Changed
- ZAI (internal model) support added

## [0.0.198] - 2025-10-02

### Added
- **Safety validation for shell commands** with configurable risk levels
  - Prevents dangerous command execution
  - User-configurable risk thresholds

## [0.0.197] - 2025-10-01

### Added
- **Command history cycling with up/down arrows** ([@j0l04as / Jack Langley](https://gecgithub01.walmart.com/j0l04as) in #109)
- Message limit configuration for MCP agent execution

### Changed
- Code cleanup and formatting improvements ([@j0l04as / Jack Langley](https://gecgithub01.walmart.com/j0l04as) in #108)

## [0.0.196] - 2025-09-30

### Fixed
- Certificate validation issues
- MCP declarations
- Windows auto-update functionality

### Changed
- Disabled telemetry verification
- Added multiple fallback options for installers

---

## Version Numbering

Code Puppy uses ZEROVER B/C IM EDGY
