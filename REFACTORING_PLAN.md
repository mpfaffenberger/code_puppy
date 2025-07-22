# Messaging System Refactoring Plan

This document outlines the plan for continuing the refactoring of the messaging system in the code-puppy codebase. The goal is to standardize how messages are sent throughout the application for improved maintainability and consistency.

## Completed Refactoring

We have successfully completed all of the planned refactoring:

1. Eliminated `_output_message` in auth.py by replacing all calls with QueueConsole
2. Replaced direct `console.print` calls in main.py with message queue system calls
3. Refactored auth.py to use semantic `emit_*` functions instead of `console.print()`
4. Updated agent.py to use `emit_*` functions
5. Documented why SynchronousInteractiveRenderer should be kept for now
6. Created comprehensive documentation in MESSAGING_ARCHITECTURE.md
7. Refactored command_line/motd.py to use `emit_*` functions
8. Refactored command_line/meta_command_handler.py to use `emit_*` functions
9. Refactored tools/file_modifications.py to use `emit_*` functions
10. Refactored tools/file_operations.py to use `emit_*` functions
11. Refactored tools/command_runner.py to use `emit_*` functions
12. Refactored tools/web_search.py to use `emit_*` functions

## Completed Refactoring of All Files

All files have been successfully refactored to use the emit_* functions:

### Phase 1: Command Line Module ✅
1. ✅ command_line/motd.py - Message of the day functionality
2. ✅ command_line/meta_command_handler.py - Handles meta commands in interactive mode

### Phase 2: Tools Module (Core) ✅
3. ✅ tools/file_modifications.py - File modification helpers and tools
4. ✅ tools/file_operations.py - File operation helpers and tools

### Phase 3: Tools Module (Secondary) ✅
5. ✅ tools/command_runner.py - Command execution tools
6. ✅ tools/web_search.py - Web search functionality

## Special Considerations

Some files require special handling during refactoring:

1. **tools/file_modifications.py**: Contains diff printing functionality that might need special formatting
2. **command_line/meta_command_handler.py**: Receives a console instance directly as a parameter
3. **tui/app.py**: Contains UI-specific rendering that might need careful review

## Approach for Each File

For each file, we will:

1. Identify all console.print calls
2. Determine the appropriate emit_* function based on the message context
3. Replace the console.print call with the corresponding emit_* function
4. Update any imports or parameters as needed
5. Run tests to ensure functionality is maintained
6. Commit changes for each module separately

## Function Mapping Guidelines

Use these guidelines when replacing console.print calls:

| Message Content | Replace With |
|-----------------|--------------|
| Error messages | emit_error() |
| Warning messages | emit_warning() |
| Success messages | emit_success() |
| Information messages | emit_info() |
| Debug/low visibility | emit_system_message() |
| Tool output | emit_tool_output() |
| Command results | emit_command_output() |

## Testing Strategy

For each refactored file:

1. Run targeted tests related to the specific module
2. Run the full test suite to catch any integration issues
3. Test in both --tui and --interactive modes when applicable
4. Verify proper message display and formatting

## Future Work

After completing this refactoring:

1. Consider a more thorough redesign of the SynchronousInteractiveRenderer
2. Standardize the message display patterns across all UI modes
3. Add more comprehensive testing of the messaging system
4. Document any remaining edge cases or special handlers