import os
import shlex

import code_puppy.messaging as messaging
from code_puppy.command_line.model_picker_completion import (
    load_model_names,
    update_model_in_input,
)
from code_puppy.command_line.motd import print_motd
from code_puppy.command_line.utils import make_directory_table
from code_puppy.config import get_config_keys
from code_puppy.tools.tools_content import tools_content

COMMANDS_HELP = """
[bold magenta]Commands Help[/bold magenta]
/help, /h                 Show this help message
/cd <dir>                 Change directory or show directories

/exit, /quit              Exit interactive mode
/generate-pr-description [@dir]  Generate comprehensive PR description
/m <model>                Set active model
/motd                     Show the latest message of the day (MOTD)
/show                     Show puppy config key-values
/compact                  Summarize and compact current chat history
/dump_context <name>      Save current message history to file
/load_context <name>      Load message history from file
/set                      Set puppy config key-values (e.g., /set yolo_mode true)
/tools                    Show available tools and capabilities
/undo                     Undo the last change
/redo                     Redo the last undone change
/checkout <response_id>   Checkout by response id from /versions (default)
/checkout prompt <ver>    Checkout a specific version for the current prompt
/versions [limit]         Show recent versions across prompts
/history [limit]          Show recent versions across prompts (same as /versions)
/history prompts          Show version history for the current prompt
/history "<prompt>"       Show version history for a specific prompt
/<unknown>                Show unknown command warning
"""


# Global to track current version for redo functionality
_current_version_track = {}


def handle_command(command: str):
    """
    Handle commands prefixed with '/'.

    Args:
        command: The command string to handle

    Returns:
        True if the command was handled, False if not, or a string to be processed as user input
    """
    command = command.strip()

    if command.strip().startswith("/motd"):
        print_motd(force=True)
        return True

    if command.strip().startswith("/compact"):
        from code_puppy.message_history_processor import (
            estimate_tokens_for_message,
            summarize_messages,
        )
        from code_puppy.state_management import get_message_history, set_message_history

        try:
            history = get_message_history()
            if not history:
                messaging.emit_warning("No history to compact yet. Ask me something first!")
                return True

            before_tokens = sum(estimate_tokens_for_message(m) for m in history)
            messaging.emit_info(
                f"🤔 Compacting {len(history)} messages... (~{before_tokens} tokens)"
            )

            compacted, _ = summarize_messages(history, with_protection=False)
            if not compacted:
                messaging.emit_error("Summarization failed. History unchanged.")
                return True

            set_message_history(compacted)

            after_tokens = sum(estimate_tokens_for_message(m) for m in compacted)
            reduction_pct = (
                ((before_tokens - after_tokens) / before_tokens * 100)
                if before_tokens > 0
                else 0
            )
            messaging.emit_success(
                f"✨ Done! History: {len(history)} → {len(compacted)} messages\n"
                f"🏦 Tokens: {before_tokens:,} → {after_tokens:,} ({reduction_pct:.1f}% reduction)"
            )
            return True
        except Exception as e:
            messaging.emit_error(f"/compact error: {e}")
            return True

    if command.startswith("/cd"):
        tokens = command.split()
        if len(tokens) == 1:
            try:
                table = make_directory_table()
                messaging.emit_info(table)
            except Exception as e:
                messaging.emit_error(f"Error listing directory: {e}")
            return True
        elif len(tokens) == 2:
            dirname = tokens[1]
            target = os.path.expanduser(dirname)
            if not os.path.isabs(target):
                target = os.path.join(os.getcwd(), target)
            if os.path.isdir(target):
                os.chdir(target)
                messaging.emit_success(f"Changed directory to: {target}")
            else:
                messaging.emit_error(f"Not a directory: {dirname}")
            return True

    if command.strip().startswith("/show"):
        from code_puppy.command_line.model_picker_completion import get_active_model
        from code_puppy.config import (
            get_owner_name,
            get_protected_token_count,
            get_puppy_name,
            get_summarization_threshold,
            get_yolo_mode,
        )

        puppy_name = get_puppy_name()
        owner_name = get_owner_name()
        model = get_active_model()
        yolo_mode = get_yolo_mode()
        protected_tokens = get_protected_token_count()
        summary_threshold = get_summarization_threshold()

        status_msg = f"""[bold magenta]🐶 Puppy Status[/bold magenta]

[bold]puppy_name:[/bold]            [cyan]{puppy_name}[/cyan]
[bold]owner_name:[/bold]            [cyan]{owner_name}[/cyan]
[bold]model:[/bold]                 [green]{model}[/green]
[bold]YOLO_MODE:[/bold]             {"[red]ON[/red]" if yolo_mode else "[yellow]off[/yellow]"}
[bold]protected_tokens:[/bold]      [cyan]{protected_tokens:,}[/cyan] recent tokens preserved
[bold]summary_threshold:[/bold]     [cyan]{summary_threshold:.1%}[/cyan] context usage triggers summarization

"""
        messaging.emit_info(status_msg)
        return True

    if command.startswith("/set"):
        # Syntax: /set KEY=VALUE or /set KEY VALUE
        from code_puppy.config import set_config_value

        tokens = command.split(None, 2)
        argstr = command[len("/set") :].strip()
        key = None
        value = None
        if "=" in argstr:
            key, value = argstr.split("=", 1)
            key = key.strip()
            value = value.strip()
        elif len(tokens) >= 3:
            key = tokens[1]
            value = tokens[2]
        elif len(tokens) == 2:
            key = tokens[1]
            value = ""
        else:
            messaging.emit_warning(
                f"Usage: /set KEY=VALUE or /set KEY VALUE\nConfig keys: {', '.join(get_config_keys())}"
            )
            return True
        if key:
            set_config_value(key, value)
            messaging.emit_success(f'🌶 Set {key} = "{value}" in puppy.cfg!')
        else:
            messaging.emit_error("You must supply a key.")
        return True

    if command.startswith("/tools"):
        # Display the tools_content.py file content with markdown formatting
        from rich.markdown import Markdown

        markdown_content = Markdown(tools_content)
        messaging.emit_info(markdown_content)
        return True

    if command.startswith("/m"):
        # Try setting model and show confirmation
        new_input = update_model_in_input(command)
        if new_input is not None:
            from code_puppy.agent import get_code_generation_agent
            from code_puppy.command_line.model_picker_completion import get_active_model

            model = get_active_model()
            # Make sure this is called for the test
            get_code_generation_agent(force_reload=True)
            messaging.emit_success(f"Active model set and loaded: {model}")
            return True
        # If no model matched, show available models
        model_names = load_model_names()
        messaging.emit_warning("Usage: /m <model-name>")
        messaging.emit_warning(f"Available models: {', '.join(model_names)}")
        return True
    if command in ("/help", "/h"):
        messaging.emit_info(COMMANDS_HELP)
        return True

    # Global versions listing across prompts
    if command.startswith("/versions"):
        from code_puppy.version_store import list_all_versions

        tokens = command.split()
        limit = None
        if len(tokens) >= 2:
            try:
                limit = int(tokens[1])
            except ValueError:
                messaging.emit_warning("Usage: /versions [limit]")
                return True

        rows = list(list_all_versions(limit=limit))
        if not rows:
            messaging.emit_warning("No versions found!")
            return True

        text = "[bold magenta]Recent Versions[/bold magenta]\n"
        for response_id, prompt_text, version, timestamp in rows:
            safe_prompt = (prompt_text[:80] + "…") if len(prompt_text) > 80 else prompt_text
            text += f"#{response_id} | v{version} | {timestamp} | Prompt: {safe_prompt}\n"
        messaging.emit_info(text)
        return True

    if command.startswith("/generate-pr-description"):
        # Parse directory argument (e.g., /generate-pr-description @some/dir)
        tokens = command.split()
        directory_context = ""
        for t in tokens:
            if t.startswith("@"):
                directory_context = f" Please work in the directory: {t[1:]}"
                break

        # Hard-coded prompt from user requirements
        pr_prompt = f"""Generate a comprehensive PR description for my current branch changes. Follow these steps:

 1 Discover the changes: Use git CLI to find the base branch (usually main/master/develop) and get the list of changed files, commits, and diffs.
 2 Analyze the code: Read and analyze all modified files to understand:
    • What functionality was added/changed/removed
    • The technical approach and implementation details
    • Any architectural or design pattern changes
    • Dependencies added/removed/updated
 3 Generate a structured PR description with these sections:
    • Title: Concise, descriptive title (50 chars max)
    • Summary: Brief overview of what this PR accomplishes
    • Changes Made: Detailed bullet points of specific changes
    • Technical Details: Implementation approach, design decisions, patterns used
    • Files Modified: List of key files with brief description of changes
    • Testing: What was tested and how (if applicable)
    • Breaking Changes: Any breaking changes (if applicable)
    • Additional Notes: Any other relevant information
 4 Create a markdown file: Generate a PR_DESCRIPTION.md file with proper GitHub markdown formatting that I can directly copy-paste into GitHub's PR
   description field. Use proper markdown syntax with headers, bullet points, code blocks, and formatting.
 5 Make it review-ready: Ensure the description helps reviewers understand the context, approach, and impact of the changes.
6. If you have Github MCP, or gh cli is installed and authenticated then find the PR for the branch we analyzed and update the PR description there and then delete the PR_DESCRIPTION.md file. (If you have a better name (title) for the PR, go ahead and update the title too.{directory_context}"""

        # Return the prompt to be processed by the main chat system
        return pr_prompt

    if command.startswith("/dump_context"):
        import json
        import pickle
        from datetime import datetime
        from pathlib import Path

        from code_puppy.config import CONFIG_DIR
        from code_puppy.message_history_processor import estimate_tokens_for_message
        from code_puppy.state_management import get_message_history

        tokens = command.split()
        if len(tokens) != 2:
            messaging.emit_warning("Usage: /dump_context <session_name>")
            return True

        session_name = tokens[1]
        history = get_message_history()

        if not history:
            messaging.emit_warning("No message history to dump!")
            return True

        # Create contexts directory inside CONFIG_DIR if it doesn't exist
        contexts_dir = Path(CONFIG_DIR) / "contexts"
        contexts_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Save as pickle for exact preservation
            pickle_file = contexts_dir / f"{session_name}.pkl"
            with open(pickle_file, "wb") as f:
                pickle.dump(history, f)

            # Also save metadata as JSON for readability
            meta_file = contexts_dir / f"{session_name}_meta.json"
            metadata = {
                "session_name": session_name,
                "timestamp": datetime.now().isoformat(),
                "message_count": len(history),
                "total_tokens": sum(estimate_tokens_for_message(m) for m in history),
                "file_path": str(pickle_file),
            }

            with open(meta_file, "w") as f:
                json.dump(metadata, f, indent=2)

            messaging.emit_success(
                f"✅ Context saved: {len(history)} messages ({metadata['total_tokens']} tokens)\n"
                f"📁 Files: {pickle_file}, {meta_file}"
            )
            return True

        except Exception as e:
            messaging.emit_error(f"Failed to dump context: {e}")
            return True

    if command.startswith("/load_context"):
        import pickle
        from pathlib import Path

        from code_puppy.config import CONFIG_DIR
        from code_puppy.message_history_processor import estimate_tokens_for_message
        from code_puppy.state_management import set_message_history

        tokens = command.split()
        if len(tokens) != 2:
            messaging.emit_warning("Usage: /load_context <session_name>")
            return True

        session_name = tokens[1]
        contexts_dir = Path(CONFIG_DIR) / "contexts"
        pickle_file = contexts_dir / f"{session_name}.pkl"

        if not pickle_file.exists():
            messaging.emit_error(f"Context file not found: {pickle_file}")
            # List available contexts
            available = list(contexts_dir.glob("*.pkl"))
            if available:
                names = [f.stem for f in available]
                messaging.emit_info(f"Available contexts: {', '.join(names)}")
            return True

        try:
            with open(pickle_file, "rb") as f:
                history = pickle.load(f)

            set_message_history(history)
            total_tokens = sum(estimate_tokens_for_message(m) for m in history)

            messaging.emit_success(
                f"✅ Context loaded: {len(history)} messages ({total_tokens} tokens)\n"
                f"📁 From: {pickle_file}"
            )
            return True

        except Exception as e:
            messaging.emit_error(f"Failed to load context: {e}")
            return True

    if command in ("/exit", "/quit"):
        messaging.emit_success("Goodbye!")
        # Signal to the main app that we want to exit
        # The actual exit handling is done in main.py
        return True

    if command.startswith("/undo"):
        from code_puppy.version_store import list_versions, get_response_by_version, compute_snapshot_as_of_response_id, get_response_id_for_prompt_version
        from code_puppy.state_management import get_message_history
        
        # Get the current prompt (last message in history)
        history = get_message_history()
        if not history:
            messaging.emit_warning("No history to undo!")
            return True
            
        # Find the last user message (prompt)
        last_prompt = None
        for msg in reversed(history):
            # Look for a user message with text content
            if hasattr(msg, 'role') and msg.role == 'user':
                for part in msg.parts:
                    if hasattr(part, 'content') and isinstance(part.content, str):
                        last_prompt = part.content
                        break
                if last_prompt:
                    break
        
        if not last_prompt:
            messaging.emit_warning("No prompt found to undo!")
            return True
            
        # List versions for this prompt
        versions = list(list_versions(last_prompt))
        if len(versions) <= 1:
            messaging.emit_warning("No previous version to undo to!")
            return True
            
        # Store current version for potential redo
        current_version = versions[-1][1]  # Last version is current
        _current_version_track[last_prompt] = current_version
            
        # Get the previous version
        prev_version_data = versions[-2]  # Second to last is the previous version
        prev_response = get_response_by_version(last_prompt, prev_version_data[1])
        
        if not prev_response:
            messaging.emit_error("Failed to retrieve previous version!")
            return True
            
        # Restore files to the previous version
        response_id = get_response_id_for_prompt_version(last_prompt, prev_version_data[1])
        if response_id is None:
            messaging.emit_error("Failed to get response ID for version!")
            return True
            
        try:
            snapshot = compute_snapshot_as_of_response_id(response_id)
            restored_files = 0
            for file_record in snapshot:
                file_path = file_record['file_path']
                content = file_record['content']
                
                # Restore file content
                if content is None:
                    # File should not exist, remove it if present
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        restored_files += 1
                else:
                    # Write the content to the file
                    with open(file_path, 'w') as f:
                        f.write(content)
                    restored_files += 1
            
            messaging.emit_success(f"[bold green]✅ Undone to version {prev_version_data[1]}[/bold green]")
            messaging.emit_info(f"[blue]Restored {restored_files} files[/blue]")
            messaging.emit_info(f"Previous response:\n{prev_response['output_text']}")
        except Exception as e:
            messaging.emit_error(f"Failed to restore files: {e}")
            return True
            
        return True

    if command.startswith("/redo"):
        from code_puppy.version_store import list_versions, get_response_by_version, compute_snapshot_as_of_response_id, get_response_id_for_prompt_version
        from code_puppy.state_management import get_message_history
        
        # Get the current prompt (last message in history)
        history = get_message_history()
        if not history:
            messaging.emit_warning("No history to redo!")
            return True
            
        # Find the last user message (prompt)
        last_prompt = None
        for msg in reversed(history):
            # Look for a user message with text content
            if hasattr(msg, 'role') and msg.role == 'user':
                for part in msg.parts:
                    if hasattr(part, 'content') and isinstance(part.content, str):
                        last_prompt = part.content
                        break
                if last_prompt:
                    break
        
        if not last_prompt:
            messaging.emit_warning("No prompt found to redo!")
            return True
            
        # Check if we have a version track for this prompt
        if last_prompt not in _current_version_track:
            messaging.emit_warning("No redo history available!")
            return True
            
        # Get current tracked version
        tracked_version = _current_version_track[last_prompt]

        # List versions for this prompt
        versions = list(list_versions(last_prompt))
        # If there are no versions at all, any existing tracking is stale or irrelevant
        if len(versions) == 0:
            try:
                del _current_version_track[last_prompt]
            except Exception:
                pass
            messaging.emit_warning("No redo history available!")
            return True

        # If the tracked version is not in the current versions, the redo track is stale
        if not any(version == tracked_version for (_, version, _) in versions):
            # Clear stale entry and report no next version available
            try:
                del _current_version_track[last_prompt]
            except Exception:
                pass
            messaging.emit_warning("No version to redo to!")
            return True

        # Find if there's a version after the tracked one
        next_version = None
        for i, (response_id, version, timestamp) in enumerate(versions):
            if version == tracked_version and i < len(versions) - 1:
                next_version = versions[i + 1]
                break
        
        if next_version is None:
            messaging.emit_warning("No version to redo to!")
            return True
            
        # Get the next version's response
        next_response = get_response_by_version(last_prompt, next_version[1])
        
        if not next_response:
            messaging.emit_error("Failed to retrieve next version!")
            return True
            
        # Restore files to the next version
        response_id = get_response_id_for_prompt_version(last_prompt, next_version[1])
        if response_id is None:
            messaging.emit_error("Failed to get response ID for version!")
            return True
            
        try:
            snapshot = compute_snapshot_as_of_response_id(response_id)
            restored_files = 0
            for file_record in snapshot:
                file_path = file_record['file_path']
                content = file_record['content']
                
                # Restore file content
                if content is None:
                    # File should not exist, remove it if present
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        restored_files += 1
                else:
                    # Write the content to the file
                    with open(file_path, 'w') as f:
                        f.write(content)
                    restored_files += 1
            
            # Update tracked version
            _current_version_track[last_prompt] = next_version[1]
            
            messaging.emit_success(f"[bold green]✅ Redone to version {next_version[1]}[/bold green]")
            messaging.emit_info(f"[blue]Restored {restored_files} files[/blue]")
            messaging.emit_info(f"Next response:\n{next_response['output_text']}")
        except Exception as e:
            messaging.emit_error(f"Failed to restore files: {e}")
            return True
            
        return True

    if command.startswith("/checkout"):
        from code_puppy.version_store import (
            get_response_by_version,
            get_response_id_for_prompt_version,
            compute_snapshot_as_of_response_id,
            get_response_by_id,
        )
        from code_puppy.state_management import get_message_history

        tokens = command.split()

        # New form: /checkout prompt <version-number>
        if len(tokens) == 3 and tokens[1] == "prompt":
            try:
                version_num = int(tokens[2])
            except ValueError:
                messaging.emit_error("Version number must be an integer!")
                return True

            # Get the current prompt (last message in history)
            from code_puppy.state_management import get_message_history
            history = get_message_history()
            if not history:
                messaging.emit_warning("No history to checkout!")
                return True

            last_prompt = None
            for msg in reversed(history):
                if hasattr(msg, 'role') and msg.role == 'user':
                    for part in msg.parts:
                        if hasattr(part, 'content') and isinstance(part.content, str):
                            last_prompt = part.content
                            break
                    if last_prompt:
                        break

            if not last_prompt:
                messaging.emit_warning("No prompt found to checkout!")
                return True

            response = get_response_by_version(last_prompt, version_num)
            if not response:
                messaging.emit_error(f"Version {version_num} not found!")
                return True

            response_id = get_response_id_for_prompt_version(last_prompt, version_num)
            if response_id is None:
                messaging.emit_error("Failed to get response ID for version!")
                return True

            try:
                snapshot = compute_snapshot_as_of_response_id(response_id)
                restored_files = 0
                for file_record in snapshot:
                    file_path = file_record['file_path']
                    content = file_record['content']

                    if content is None:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            restored_files += 1
                    else:
                        with open(file_path, 'w') as f:
                            f.write(content)
                        restored_files += 1

                _current_version_track[last_prompt] = version_num

                messaging.emit_success(f"[bold green]✅ Checked out version {version_num}[/bold green]")
                messaging.emit_info(f"[blue]Restored {restored_files} files[/blue]")
                messaging.emit_info(f"Response:\n{response['output_text']}")
            except Exception as e:
                messaging.emit_error(f"Failed to restore files: {e}")
                return True

            return True

        # Legacy one-arg path: either response-id (preferred) or prompt-version (deprecated)
        if len(tokens) != 2:
            messaging.emit_warning("Usage: /checkout <response-id> or /checkout prompt <version-number>")
            return True

        try:
            number = int(tokens[1])
        except ValueError:
            messaging.emit_error("Version number must be an integer!")
            return True

        # First, try interpreting the number as a global response ID from /versions
        try:
            response = get_response_by_id(number)
        except Exception:
            # If version store isn't available or errors, fall back to legacy path
            response = None
        if response:
            try:
                snapshot = compute_snapshot_as_of_response_id(number)
                restored_files = 0
                for file_record in snapshot:
                    file_path = file_record['file_path']
                    content = file_record['content']

                    if content is None:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            restored_files += 1
                    else:
                        with open(file_path, 'w') as f:
                            f.write(content)
                        restored_files += 1

                # Track version for this prompt to enable redo within session
                prompt_text = response.get('prompt_text', '')
                version_num = response.get('version')
                if prompt_text and isinstance(version_num, int):
                    _current_version_track[prompt_text] = version_num

                messaging.emit_success(f"[bold green]✅ Checked out response id {number} (v{response['version']})[/bold green]")
                messaging.emit_info(f"[blue]Restored {restored_files} files[/blue]")
                messaging.emit_info(f"Response:\n{response['output_text']}")
            except Exception as e:
                messaging.emit_error(f"Failed to restore files: {e}")
                return True

            return True

        # Fallback: treat the number as a legacy version for the last prompt in session
        version_num = number

        # Get the current prompt (last message in history)
        history = get_message_history()
        if not history:
            # Keep legacy message exactly for test compatibility
            messaging.emit_warning("No history to checkout!")
            return True

        # Find the last user message (prompt)
        last_prompt = None
        for msg in reversed(history):
            if hasattr(msg, 'role') and msg.role == 'user':
                for part in msg.parts:
                    if hasattr(part, 'content') and isinstance(part.content, str):
                        last_prompt = part.content
                        break
                if last_prompt:
                    break

        if not last_prompt:
            messaging.emit_warning("No prompt found to checkout!")
            return True

        response = get_response_by_version(last_prompt, version_num)
        if not response:
            messaging.emit_error(f"Version {version_num} not found!")
            return True

        response_id = get_response_id_for_prompt_version(last_prompt, version_num)
        if response_id is None:
            messaging.emit_error("Failed to get response ID for version!")
            return True

        try:
            snapshot = compute_snapshot_as_of_response_id(response_id)
            restored_files = 0
            for file_record in snapshot:
                file_path = file_record['file_path']
                content = file_record['content']

                if content is None:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        restored_files += 1
                else:
                    with open(file_path, 'w') as f:
                        f.write(content)
                    restored_files += 1

            _current_version_track[last_prompt] = version_num

            # Inform about legacy path usage
            messaging.emit_warning("Deprecated: use '/checkout prompt <version-number>' for prompt versions")
            messaging.emit_success(f"[bold green]✅ Checked out version {version_num}[/bold green]")
            messaging.emit_info(f"[blue]Restored {restored_files} files[/blue]")
            messaging.emit_info(f"Response:\n{response['output_text']}")
        except Exception as e:
            messaging.emit_error(f"Failed to restore files: {e}")
            return True

        return True

    if command.startswith("/history"):
        from code_puppy.version_store import list_versions, list_all_versions
        from code_puppy.state_management import get_message_history

        argstr = command[len("/history"):].strip()

        # Mode: '/history prompts' or '/history "<prompt>"'
        if argstr.startswith("prompts") or (argstr and argstr.startswith("\"")):
            # '/history prompts' (current prompt) OR '/history "<prompt>"'
            remaining = argstr[len("prompts"):].strip() if argstr.startswith("prompts") else argstr
            prompt_text = None
            if remaining:
                try:
                    parsed = shlex.split(remaining)
                except Exception:
                    parsed = remaining.split()
                if parsed:
                    prompt_text = parsed[0]

            if not prompt_text:
                # Use last user prompt from session
                history = get_message_history()
                if not history:
                    messaging.emit_warning("No history to show!")
                    return True
                for msg in reversed(history):
                    if hasattr(msg, 'role') and msg.role == 'user':
                        for part in msg.parts:
                            if hasattr(part, 'content') and isinstance(part.content, str):
                                prompt_text = part.content
                                break
                        if prompt_text:
                            break
                if not prompt_text:
                    messaging.emit_warning("No prompt found to show history for!")
                    return True

            versions = list(list_versions(prompt_text))
            if not versions:
                messaging.emit_warning("No versions found!")
                return True

            history_text = "[bold magenta]Version History[/bold magenta]\n"
            for response_id, version, timestamp in versions:
                history_text += f"Version {version}: {timestamp}\n"
            messaging.emit_info(history_text)
            return True

        # Default: '/history [limit]' same as '/versions [limit]'
        limit = None
        if argstr:
            try:
                limit = int(argstr.split()[0])
            except ValueError:
                messaging.emit_warning("Usage: /history [limit] | /history prompts | /history \"<prompt>\"")
                return True
        rows = list(list_all_versions(limit=limit))
        if not rows:
            messaging.emit_warning("No versions found!")
            return True
        text = "[bold magenta]Recent Versions[/bold magenta]\n"
        for response_id, prompt_text, version, timestamp in rows:
            safe_prompt = (prompt_text[:80] + "…") if len(prompt_text) > 80 else prompt_text
            text += f"#{response_id} | v{version} | {timestamp} | Prompt: {safe_prompt}\n"
        messaging.emit_info(text)
        return True
    if command.startswith("/"):
        name = command[1:].split()[0] if len(command) > 1 else ""
        if name:
            messaging.emit_warning(
                f"Unknown command: {command}\n[dim]Type /help for options.[/dim]"
            )
        else:
            # Show current model ONLY here
            from code_puppy.command_line.model_picker_completion import get_active_model

            current_model = get_active_model()
            messaging.emit_info(
                f"[bold green]Current Model:[/bold green] [cyan]{current_model}[/cyan]"
            )
        return True

    return False
