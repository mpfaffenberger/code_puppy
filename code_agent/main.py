import asyncio
import argparse
import sys
import os
from dotenv import load_dotenv
from pydantic_ai.messages import SystemPromptPart, ToolCallPart, ToolReturnPart
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.console import ConsoleOptions, RenderResult
from rich.markdown import CodeBlock
from rich.text import Text
from prompt_toolkit import prompt
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.history import InMemoryHistory
import signal

# Initialize rich console for pretty output
import code_agent.tools
from code_agent.tools.common import console
from code_agent.agent import code_generation_agent
shutdown_flag = False

# Function to handle shutdown signal
def handle_shutdown(signum, frame):
    global shutdown_flag
    shutdown_flag = True
    console.print("[bold red] Shutdown requested. Exiting...[/bold red]")
    sys.exit(0)

# Define a function to get the secret file path
def get_secret_file_path():
    hidden_directory = os.path.join(os.path.expanduser("~"), ".agent_secret")
    if not os.path.exists(hidden_directory):
        os.makedirs(hidden_directory)
    return os.path.join(hidden_directory, "history.txt")

async def main():
    global shutdown_flag

    # Load environment variables from .env file
    load_dotenv()

    # Set up argument parser
    parser = argparse.ArgumentParser(description="Code Generation Agent - Similar to Windsurf or Cursor")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    parser.add_argument("command", nargs='*', help="Run a single command")
    args = parser.parse_args()

    # Register signals for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    history_file_path = get_secret_file_path()

    if args.command:
        # Join the list of command arguments into a single string command
        command = ' '.join(args.command)
        try:
            while not shutdown_flag:
                response = await code_generation_agent.run(command)
                console.print(response.output_message)
                if response.awaiting_user_input:
                    console.print("[bold red]The agent requires further input. Interactive mode is recommended for such tasks.")
        except AttributeError as e:
            console.print(f"[bold red]AttributeError:[/bold red] {str(e)}")
            console.print("[bold yellow]\u26a0 The response might not be in the expected format, missing attributes like 'output_message'.")
        except Exception as e:
            console.print(f"[bold red]Unexpected Error:[/bold red] {str(e)}")
    elif args.interactive:
        await interactive_mode(history_file_path)
    else:
        parser.print_help()

# Add the file handling functionality for interactive mode
async def interactive_mode(history_file_path: str) -> None:
    """Run the agent in interactive mode."""
    global shutdown_flag
    console.print("[bold green]Code Generation Agent[/bold green] - Interactive Mode")
    console.print("Type 'exit' or 'quit' to exit the interactive mode.")
    console.print("Type 'clear' to reset the conversation history.")

    message_history = []

    # Initialize history from the secret file if it exists
    history = InMemoryHistory()
    if os.path.exists(history_file_path):
        with open(history_file_path, 'r') as history_file:
            for line in history_file:
                history.append_string(line.strip())

    bindings = KeyBindings()

    def exit_(event):
        event.app.exit()

    def clear(event):
        event.current_buffer.document = Document()

    # Add exit and clear commands
    bindings.add('c-x')(exit_)
    bindings.add('c-c')(clear)

    # Track if the last line was empty for double-Enter detection
    last_empty_line = [False]

    @bindings.add('enter')
    def _(event):
        """Submit input when Enter is pressed twice on empty lines."""
        buffer = event.current_buffer
        doc = buffer.document

        # If buffer is empty, do nothing special
        if not doc.text:
            buffer.newline()
            return

        # Get the current line
        current_line = doc.current_line
        is_current_line_empty = not current_line.strip()

        # If current line is empty and last line was also empty and we have content, submit
        if is_current_line_empty and last_empty_line[0] and doc.text.strip():
            buffer.validate_and_handle()
            last_empty_line[0] = False
            return

        # Update empty line tracker and insert newline
        last_empty_line[0] = is_current_line_empty
        buffer.newline()

    while not shutdown_flag:
        task = ""
        console.print("[bold blue]Enter your coding task (multiline is supported):[/bold blue]")

        task = prompt('> ', key_bindings=bindings, history=history, multiline=True, prompt_continuation=prompt_continuation, in_thread=True)

        if shutdown_flag:
            break

        # Check for exit commands
        if task.strip().lower() in ["exit", "quit"]:
            console.print("[bold green]Goodbye![/bold green]")
            break

        # Check for clear command
        if task.strip().lower() == "clear":
            message_history = []
            console.print("[bold yellow]Conversation history cleared![/bold yellow]")
            console.print("[dim]The agent will not remember previous interactions.[/dim]\n")
            continue

        if task.strip():
            console.print(f"\n[bold blue]Processing task:[/bold blue] {task}\n")

            # Write to the secret file for permanent history
            with open(history_file_path, 'a') as history_file:
                history_file.write(f"{task}\n")
            
            # Counter for consecutive auto-continue invocations
            auto_continue_count = 0
            max_auto_continues = 10
            is_done = False

            while not is_done and auto_continue_count <= max_auto_continues:
                if shutdown_flag:
                    break

                try:
                    prettier_code_blocks()

                    # Only show "asking" message for initial query or if not auto-continuing
                    if auto_continue_count == 0:
                        console.log(f'Asking: {task}...', style='cyan')
                    else:
                        console.log(f'Auto-continuing ({auto_continue_count}/{max_auto_continues})...', style='cyan')

                    # Store agent's full response
                    agent_response = None

                    result = await code_generation_agent.run(task, message_history=message_history)
                    # Get the structured response
                    agent_response = result.output
                    console.print(agent_response.output_message)

                    # Update message history with all messages from this interaction
                    message_history = result.new_messages()
                    if agent_response:
                        # Check if the agent needs user input
                        if agent_response.awaiting_user_input:
                            console.print("\n[bold yellow]\u26a0 Agent needs your input to continue.[/bold yellow]")
                            is_done = True  # Exit the loop to get user input
                        # Otherwise, auto-continue if we haven't reached the limit
                        elif auto_continue_count < max_auto_continues:
                            auto_continue_count += 1
                            task = "please continue"
                            console.print("\n[yellow]Agent continuing automatically...[/yellow]")
                        else:
                            # Reached max auto-continues
                            console.print(f"\n[bold yellow]\u26a0 Reached maximum of {max_auto_continues} automatic continuations.[/bold yellow]")
                            console.print("[dim]You can enter a new request or type 'please continue' to resume.[/dim]")
                            is_done = True

                    # Show context status
                    console.print(f"[dim]Context: {len(message_history)} messages in history[/dim]\n")

                except Exception:
                    console.print_exception(show_locals=True)
                    is_done = True

def prettier_code_blocks():
    class SimpleCodeBlock(CodeBlock):
        def __rich_console__(
            self, console: Console, options: ConsoleOptions
        ) -> RenderResult:
            code = str(self.text).rstrip()
            yield Text(self.lexer_name, style='dim')
            syntax = Syntax(
                code,
                self.lexer_name,
                theme=self.theme,
                background_color='default',
                line_numbers=True
            )
            yield syntax
            yield Text(f'/{self.lexer_name}', style='dim')

    Markdown.elements['fence'] = SimpleCodeBlock

def prompt_continuation(width, line_number, wrap_count):
    return ". "

def main_entry():
    """Entry point for the installed CLI tool."""
    asyncio.run(main())

if __name__ == "__main__":
    main_entry()
