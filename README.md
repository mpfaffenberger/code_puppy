# Code Puppy

## Overview

Code Puppy is a sophisticated AI-powered code generation agent, designed to understand programming tasks, generate high-quality code, and explain its reasoning similar to tools like Windsurf and Cursor. 

## Features

- **Multi-language support**: Capable of generating code in various programming languages.
- **Interactive CLI**: A command-line interface for interactive use.
- **Detailed explanations**: Provides insights into generated code to understand its logic and structure.

## Installation

`pip install code-puppy`

## Usage

### Command Line Interface

Run specific tasks or engage in interactive mode:

```bash
# Execute a task directly
code-puppy "write me a C++ hello world program in /tmp/main.cpp then compile it and run it"

# Enter interactive mode
code-puppy --interactive
```

## Requirements

- Python 3.9+
- OpenAI API key (for GPT models)
- Gemini API key (for Google's Gemini models)
- Anthropic key (for Claude models)
- Ollama endpoint available


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
