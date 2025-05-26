import asyncio
import argparse
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.console import ConsoleOptions, RenderResult
from rich.markdown import CodeBlock
from rich.text import Text

from pydantic_ai import Agent
# Initialize rich console for pretty output

# These imports need to be relative for the package structure
from code_agent.models.codesnippet import CodeResponse
from code_agent.agent import code_generation_agent
from code_agent.agent_tools import console 

async def main():
    # Load environment variables from .env file
    load_dotenv()
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Code Generation Agent - Similar to Windsurf or Cursor")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    args = parser.parse_args()
    
    if args.interactive:
        await interactive_mode()
    else:
        parser.print_help()

def prettier_code_blocks():
    """Make rich code blocks prettier and easier to copy.

    From https://github.com/samuelcolvin/aicli/blob/v0.8.0/samuelcolvin_aicli.py#L22
    """

    class SimpleCodeBlock(CodeBlock):
        def __rich_console__(
            self, console: Console, options: ConsoleOptions
        ) -> RenderResult:
            code = str(self.text).rstrip()
            yield Text(self.lexer_name, style='dim')
            yield Syntax(
                code,
                self.lexer_name,
                theme=self.theme,
                background_color='default',
                word_wrap=True,
            )
            yield Text(f'/{self.lexer_name}', style='dim')

    Markdown.elements['fence'] = SimpleCodeBlock


async def interactive_mode() -> None:
    """Run the agent in interactive mode."""
    console.print("[bold green]Code Generation Agent[/bold green] - Interactive Mode")
    console.print("Type 'exit' or 'quit' to exit the interactive mode.")
    console.print("Type 'clear' to reset the conversation history.")
    
    message_history = []
    
    while True:
        task = console.input("[bold blue]Enter your coding task:[/bold blue] ")
        
        # Check for exit commands
        if task.lower() in ["exit", "quit"]:
            console.print("[bold green]Goodbye![/bold green]")
            break
        
        # Check for clear command
        if task.lower() == "clear":
            message_history = []
            console.print("[bold yellow]Conversation history cleared![/bold yellow]")
            console.print("[dim]The agent will not remember previous interactions.[/dim]\n")
            continue
        
        if task.strip():
            console.print(f"\n[bold blue]Processing task:[/bold blue] {task}\n")
            
            # Counter for consecutive auto-continue invocations
            auto_continue_count = 0
            max_auto_continues = 10
            is_done = False
            
            while not is_done and auto_continue_count <= max_auto_continues:
                try:
                    prettier_code_blocks()
                    
                    # Only show "asking" message for initial query or if not auto-continuing
                    if auto_continue_count == 0:
                        console.log(f'Asking: {task}...', style='cyan')
                    else:
                        console.log(f'Auto-continuing ({auto_continue_count}/{max_auto_continues})...', style='cyan')
                    
                    # Store agent's full response
                    agent_response = None
                    response_content = ""
                    
                    result = await code_generation_agent.run(task, message_history=message_history)
                    # Get the structured response
                    agent_response = result.output
                    console.print(agent_response.output_message)
                    
                    # Update message history with all messages from this interaction
                    message_history = result.new_messages()
                    
                    # Show usage statistics
                    console.print(result.usage())
                    
                    # Check the structured response
                    if agent_response:
                        # Check if the agent should continue
                        if not agent_response.should_continue:
                            is_done = True
                            console.print("\n[bold green]✓ Agent has completed the task![/bold green]")
                        # Check if the agent needs user input
                        elif agent_response.needs_user_input_to_continue:
                            console.print("\n[bold yellow]⚠ Agent needs your input to continue.[/bold yellow]")
                            is_done = True  # Exit the loop to get user input
                        # Otherwise, auto-continue if we haven't reached the limit
                        elif auto_continue_count < max_auto_continues:
                            auto_continue_count += 1
                            task = "please continue"
                            console.print("\n[yellow]Agent continuing automatically...[/yellow]")
                        else:
                            # Reached max auto-continues
                            console.print(f"\n[bold yellow]⚠ Reached maximum of {max_auto_continues} automatic continuations.[/bold yellow]")
                            console.print("[dim]You can enter a new request or type 'please continue' to resume.[/dim]")
                            is_done = True  # Exit the inner loop
                    
                    # Show context status
                    console.print(f"[dim]Context: {len(message_history)} messages in history[/dim]\n")
                
                except Exception:
                    console.print_exception(show_locals=True)
                    is_done = True  # Exit on error

def main_entry():
    """Entry point for the installed CLI tool."""
    asyncio.run(main())

if __name__ == "__main__":
    main_entry()
