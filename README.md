# Code Generation Agent

A powerful AI-powered code generation agent inspired by tools like Windsurf and Cursor. This agent can understand programming tasks, generate high-quality code, and explain its reasoning.

## Features

- Generate code from natural language descriptions
- Provides detailed explanations of generated code
- Handles multiple programming languages
- Interactive CLI interface
- Easily integrate into your Python applications

## Installation

1. Clone this repository
2. Install dependencies:

```bash
pip install -e .
# OR
pip install -r requirements.txt
```

3. Create a `.env` file in the root directory with your API keys (see `.env.example` in the examples folder)

## Usage

### Command Line Interface

The agent can be used from the command line:

```bash
# Run with a specific task
python main.py "Create a function to calculate the factorial of a number"

# Run in interactive mode
python main.py --interactive
```

### Python API

You can also use the agent directly in your Python code:

```python
import asyncio
from agent_tools import generate_code

async def main():
    task = "Create a function that validates email addresses"
    response = await generate_code(None, task)
    
    if response.success:
        for snippet in response.snippets:
            print(f"Language: {snippet.language}")
            print(snippet.code)
            print(snippet.explanation)

if __name__ == "__main__":
    asyncio.run(main())
```

Check the `examples` directory for more usage examples.

## Project Structure

- `agent.py` - Main agent definition
- `agent_tools.py` - Implementation of code generation tools
- `agent_prompts.py` - System prompts and templates
- `models/` - Pydantic models for code snippets and responses
- `examples/` - Example usage scripts
- `main.py` - CLI interface

## Requirements

- Python 3.9+
- OpenAI API key (for GPT models)
- Optionally: Gemini API key (for Google's Gemini models)

## License

MIT
