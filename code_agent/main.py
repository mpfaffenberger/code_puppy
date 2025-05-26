import asyncio
import argparse
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.live import Live
from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import CodeBlock, Markdown
from rich.syntax import Syntax
from rich.text import Text

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
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
    console.print("Type 'clear' to reset the conversation history.\n")
    
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
            
            try:
                prettier_code_blocks()
                console.log(f'Asking: {task}...', style='cyan')
                
                with Live('', console=console) as live:
                    async with code_generation_agent.run_stream(task, message_history=message_history) as result:
                        async for message in result.stream():
                            live.update(Markdown(message))
                
                # Update message history with all messages from this interaction
                [message_history.append(msg) for msg in result.all_messages()]
                
                # Show usage statistics
                console.print(result.usage())
                
                # Show context status
                console.print(f"[dim]Context: {len(message_history)} messages in history[/dim]\n")
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {str(e)}")

def main_entry():
    """Entry point for the installed CLI tool."""
    asyncio.run(main())

if __name__ == "__main__":
    main_entry()
