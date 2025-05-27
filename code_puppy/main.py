import asyncio
import argparse
import os
import readline
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.console import ConsoleOptions, RenderResult
from rich.markdown import CodeBlock
from rich.text import Text
from rich.syntax import Syntax

# Initialize rich console for pretty output
from code_puppy.tools.common import console
from code_puppy.agent import code_generation_agent

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
    parser = argparse.ArgumentParser(description="Code Puppy - A code generation agent")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    parser.add_argument("command", nargs='*', help="Run a single command")
    args = parser.parse_args()

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
    console.print("[bold green]Code Puppy[/bold green] - Interactive Mode")
    console.print("Type 'exit' or 'quit' to exit the interactive mode.")
    console.print("Type 'clear' to reset the conversation history.")

    message_history = []

    # Set up readline history file in home directory
    history_file = os.path.expanduser('~/.code_puppy_history.txt')
    history_dir = os.path.dirname(history_file)
    
    # Ensure history directory exists
    if history_dir and not os.path.exists(history_dir):
        try:
            os.makedirs(history_dir, exist_ok=True)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not create history directory: {e}[/yellow]")
    
    # Try to read history file
    try:
        if os.path.exists(history_file):
            readline.read_history_file(history_file)
    except (FileNotFoundError, OSError) as e:
        console.print(f"[yellow]Warning: Could not read history file: {e}[/yellow]")
    
    readline.set_history_length(100)

    while True:
        console.print("[bold blue]Enter your coding task:[/bold blue]")
        
        try:
            # Simple single-line input
            task = input(">>> ")
            
            # Add to readline history if not empty
            if task.strip():
                readline.add_history(task)
            
            # Save history
            try:
                readline.write_history_file(history_file)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not write history file: {e}[/yellow]")
            
        except (KeyboardInterrupt, EOFError):
            # Handle Ctrl+C or Ctrl+D
            console.print("\n[yellow]Input cancelled[/yellow]")
            continue

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

            # Counter for consecutive auto-continue invocations
            auto_continue_count = 0
            max_auto_continues = 10
            is_done = False

            try:
                prettier_code_blocks()

                console.log(f'Asking: {task}...', style='cyan')

                # Store agent's full response
                agent_response = None

                result = await code_generation_agent.run(task, message_history=message_history)
                # Get the structured response
                agent_response = result.output
                console.print(agent_response.output_message)

                # Update message history with all messages from this interaction
                message_history = result.new_messages()

                if agent_response and agent_response.awaiting_user_input:
                    console.print("\n[bold yellow]\u26a0 Agent needs your input to continue.[/bold yellow]")

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

def main_entry():
    """Entry point for the installed CLI tool."""
    asyncio.run(main())

if __name__ == "__main__":
    main_entry()
