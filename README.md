# 🐶 Code Puppy 🐶
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen)
  <a href="https://github.com/mpfaffenberger/code_puppy"><img src="https://img.shields.io/pypi/pyversions/pydantic-ai.svg" alt="versions"></a>
  <a href="https://github.com/mpfaffenberger/code_puppy/blob/main/LICENSE"><img src="https://img.shields.io/github/license/pydantic/pydantic-ai.svg?v" alt="license"></a>

*"Who needs an IDE?"* - someone, probably.

## Overview

*This project was coded angrily in reaction to Windsurf and Cursor removing access to models and raising prices.* 

*You could also run 50 code puppies at once if you were insane enough.*

*Would you rather plow a field with one ox or 1024 puppies?* 
    - If you pick the ox, better slam that back button in your browser.
    

Code Puppy is an AI-powered code generation agent, designed to understand programming tasks, generate high-quality code, and explain its reasoning similar to tools like Windsurf and Cursor. 

## Features

- **Multi-language support**: Capable of generating code in various programming languages.
- **Interactive CLI**: A command-line interface for interactive use.
- **Detailed explanations**: Provides insights into generated code to understand its logic and structure.

## Command Line Animation

![Code Puppy](code_puppy.gif)

## Installation

`pip install code-puppy`

## Usage
```bash
export MODEL_NAME=gpt-4.1 # or gemini-2.5-flash-preview-05-20 as an example for Google Gemini models
export OPENAI_API_KEY=<your_openai_api_key> # or GEMINI_API_KEY for Google Gemini models
export YOLO_MODE=true # to bypass the safety confirmation prompt when running shell commands

# or ...

AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...

code-puppy --interactive
```
Running in a super weird corporate environment? 

Try this:
```bash
export MODEL_NAME=my-custom-model
export YOLO_MODE=true
export MODELS_JSON_PATH=/path/to/custom/models.json
```

```json
{
    "my-custom-model": {
        "type": "custom_openai",
        "name": "o4-mini-high",
        "max_requests_per_minute": 100,
        "max_retries": 3,
        "retry_base_delay": 10,
        "custom_endpoint": {
            "url": "https://my.custom.endpoint:8080",
            "headers": {
                "X-Api-Key": "<Your_API_Key>",
                "Some-Other-Header": "<Some_Value>"
            },
            "ca_certs_path": "/path/to/cert.pem"
        }
    }
}
```
Open an issue if your environment is somehow weirder than mine.

Run specific tasks or engage in interactive mode:

```bash
# Execute a task directly
code-puppy "write me a C++ hello world program in /tmp/main.cpp then compile it and run it"
```

## Requirements

- Python 3.9+
- OpenAI API key (for GPT models)
- Gemini API key (for Google's Gemini models)
- Anthropic key (for Claude models)
- Ollama endpoint available

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Puppy Rules
Puppy rules allow you to define and enforce coding standards and styles that your code should comply with. These rules can cover various aspects such as formatting, naming conventions, and even design guidelines.

### Example of a Puppy Rule
For instance, if you want to ensure that your application follows a specific design guideline, like using a dark mode theme with teal accents, you can define a puppy rule like this:

```plaintext
# Puppy Rule: Dark Mode with Teal Accents

  - theme: dark
  - accent-color: teal
  - background-color: #121212
  - text-color: #e0e0e0

Ensure that all components follow these color schemes to promote consistency in design.
```

## Conclusion
By using Code Puppy, you can maintain code quality and adhere to design guidelines with ease.
