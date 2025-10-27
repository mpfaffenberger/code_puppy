# Changelog

All notable changes to Code Puppy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),

## [Unreleased] - 2025-10-22

### 🎉 Major Features

- **Edit File Permissions System** ([@cgycorey](https://github.com/cgycorey) in #45)
  - Fine-grained control over file editing permissions
  - Allows users to approve/deny file modifications
  - Enhanced security for automated file operations

- **Configurable Diff Highlighting**
  - Intelligent color pair system for diff display
  - Customizable diff command configuration hints
  - Beautiful, readable code change visualization

- **Interactive Model Picker TUI** ([@jackdevs000](https://github.com/jackdevs000) in #52)
  - Full-featured interactive model selection interface
  - Border fix for improved UI consistency
  - Real-time model switching from the command line

- **Manual Autosave Session Loading**
  - Load any previously saved session on demand
  - No longer automatically prompts on load, you need to run /autosave_load

- **Enhanced Dependency Management**
  - Pinned ripgrep to exact version 14.1.0 for stability
  - Added pexpect for advanced CLI testing

### 🧪 Testing & Quality Assurance

- **Comprehensive Integration Test Suite**
  - Rebuilt robust pexpect CLI test harness
  - Round-robin model distribution testing
  - File operation tools integration tests
  - Autosave and session rotation test coverage
  - CLI happy-path testing with shared fixtures
  - MCP Context7 end-to-end integration tests
  - DBOS initialization and database verification tests

- **Unit Test Expansion** ([@Dakota Brown](https://github.com/DakotaBrown) in #55)
  - Extensive new unit test coverage across modules
  - Improved test fixture extraction and reusability
  - Better test isolation and consistency

- **Test Infrastructure Improvements**
  - Fixed autosave integration tests with explicit triggers
  - Ubuntu CI filesystem timing issue resolution
  - Removed CI skip flags and fixed timeout issues
  - Selective file cleanup in test harness
  - Hardened sync mechanisms for async operations
  - SQLite report dumping for debugging


### 🐛 Bug Fixes

- **Camoufox Browser Support**
  - Fixed Camoufox loading issues
  - Resolved browser initialization problems
  - Improved profile persistence

- **CI & Testing**
  - Resolved MCP tool name conflicts during agent reload
  - Fixed Ubuntu CI filesystem timing races
  - Eliminated flaky integration test timeouts
  - Context7 tool execution visibility improvements

### ♻️ Refactoring & Code Quality

- **Error Handling Improvements**
  - Replaced fatal errors with warnings in model processing
  - Graceful handling for missing ZAI_API_KEY
  - Better error messages for attachment processing
  - Restart notifications for DBOS configuration changes

- **DBOS Configuration**
  - Made DBOS enablement runtime-configurable via CLI
  - Dynamic configuration without restart requirements
  - Better integration with CLI workflow

### 📚 Documentation

- **Updated Documentation**
  - Added `bd` (issue tracker) usage to AGENTS.md
  - Documented lefthook linters and hooks setup
  - Closed documentation gaps (bd-21)

### 🔧 Technical Improvements

- **Agent Permissions Standardization** ([@Diego](https://github.com/Diego) in #59)
  - Removed edit_file from code-reviewer for safety
  - Added invoke_agent and list_agent collaboration to all reviewers
  - Consistent permission model across agent types

- **Integration Test Harness Evolution**
  - Pexpect flows made \r-explicit
  - Autosave-friendly CLI interactions
  - Robust synchronization mechanisms
  - Bypassed session pickers for automation

### 🎨 UI/UX Enhancements

- **Diff Display**
  - Configuration hints for diff commands
  - Intelligent color pair selection
  - Enhanced readability of code changes

- **Model Selection**
  - Interactive TUI with improved borders
  - Real-time feedback and selection
  - Streamlined model switching workflow

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
