# Code Generation Agent

## Overview

This project is a sophisticated AI-powered code generation agent, designed to understand programming tasks, generate high-quality code, and explain its reasoning similar to tools like Windsurf and Cursor. 

## Features

- **Multi-language support**: Capable of generating code in various programming languages.
- **Interactive CLI**: A command-line interface for interactive use.
- **Detailed explanations**: Provides insights into generated code to understand its logic and structure.
- **Easy Integration**: Embed it seamlessly into Python projects.

## New Feature
- **Real-time collaboration**: Allows multiple users to collaboratively edit and review code generation tasks in real-time.

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository_url>
   cd <repository_name>
   ```

2. **Install dependencies**:
   ```bash
   pip install -e .
   # OR
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   - Create an `.env` file in the root, using `.env.example` as a template, to store required API keys.

## Usage

### Command Line Interface

Run specific tasks or engage in interactive mode:

```bash
# Execute a task directly
uv run python main.py "write me a C++ hello world program in /tmp/main.cpp then compile it and run it"

# Enter interactive mode
uv run python main.py --interactive
```

### Python API

Utilize the agent programmatically within your Python scripts:

```python
import asyncio
from code_agent.agent_tools import generate_code

async def main():
    task = "Your task description"
    response = await generate_code(None, task)
    
    if response.success:
        for snippet in response.snippets:
            print(f"Language: {snippet.language}")
            print(snippet.code)
            print(snippet.explanation)

if __name__ == "__main__":
    asyncio.run(main())
```

Explore the `examples` directory for elaborated utilization samples.

## Project Structure

- **`code_agent/agent.py`** - Core functionalities of the agent.
- **`code_agent/agent_tools.py`** - Tools and utilities for code generation.
- **`code_agent/agent_prompts.py`** - Templates and prompts used by the system.
- **`code_agent/models/`** - Data models for defining code and responses.
- **`examples/`** - Example scripts showcasing agent capabilities.
- **`main.py`** - Entry point for command-line interactions.

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository.
2. Create a new branch (`git checkout -b feature/xyz`).
3. Commit your changes (`git commit -m 'Add feature'`).
4. Push to the branch (`git push origin feature/xyz`).
5. Open a Pull Request.

## Requirements

- Python 3.9+
- OpenAI API key (for GPT models)
- Optionally: Gemini API key (for Google's Gemini models)

## Troubleshooting

- Ensure all dependencies are installed correctly and the environment is properly configured.
- Check that API keys are valid and not expired.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
