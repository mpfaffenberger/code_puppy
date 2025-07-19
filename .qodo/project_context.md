# Code Puppy - Project Context for Qodo

## Project Overview

Code Puppy is an AI-powered code generation agent designed for enterprise-scale development, specifically optimized for Walmart Global Tech. It's a sophisticated tool that can understand programming tasks, generate high-quality code, and provide detailed explanations of its reasoning.

## Architecture

### Core Components

1. **Main Entry Point** (`code_puppy/main.py`)
   - CLI interface and interactive mode
   - Command parsing and execution
   - Integration with various AI models

2. **AI Model Integration**
   - Support for multiple AI providers (OpenAI, Gemini, Anthropic, Ollama, Azure)
   - Dynamic model switching
   - Rate limiting and retry logic
   - Custom endpoint support for enterprise environments

3. **Code Generation Engine**
   - Multi-language code generation
   - Context-aware programming assistance
   - Code explanation and documentation

4. **Enterprise Features**
   - Walmart-specific optimizations
   - Internal tool integration
   - Compliance framework
   - Security enhancements

### Key Technologies

- **Framework**: Pydantic-AI for AI model management
- **HTTP Client**: httpx with rate limiting
- **CLI**: Rich for beautiful terminal output
- **Logging**: Logfire for observability
- **Testing**: pytest with asyncio support
- **Code Quality**: Ruff for linting and formatting

## Development Workflow

### Environment Setup
- Python 3.10+ required
- Uses `uv` for dependency management
- Virtual environment in `.venv`
- Enterprise PyPI registry for Walmart internal use

### Testing Strategy
- pytest with asyncio support
- 95% code coverage requirement
- Comprehensive test suite in `tests/` directory
- Coverage reporting with pytest-cov

### Code Quality
- Ruff for linting and formatting
- Type hints required for all functions
- PEP 8 compliance
- Enterprise coding standards

## Key Features

### Multi-Model Support
The application supports various AI models through a unified interface:
- OpenAI GPT models
- Google Gemini
- Anthropic Claude
- Local Ollama models
- Azure OpenAI
- Custom enterprise endpoints

### Interactive CLI
- Command-line interface for direct task execution
- Interactive mode for ongoing conversations
- Model switching capabilities (`~m` command)
- Rich terminal output with syntax highlighting

### Enterprise Integration
- Walmart Global Tech optimizations
- Internal security protocols
- Compliance with enterprise standards
- Custom authentication and endpoints

## Configuration

### Environment Variables
- `OPENAI_API_KEY`: OpenAI API access
- `GEMINI_API_KEY`: Google Gemini access
- `AZURE_OPENAI_API_KEY`: Azure OpenAI access
- `AZURE_OPENAI_ENDPOINT`: Azure endpoint URL

### Model Configuration
Models are automatically fetched and cached locally. Custom models can be configured with:
- Custom endpoints
- Authentication headers
- SSL certificate paths
- Rate limiting parameters

### MCP Server Integration
Supports Model Context Protocol (MCP) servers for external tools:
- Context7 integration for documentation search
- Configurable through `~/.code_puppy/mcp_servers.json`
- Extensible plugin architecture

## File Structure

```
code_puppy/
├── main.py              # Main entry point
├── models.json          # Model configurations
└── [other modules]      # Core functionality

tests/                   # Test suite
├── test_*.py           # Test files
└── [test modules]      # Test organization

docs/                   # Documentation
├── README.md           # Main documentation
├── CONTRIBUTING.md     # Contribution guidelines
└── [other docs]        # Additional documentation
```

## Enterprise Considerations

### Dual Licensing
- Legacy code (pre-July 7, 2025): MIT License
- Walmart enhancements: Proprietary
- Clear separation of open source and proprietary components

### Security
- Enterprise-grade security protocols
- Secure API key management
- Custom certificate support
- Internal network compatibility

### Scalability
- Designed for global development teams
- Rate limiting and retry mechanisms
- Efficient caching strategies
- Asynchronous operations

## Development Guidelines

### Code Standards
1. Use type hints for all function parameters and return values
2. Implement proper error handling for AI model failures
3. Use async/await for I/O operations
4. Maintain comprehensive test coverage
5. Follow Walmart enterprise security guidelines

### AI-Specific Best Practices
1. Implement proper rate limiting for API calls
2. Handle model switching gracefully
3. Validate AI responses before processing
4. Use structured logging with logfire
5. Implement fallback mechanisms for model failures

### Testing Requirements
1. Unit tests for all core functionality
2. Integration tests for AI model interactions
3. Mock external dependencies appropriately
4. Test error conditions and edge cases
5. Maintain 95% code coverage

## Future Enhancements

### Planned Features
- Enhanced MCP server support
- Additional AI model integrations
- Improved enterprise security features
- Advanced code analysis capabilities
- Better integration with Walmart tools

### Technical Debt
- Monitor and address performance bottlenecks
- Regular dependency updates
- Security vulnerability assessments
- Code quality improvements
- Documentation updates

This project represents a sophisticated AI-powered development tool that balances open-source innovation with enterprise requirements, specifically tailored for Walmart Global Tech's development ecosystem.