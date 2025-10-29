"""History command implementation with message formatting capabilities."""
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from code_puppy.agents.agent_manager import get_current_agent
from code_puppy.config import (
    AUTOSAVE_DIR,
    get_current_autosave_id,
    get_current_autosave_session_name,
    get_puppy_name,
)
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.session_storage import list_sessions


class MessageFormatter:
    """Handles formatting and display of message history."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.puppy_name = get_puppy_name()
    
    def format_message(self, message: Any, index: int) -> str:
        """Format a single message for display."""
        try:
            role, content = self._extract_message_info(message)
            
            # Clean up role name
            if role not in ['USER', 'ASSISTANT', 'SYSTEM', 'TOOL']:
                role = role[:10]  # Truncate very long role names
            
            # Truncate long content for display (unless verbose)
            if not self.verbose and len(content) > 100:
                content = content[:97] + "..."
            
            return f"  [{index}] [cyan]{role}[/cyan]: {content}"
            
        except Exception as e:
            return f"  [{index}] [dim]Error parsing message: {str(e)[:30]}...[/dim]"
    
    def _extract_message_info(self, message: Any) -> Tuple[str, str]:
        """Extract role and content from various message formats."""
        # Handle simple role/content format (legacy/compatibility)
        if hasattr(message, 'role') and hasattr(message, 'content'):
            role = str(message.role).upper()
            content = str(message.content)
        
        # Handle Pydantic AI ModelRequest type
        elif hasattr(message, 'parts') and hasattr(message, 'role'):
            role = message.role.value if hasattr(message.role, 'value') else str(message.role)
            content = self._format_parts_message(message)
        
        # Handle other Pydantic AI ModelMessage types
        elif hasattr(message, 'parts'):
            content = self._format_parts_message(message)
            role = self._infer_role_from_class(message)
        
        # Handle dictionary format
        elif isinstance(message, dict):
            role = message.get('role', 'unknown').upper()
            content = message.get('content', str(message))
        
        # Fallback to string representation
        else:
            content = str(message)
            if content and len(content) < 200:  # If it's a short string, maybe it's just content
                role = 'MESSAGE'
            else:
                role = type(message).__name__.upper()
        
        return role, content
    
    def _format_parts_message(self, message: Any) -> str:
        """Format a message with parts (Pydantic AI format)."""
        content_parts = []
        tool_call_count = 0
        has_thinking = False
        thinking_parts = []
        tool_calls = []
        
        for part in message.parts:
            part_type = type(part).__name__
            
            # UserPromptPart - show the content directly
            if part_type == 'UserPromptPart' and hasattr(part, 'content'):
                user_content = str(part.content).strip()
                if user_content:
                    content_parts.append(user_content)
            
            # ThinkingPart - capture full thinking content and duration
            elif part_type == 'ThinkingPart':
                has_thinking = True
                thinking_content = str(part.content) if hasattr(part, 'content') else "(no thinking content)"
                
                if self.verbose:
                    # In verbose mode, store full thinking content
                    thinking_parts.append(thinking_content)
                else:
                    # In normal mode, just capture duration for summary
                    thinking_duration = self._extract_thinking_duration(part)
                    
                    # Store duration for later use
                    if thinking_duration is not None:
                        if not hasattr(message, '_thinking_duration'):
                            message._thinking_duration = 0
                        message._thinking_duration = max(message._thinking_duration, thinking_duration)
            
            # ToolCallPart - capture detailed tool call information
            elif 'ToolCall' in part_type:
                tool_call_count += 1
                
                if self.verbose:
                    # In verbose mode, capture detailed tool call information
                    tool_name = getattr(part, 'name', 'unknown_tool')
                    tool_args = getattr(part, 'args', {})
                    
                    # Format tool call details
                    try:
                        args_str = json.dumps(tool_args, indent=2, default=str)
                        tool_calls.append(f"  📋 {tool_name}:\n{args_str}")
                    except (TypeError, ValueError):
                        tool_calls.append(f"  📋 {tool_name}: {tool_args}")
            
            # TextPart - show the content
            elif part_type == 'TextPart' and hasattr(part, 'content'):
                text_content = str(part.content).strip()
                if text_content:
                    content_parts.append(text_content)
            
            # Fallback for other parts
            elif hasattr(part, 'content'):
                part_content = str(part.content).strip()
                if part_content:
                    content_parts.append(part_content)
            else:
                content_parts.append(str(part))
        
        return self._build_final_content(
            content_parts, has_thinking, thinking_parts, tool_call_count, tool_calls, message
        )
    
    def _extract_thinking_duration(self, part: Any) -> Optional[float]:
        """Extract thinking duration from a ThinkingPart."""
        thinking_duration = None
        
        # Check if the ThinkingPart has duration info
        if hasattr(part, 'duration'):
            thinking_duration = part.duration
        elif hasattr(part, 'content'):
            content_str = str(part.content)
            # Look for duration in content like "thought for 2.3s" or similar patterns
            duration_match = re.search(
                r'(?:(?:thought|thinking|for|took)\s+[^(]*?)?(\d+(?:\.\d+)?)\s*(?:s|sec|seconds?|ms|milliseconds?)',
                content_str, re.IGNORECASE
            )
            if duration_match:
                duration_val = float(duration_match.group(1))
                duration_unit = duration_match.group(0).lower()
                if 'ms' in duration_unit:
                    thinking_duration = duration_val / 1000  # Convert ms to seconds
                else:
                    thinking_duration = duration_val
        
        return thinking_duration
    
    def _build_final_content(
        self,
        content_parts: List[str],
        has_thinking: bool,
        thinking_parts: List[str],
        tool_call_count: int,
        tool_calls: List[str],
        message: Any
    ) -> str:
        """Build the final content string based on collected parts."""
        if self.verbose:
            # Verbose mode: show full details
            if thinking_parts:
                content_parts.append(f"\n  🧠 {self.puppy_name} thinking:")
                for i, thinking in enumerate(thinking_parts, 1):
                    # Indent each line of thinking content
                    for line in thinking.split('\n'):
                        content_parts.append(f"    {line}")
            
            if tool_calls:
                content_parts.append(f"\n  🔧 {self.puppy_name} tool calls:")
                for tool_call in tool_calls:
                    # Add proper indentation for each tool call line
                    for line in tool_call.split('\n'):
                        content_parts.append(f"    {line}")
        else:
            # Normal mode: show summaries
            if has_thinking:
                # Check if we have thinking duration info
                if hasattr(message, '_thinking_duration') and message._thinking_duration > 0:
                    duration = message._thinking_duration
                    if duration < 1:
                        # Show in milliseconds if less than 1 second
                        duration_ms = int(duration * 1000)
                        content_parts.append(f"{self.puppy_name} thought ({duration_ms}ms)")
                    else:
                        # Show in seconds with appropriate precision
                        if duration < 10:
                            content_parts.append(f"{self.puppy_name} thought ({duration:.2f}s)")
                        else:
                            content_parts.append(f"{self.puppy_name} thought ({duration:.1f}s)")
                else:
                    content_parts.append(f"{self.puppy_name} thought")
            
            if tool_call_count > 0:
                content_parts.append(f"{self.puppy_name} made {tool_call_count} tool call{'s' if tool_call_count != 1 else ''}")
        
        return " | ".join(content_parts) if content_parts else "Empty message"
    
    def _infer_role_from_class(self, message: Any) -> str:
        """Infer role from message class name."""
        class_name = message.__class__.__name__
        if 'request' in class_name.lower():
            return 'USER'
        elif 'response' in class_name.lower() or 'assistant' in class_name.lower():
            return 'ASSISTANT'
        elif 'system' in class_name.lower():
            return 'SYSTEM'
        else:
            return class_name.replace('Message', '').replace('Model', '').upper()


class HistoryCommand:
    """Handles the /history command with all its parsing and display logic."""
    
    def __init__(self):
        self.formatter: Optional[MessageFormatter] = None
    
    def parse_and_execute(self, command: str) -> bool:
        """Parse command arguments and execute the history display.
        
        Args:
            command: The full /history command string
            
        Returns:
            True if command was handled successfully
        """
        try:
            line_count, verbose = self._parse_command_args(command)
            if line_count is None:  # Error case from _parse_command_args
                return True
            self.formatter = MessageFormatter(verbose=verbose)
            
            group_id = str(uuid.uuid4())
            self._show_current_session_info(group_id)
            self._show_message_history(line_count, group_id)
            self._show_other_sessions(group_id)
            
            return True
            
        except Exception as e:
            emit_error(f"Failed to execute history command: {e}")
            return True
    
    def _parse_command_args(self, command: str) -> Tuple[Optional[int], bool]:
        """Parse command arguments for line count and verbose flag."""
        tokens = command.split()
        line_count = 10  # default
        verbose = False
        
        # Handle different argument patterns
        if len(tokens) == 2:
            arg = tokens[1]
            if arg in ['-v', '--verbose']:
                verbose = True
            else:
                try:
                    line_count = int(arg)
                    if line_count <= 0:
                        emit_error("Line count must be a positive integer")
                        return None, verbose
                except ValueError:
                    emit_error(f"Invalid line count: {arg}. Must be a positive integer.")
                    return None, verbose
        elif len(tokens) == 3:
            # Handle combinations like "/history 5 -v" or "/history -v 5"
            if '-v' in tokens or '--verbose' in tokens:
                verbose = True
                # Find the numeric argument
                for token in tokens[1:]:
                    if token not in ['-v', '--verbose']:
                        try:
                            line_count = int(token)
                            if line_count <= 0:
                                emit_error("Line count must be a positive integer")
                                return None, verbose
                        except ValueError:
                            emit_error(f"Invalid line count: {token}. Must be a positive integer.")
                            return None, verbose
                        break
            else:
                emit_error("Usage: /history [N] [-v|--verbose] - shows N messages, verbose shows full content")
                return None, verbose
        elif len(tokens) > 3:
            emit_error("Usage: /history [N] [-v|--verbose] - shows N messages, verbose shows full content")
            return None, verbose
        
        return line_count, verbose
    
    def _show_current_session_info(self, group_id: str) -> None:
        """Show information about the current autosave session."""
        current_session_name = get_current_autosave_session_name()
        emit_info(
            f"[bold magenta]Current Autosave Session:[/bold magenta] {current_session_name}",
            message_group=group_id,
        )
    
    def _show_message_history(self, line_count: int, group_id: str) -> None:
        """Show the actual message history."""
        try:
            agent = get_current_agent()
            history = agent.get_message_history()
            
            if not history or (isinstance(history, list) and len(history) == 0):
                emit_warning(
                    "No message history in current session. Ask me something first!",
                    message_group=group_id,
                )
                return
            
            total_tokens = sum(agent.estimate_tokens_for_message(m) for m in history)
            emit_info(
                f"[bold]Messages:[/bold] {len(history)} total ({total_tokens:,} tokens)",
                message_group=group_id,
            )
            
            # Show recent messages (last N messages, or all if N >= total)
            if len(history) > line_count:
                recent_messages = history[-line_count:]
            else:
                recent_messages = history
            
            mode_desc = " (verbose)" if self.formatter.verbose else ""
            emit_info(
                f"[bold]Recent Messages (last {len(recent_messages)}):{mode_desc}[/bold]",
                message_group=group_id,
            )
            
            # Display each message
            for i, message in enumerate(recent_messages, start=len(history) - len(recent_messages) + 1):
                formatted_message = self.formatter.format_message(message, i)
                emit_info(formatted_message, message_group=group_id)
            
            if len(history) > line_count:
                emit_info(
                    f"  [dim]... and {len(history) - line_count} earlier messages[/dim]",
                    message_group=group_id,
                )
                
        except Exception as e:
            emit_error(f"Failed to get current message history: {e}", message_group=group_id)
    
    def _show_other_sessions(self, group_id: str) -> None:
        """Show information about other available autosave sessions."""
        try:
            autosave_dir = Path(AUTOSAVE_DIR)
            all_sessions = list_sessions(autosave_dir)
            
            current_session_name = get_current_autosave_session_name()
            # Filter out the current session
            other_sessions = [s for s in all_sessions if s != current_session_name]
            
            if other_sessions:
                emit_info(
                    "\n[bold magenta]Other Autosave Sessions Available:[/bold magenta]",
                    message_group=group_id,
                )
                
                # Load metadata for each session to show more info
                for session in other_sessions[:5]:  # Limit to 5 to avoid spam
                    meta_path = autosave_dir / f"{session}_meta.json"
                    try:
                        with meta_path.open("r", encoding="utf-8") as f:
                            metadata = json.load(f)
                        timestamp = metadata.get("timestamp", "unknown")
                        message_count = metadata.get("message_count", 0)
                        total_tokens = metadata.get("total_tokens", 0)
                        
                        # Format timestamp nicely
                        if timestamp != "unknown":
                            try:
                                dt = datetime.fromisoformat(timestamp)
                                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                            except Exception:
                                pass
                        
                        emit_info(
                            f"  [cyan]{session}[/cyan] - {message_count} messages ({total_tokens:,} tokens) - {timestamp}",
                            message_group=group_id,
                        )
                    except Exception:
                        emit_info(
                            f"  [cyan]{session}[/cyan] - [dim]metadata unavailable[/dim]",
                            message_group=group_id,
                        )
                
                if len(other_sessions) > 5:
                    emit_info(
                        f"  [dim]... and {len(other_sessions) - 5} more sessions[/dim]",
                        message_group=group_id,
                    )
                
                emit_info(
                    "\n[dim]Tip: Use /load_context <session_name> to load a different session[/dim]",
                    message_group=group_id,
                )
            else:
                emit_info(
                    "\n[dim]No other autosave sessions available[/dim]",
                    message_group=group_id,
                )
                
        except Exception as e:
            emit_warning(f"Failed to list other sessions: {e}", message_group=group_id)


# Global instance for easy access
_history_command = HistoryCommand()


def handle_history_command(command: str) -> bool:
    """Convenient function to handle /history commands.
    
    Args:
        command: The full /history command string
        
    Returns:
        True if command was handled successfully
    """
    return _history_command.parse_and_execute(command)